"""The ten pipeline nodes.

Each node returns a partial state update. LLM calls are always optional: when no
model is configured (Demo Mode, missing key, call failure) the deterministic
templates in :mod:`src.graph.deterministic` produce the same *shape* of output so
the graph, the UI and the PDF keep working.

Privacy: nodes never log story text, OCR text or draft content - only counts,
labels and error types.
"""

from __future__ import annotations

import functools
from typing import Any, Callable

from langgraph.errors import GraphBubbleUp
from langgraph.types import interrupt

from src.config import get_logger
from src.graph import deterministic as det
from src.graph.state import (
    ActionPlanOutput,
    ClassifierOutput,
    ComplaintDraft,
    EvidenceAnalysis,
    SaakshyaState,
    normalise_category,
)
from src.llm import SYSTEM_PROMPT, invoke_structured, llm_available
from src.rag import format_citation, get_kb

LOGGER = get_logger("graph")

MAX_FOLLOWUP_ROUNDS = 2
MAX_VERIFY_RETRIES = 2
MAX_MATCHES = 6


def safe_node(name: str, defaults: dict[str, Any] | None = None) -> Callable[[Callable], Callable]:
    """Wrap a node so an unexpected error is recorded instead of raised."""

    def decorator(func: Callable[[SaakshyaState], dict[str, Any]]) -> Callable[[SaakshyaState], dict[str, Any]]:
        @functools.wraps(func)
        def wrapper(state: SaakshyaState) -> dict[str, Any]:
            try:
                return func(state)
            except GraphBubbleUp:
                # ``interrupt()`` must reach the runtime, not the error handler.
                raise
            except Exception as exc:  # last line of defence for the demo
                LOGGER.warning("Node %s failed with %s", name, type(exc).__name__)
                payload: dict[str, Any] = dict(defaults or {})
                payload["stage"] = f"{name}_error"
                payload["errors"] = [f"{name}: {type(exc).__name__}"]
                return payload

        return wrapper

    return decorator


# --------------------------------------------------------------------- helpers
def story_text(state: SaakshyaState) -> str:
    """The story plus any follow-up answers, in one block."""
    parts = [state.get("user_story") or ""]
    parts.extend(answer for answer in (state.get("followup_answers") or []) if answer)
    return "\n".join(part for part in parts if part.strip())


def evidence_text(items: list[dict[str, Any]]) -> str:
    """Concatenate extracted text from every evidence item."""
    chunks = []
    for item in items:
        text = item.get("ocr_text") or item.get("transcript") or ""
        if text:
            chunks.append(f"{item.get('label', '')}: {text}")
    return "\n".join(chunks)


def corpus(state: SaakshyaState) -> str:
    """Every fact the pipeline is allowed to use (for the verifier)."""
    items = state.get("evidence_items") or []
    parts = [story_text(state), evidence_text(items)]
    for item in items:
        parts.append(
            " ".join(
                str(item.get(key) or "")
                for key in ("label", "filename", "evidence_type", "uploaded_at", "sha256")
            )
        )
    for event in state.get("timeline") or []:
        parts.append(str(event.get("date") or ""))
        parts.append(str(event.get("date_display") or ""))
    return "\n".join(parts)


def _categories_from_state(state: SaakshyaState) -> list[str]:
    """Category slugs in the current state."""
    return [str(item.get("category")) for item in state.get("issue_categories") or []]


def _dedupe_matches(matches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep the first occurrence of every KB id, capped at ``MAX_MATCHES``."""
    seen: set[str] = set()
    ordered: list[dict[str, Any]] = []
    for match in matches:
        kb_id = str(match.get("kb_id"))
        if kb_id and kb_id not in seen:
            seen.add(kb_id)
            ordered.append(match)
    return ordered[:MAX_MATCHES]


# ----------------------------------------------------------------------- nodes
@safe_node("intake", defaults={"intake_complete": True, "followup_questions": []})
def intake_node(state: SaakshyaState) -> dict[str, Any]:
    """Read the story and ask up to three follow-up questions if needed."""
    combined = story_text(state)
    if state.get("intake_complete"):
        return {"followup_questions": [], "stage": "intake_done"}
    round_no = int(state.get("followup_round") or 0)
    missing = det.missing_intake_info(combined)
    if missing and round_no < MAX_FOLLOWUP_ROUNDS:
        questions = det.followup_questions(combined, state.get("language", "en"))
        LOGGER.info("Intake needs %d follow-up question(s)", len(questions))
        return {
            "followup_questions": questions,
            "followup_round": round_no + 1,
            "intake_complete": False,
            "stage": "intake_questions",
        }
    LOGGER.info("Intake complete with %d missing field(s) tolerated", len(missing))
    return {"followup_questions": [], "intake_complete": True, "stage": "intake_done"}


@safe_node("safety_check", defaults={"risk_level": "low", "urgent_help": []})
def safety_check_node(state: SaakshyaState) -> dict[str, Any]:
    """Detect immediate danger and surface urgent help (the graph still continues)."""
    risk, signals = det.detect_danger(story_text(state))
    language = state.get("language", "en")
    return {
        "risk_level": risk,
        "risky_signals": signals,
        "urgent_help": det.urgent_help_lines(risk, language),
        "stage": "safety_checked",
    }


@safe_node("evidence_analyzer")
def evidence_analyzer_node(state: SaakshyaState) -> dict[str, Any]:
    """Extract dates, senders, threats and quotes from each evidence item."""
    items = [dict(item) for item in state.get("evidence_items") or []]
    llm = llm_available()
    for item in items:
        text = item.get("ocr_text") or item.get("transcript") or ""
        analysis: dict[str, Any] | None = None
        if llm:
            prompt = (
                f"Evidence type: {item.get('evidence_type', 'unknown')}\n"
                f"File name: {item.get('filename', 'unknown')}\n"
                f"Extracted text (may be empty):\n{text[:6000] or '(no readable text)'}\n\n"
                "List only what the text actually shows. Leave lists empty when unsure."
            )
            result = invoke_structured(prompt, EvidenceAnalysis, system=SYSTEM_PROMPT)
            if result is not None:
                analysis = result.model_dump()
        if analysis is None:
            analysis = det.analyse_evidence(text, item.get("evidence_type", "screenshot"))
        item["analysis"] = analysis
    return {"evidence_items": items, "llm_used": llm, "stage": "evidence_analyzed"}


@safe_node("timeline_builder", defaults={"timeline": [], "timeline_gaps": []})
def timeline_builder_node(state: SaakshyaState) -> dict[str, Any]:
    """Merge the story and the evidence into a chronological timeline."""
    timeline, gaps = det.build_timeline(
        story_text(state), state.get("evidence_items") or [], state.get("language", "en")
    )
    return {"timeline": timeline, "timeline_gaps": gaps, "stage": "timeline_built"}


@safe_node("classifier", defaults={"issue_categories": [{"category": "other", "confidence": 0.3}]})
def classifier_node(state: SaakshyaState) -> dict[str, Any]:
    """Classify the situation into one or more issue categories."""
    text = "\n".join([story_text(state), evidence_text(state.get("evidence_items") or [])])
    categories: list[dict[str, Any]] = []
    if llm_available():
        result = invoke_structured(
            "Classify this situation. Categories allowed: domestic_violence, "
            "workplace_sexual_harassment, stalking, cyber_harassment, dowry_related, other. "
            "Use more than one label only when the facts support it.\n\n" + text[:6000],
            ClassifierOutput,
            system=SYSTEM_PROMPT,
        )
        if result is not None:
            categories = [
                {
                    "category": normalise_category(issue.category),
                    "confidence": round(float(issue.confidence), 2),
                }
                for issue in result.issues
            ]
            if result.rationale:
                LOGGER.info("Classifier rationale length=%d", len(result.rationale))
    if not categories:
        categories = det.classify(text)
    return {"issue_categories": categories[:3], "stage": "classified"}


@safe_node("rights_rag", defaults={"legal_matches": []})
def rights_rag_node(state: SaakshyaState) -> dict[str, Any]:
    """Retrieve curated legal entries and attach a citation to each one."""
    kb = get_kb()
    categories = _categories_from_state(state)
    query = "\n".join(
        [
            story_text(state),
            " ".join(categories),
            " ".join(match.get("summary", "") for match in state.get("evidence_items") or []),
            evidence_text(state.get("evidence_items") or ""),
        ]
    )
    hits = kb.search(query, k=MAX_MATCHES, categories=categories)
    matches = [
        {
            **hit.entry.to_dict(),
            "relevance": "Matched on: " + ", ".join(hit.matched_terms[:5]) if hit.matched_terms else "Category match",
            "citation": format_citation(hit.entry),
        }
        for hit in hits
    ]
    for category in categories:
        if not any(category in match.get("categories", []) for match in matches):
            matches.extend(
                {
                    **extra.entry.to_dict(),
                    "relevance": f"Selected for category: {category}",
                    "citation": format_citation(extra.entry),
                }
                for extra in kb.for_categories([category], k=2)
            )
    matches = _dedupe_matches(matches)
    LOGGER.info("Rights retrieval returned %d cited entries", len(matches))
    return {"legal_matches": matches, "stage": "rights_matched"}


@safe_node("action_plan")
def action_plan_node(state: SaakshyaState) -> dict[str, Any]:
    """Produce a prioritised, local-language action plan."""
    language = state.get("language", "en")
    categories = _categories_from_state(state)
    steps: list[dict[str, Any]] = []
    if llm_available():
        prompt = (
            f"Language for the answer: {'Hindi' if language == 'hi' else 'English'}.\n"
            f"Risk level: {state.get('risk_level', 'low')}.\n"
            f"Categories: {', '.join(categories) or 'other'}.\n"
            f"Story:\n{story_text(state)[:4000]}\n\n"
            "Give 4-6 prioritised steps: immediate safety, preserving evidence, who to contact, "
            "documents to carry, free legal aid. Do not invent phone numbers other than "
            "112, 181, 1091, 1930 and 15100. Keep each step under 45 words."
        )
        result = invoke_structured(prompt, ActionPlanOutput, system=SYSTEM_PROMPT)
        if result is not None and len(result.steps) >= 2:
            steps = [step.model_dump() for step in result.steps]
    if not steps:
        steps = det.build_action_plan(state.get("risk_level", "low"), categories, language)
    if state.get("risk_level") == "high" and steps and "112" not in str(steps[0]):
        steps.insert(
            0,
            {
                "priority": 0,
                "title": "अभी सुरक्षा" if language == "hi" else "Safety first, right now",
                "detail": (
                    "112 पर कॉल करें (पुलिस/एम्बुलेंस) और 181 से बात करें। किसी भरोसेमंद व्यक्ति को अभी बताएँ।"
                    if language == "hi"
                    else "Call 112 (police/ambulance) and 181 now. Tell one trusted person immediately."
                ),
                "contact": "112 / 181",
            },
        )
    return {"action_plan": steps, "stage": "plan_ready"}


@safe_node("complaint_drafter", defaults={"draft_text": "", "complaint_draft": {}})
def complaint_drafter_node(state: SaakshyaState) -> dict[str, Any]:
    """Draft the complaint using only supplied facts, with evidence refs and citations."""
    language = state.get("language", "en")
    items = state.get("evidence_items") or []
    matches = state.get("legal_matches") or []
    feedback = []
    verification = state.get("verification") or {}
    if verification and not verification.get("passed", True):
        feedback = list(verification.get("problems") or [])
    draft: dict[str, Any] | None = None

    if llm_available():
        evidence_lines = "\n".join(
            f"- {item.get('label')}: {item.get('evidence_type')} uploaded {str(item.get('uploaded_at'))[:10]}, "
            f"SHA-256 {item.get('sha256')}, text: {(item.get('ocr_text') or item.get('transcript') or '')[:400]}"
            for item in items
        ) or "- (no evidence uploaded yet)"
        citation_lines = "\n".join(f"[{match.get('kb_id')}] {match.get('act')} - {match.get('title')}" for match in matches)
        prompt = (
            f"Language: {'Hindi' if language == 'hi' else 'English'}.\n"
            f"Case title: {state.get('case_title', '')}\n"
            f"Story (the only source of facts):\n{story_text(state)[:5000]}\n\n"
            f"Evidence index:\n{evidence_lines}\n\n"
            f"Citations you may use (cite as [KB-xx], never invent others):\n{citation_lines}\n\n"
            "Write a formal complaint letter addressed to the Station House Officer or the "
            "Protection Officer. Keep every fact traceable to the story or evidence. Reference "
            "evidence as E1, E2 and include the hashes. End with place/date/signature lines and a "
            "line saying the exact sections will be confirmed with a lawyer."
        )
        if feedback:
            prompt += "\nThe previous draft failed these checks, fix them: " + "; ".join(feedback)
        result = invoke_structured(prompt, ComplaintDraft, system=SYSTEM_PROMPT)
        if result is not None and result.body.strip():
            draft = result.model_dump()

    if draft is None:
        draft = det.build_complaint(
            state.get("case_title", "My complaint"),
            story_text(state),
            items,
            state.get("timeline") or [],
            _categories_from_state(state),
            matches,
            language=language,
            feedback=feedback or None,
        )

    draft_text = f"{draft.get('subject', '').strip()}\n\n{draft.get('body', '').strip()}".strip()
    if matches and not det.CITATION_RE.search(draft_text):
        draft_text += "\n\nSources (verify with a lawyer):\n" + "\n".join(
            f"- {match.get('citation') or format_citation_by_id(match)}" for match in matches
        )
    if items and not det.EVIDENCE_REF_RE.search(draft_text):
        draft_text += "\n\nEvidence index:\n" + "\n".join(
            f"- {item.get('label')}: {item.get('filename')} | SHA-256 {item.get('sha256')}"
            for item in items
        )
    draft["draft_text"] = draft_text
    return {"complaint_draft": draft, "draft_text": draft_text, "stage": "draft_ready"}


@safe_node("verifier", defaults={"verification": {"passed": False}, "verify_retries": 0})
def verifier_node(state: SaakshyaState) -> dict[str, Any]:
    """Self-check: citations exist and no date is invented."""
    known = [str(match.get("kb_id")) for match in state.get("legal_matches") or []]
    result = det.verify(state.get("draft_text") or "", corpus(state), known)
    retries = int(state.get("verify_retries") or 0)
    if not result["passed"]:
        retries += 1
        LOGGER.warning("Verifier found %d problem(s) (attempt %d)", len(result["problems"]), retries)
    result["retries"] = retries
    return {
        "verification": result,
        "verify_retries": retries,
        "stage": "verified" if result["passed"] else "verification_failed",
    }


@safe_node("human_review", defaults={"human_approved": False})
def human_review_node(state: SaakshyaState) -> dict[str, Any]:
    """Pause for the survivor's edit + approval (LangGraph interrupt)."""
    payload = {
        "case_id": state.get("case_id", ""),
        "draft_text": state.get("draft_text", ""),
        "verification": state.get("verification", {}),
        "risk_level": state.get("risk_level", "low"),
        "ask": "Review, edit if needed, and approve. Nothing is exported without approval.",
    }
    decision = interrupt(payload)
    if not isinstance(decision, dict):
        decision = {"approved": bool(decision)}
    approved = bool(decision.get("approved"))
    edited = str(decision.get("draft_text") or state.get("draft_text") or "")
    approver = str(decision.get("approver") or "")
    LOGGER.info("Human review decision: approved=%s", approved)
    if approved:
        return {
            "human_approved": True,
            "approved_draft": edited,
            "draft_text": edited,
            "approver": approver,
            "stage": "approved",
        }
    return {
        "human_approved": False,
        "approved_draft": "",
        "approver": approver,
        "stage": "changes_requested",
    }


def format_citation_by_id(match: dict[str, Any]) -> str:
    """Citation line from a rights match dict (no KB lookup needed)."""
    return (
        f"[{match.get('kb_id')}] {match.get('act')} - {match.get('title')} "
        f"(last reviewed {match.get('last_reviewed', '?')}; verify with a lawyer)"
    )


# --------------------------------------------------------------------- routing
def route_after_intake(state: SaakshyaState) -> str:
    """Stop for follow-up answers, otherwise continue to the safety check."""
    return "safety_check" if state.get("intake_complete") else "wait_for_user"


def route_after_verifier(state: SaakshyaState) -> str:
    """Loop back to the drafter on failure, up to ``MAX_VERIFY_RETRIES``."""
    verification = state.get("verification") or {}
    if verification.get("passed"):
        return "human_review"
    retries = int(state.get("verify_retries") or 0)
    return "complaint_drafter" if retries <= MAX_VERIFY_RETRIES else "human_review"
