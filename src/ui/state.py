"""Session/DB glue between Streamlit and the LangGraph pipeline."""

from __future__ import annotations

from typing import Any

import streamlit as st

from src import db
from src.config import get_settings
from src.graph.build import NODE_LABELS, pending_interrupt, stream_pipeline
from src.graph.nodes import MAX_FOLLOWUP_ROUNDS
from src.graph.state import empty_state
from src.i18n import t

EVIDENCE_STATE_KEYS = (
    "id",
    "label",
    "filename",
    "evidence_type",
    "resource_type",
    "public_id",
    "sha256",
    "version",
    "num_bytes",
    "etag",
    "uploaded_at",
    "ocr_text",
    "ocr_method",
    "transcript",
    "thumbnail_url",
)


def evidence_to_state(row: dict[str, Any]) -> dict[str, Any]:
    """Trim a DB evidence row to the keys the graph needs."""
    return {key: row.get(key) for key in EVIDENCE_STATE_KEYS}


def build_initial_state(case: dict[str, Any], answers: list[str] | None = None) -> dict[str, Any]:
    """Build a fresh graph state from the stored case and its evidence."""
    stored_answers = list(case.get("followup_answers") or [])
    if answers:
        stored_answers.extend(answers)
    evidence = [evidence_to_state(row) for row in db.list_evidence(case["id"])]
    state = empty_state()
    state.update(
        {
            "case_id": case["id"],
            "case_title": case.get("title", ""),
            "user_story": case.get("user_story", ""),
            "language": case.get("language", "en"),
            "evidence_items": evidence,
            "followup_answers": stored_answers,
            # One bounded round of questions: once she has answered, do not ask again.
            "followup_round": MAX_FOLLOWUP_ROUNDS if stored_answers else 0,
            "intake_complete": bool(stored_answers),
        }
    )
    return state


def run_with_progress(
    state: dict[str, Any] | None,
    run_index: int,
    lang: str,
    resume: dict[str, Any] | None = None,
    case_id: str | None = None,
) -> dict[str, Any]:
    """Stream the graph while showing every node in an ``st.status`` block."""
    started = state or {}
    label = f"{t('agent_running', lang)}…"
    with st.status(label, expanded=True) as status:
        completed: list[str] = []

        def on_node(name: str, _update: Any) -> None:
            completed.append(name)
            st.write(f"✅ {NODE_LABELS.get(name, name)}")

        result = stream_pipeline(
            state=started if resume is None else None,
            run_index=run_index,
            on_node=on_node,
            case_id=case_id or str(started.get("case_id") or ""),
            resume=resume,
        )
        paused = pending_interrupt(result) is not None
        status.update(
            label=t("agent_paused", lang) if paused else t("agent_finished", lang),
            state="complete",
            expanded=False,
        )
    st.session_state["last_nodes"] = completed
    return result


def persist_run(case_id: str, result: dict[str, Any]) -> None:
    """Write the analysis results to SQLite (never the approval flag)."""
    verification = result.get("verification") or {}
    draft = result.get("approved_draft") or result.get("draft_text") or ""
    db.update_case(
        case_id,
        risk_level=result.get("risk_level"),
        issue_categories=result.get("issue_categories") or [],
        timeline=result.get("timeline") or [],
        timeline_gaps=result.get("timeline_gaps") or [],
        action_plan=result.get("action_plan") or [],
        legal_matches=result.get("legal_matches") or [],
        draft_text=draft or None,
        verifier_status=("passed" if verification.get("passed") else "flagged")
        if verification
        else None,
    )


def store_run(case_id: str, run_index: int, result: dict[str, Any]) -> None:
    """Keep the latest run in the session so tabs can render it."""
    st.session_state["run"] = {
        "case_id": case_id,
        "run_index": run_index,
        "state": result,
    }
    persist_run(case_id, result)


def current_run(case_id: str) -> dict[str, Any]:
    """Return the session run for ``case_id`` (empty state when none)."""
    run = st.session_state.get("run") or {}
    if run.get("case_id") != case_id:
        return {"case_id": case_id, "run_index": 0, "state": empty_state()}
    return run


def clear_run() -> None:
    """Forget the current run (used when the story or evidence changes)."""
    st.session_state.pop("run", None)
    st.session_state.pop("last_nodes", None)
    st.session_state.pop("pdf_bytes", None)


def next_run_index(case_id: str) -> int:
    """Increment the per-case run counter (each run gets its own thread)."""
    key = f"run_index::{case_id}"
    value = int(st.session_state.get(key, 0)) + 1
    st.session_state[key] = value
    return value


def app_status(lang: str) -> dict[str, str]:
    """Short status strings for the sidebar."""
    settings = get_settings()
    from src.llm import provider_label

    return {
        "llm": provider_label(),
        "storage": "mock (offline)" if settings.use_mock_cloudinary else "Cloudinary (authenticated)",
        "ocr": "add-on enabled" if settings.cloudinary_ocr_enabled else "LLM fallback",
        "tracing": "LangSmith on" if settings.langsmith_tracing else "tracing off",
    }
