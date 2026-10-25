"""Typed state and structured-output schemas for the agent pipeline.

``SaakshyaState`` is a ``TypedDict`` because LangGraph merges partial updates by
key. The Pydantic models are what nodes ask the LLM for (and what they validate
fallback output against), so a malformed model reply can never corrupt state.
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, Literal, TypedDict

from pydantic import BaseModel, Field

CATEGORIES: tuple[str, ...] = (
    "domestic_violence",
    "workplace_sexual_harassment",
    "stalking",
    "cyber_harassment",
    "dowry_related",
    "other",
)

RiskLevel = Literal["low", "medium", "high"]


# --------------------------------------------------------------- Pydantic I/O
class EvidenceAnalysis(BaseModel):
    """What the analyzer extracts from one screenshot/photo/note."""

    summary: str = Field(default="", description="One-line description of the item")
    dates: list[str] = Field(default_factory=list, description="Dates visible or stated")
    senders: list[str] = Field(default_factory=list, description="Names or handles who sent the messages")
    threats: list[str] = Field(default_factory=list, description="Threatening phrases, quoted")
    key_quotes: list[str] = Field(default_factory=list, description="Short exact quotes")
    people: list[str] = Field(default_factory=list, description="Other people named")


class IssueCategory(BaseModel):
    """One label with a confidence score."""

    category: str = Field(description="one of: " + ", ".join(CATEGORIES))
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class ClassifierOutput(BaseModel):
    """Multi-label classification result."""

    issues: list[IssueCategory] = Field(default_factory=list)
    rationale: str = ""


class ActionStep(BaseModel):
    """One prioritised action for the plan tab."""

    priority: int = 1
    title: str = ""
    detail: str = ""
    contact: str = ""


class ActionPlanOutput(BaseModel):
    """Wrapper so the LLM returns a list under a key."""

    steps: list[ActionStep] = Field(default_factory=list)


class ComplaintDraft(BaseModel):
    """Structured complaint, always grounded in supplied facts."""

    subject: str
    body: str
    evidence_refs: list[str] = Field(default_factory=list)
    citations: list[str] = Field(default_factory=list)


# ------------------------------------------------------------------- state
class EvidenceItemState(TypedDict, total=False):
    """Evidence as it travels through the graph."""

    id: str
    label: str
    filename: str
    evidence_type: str
    resource_type: str
    public_id: str
    sha256: str
    version: int | None
    num_bytes: int | None
    etag: str | None
    uploaded_at: str
    ocr_text: str
    ocr_method: str
    transcript: str
    thumbnail_url: str
    analysis: dict[str, Any]


class SaakshyaState(TypedDict, total=False):
    """The full graph state (every node returns a partial update)."""

    case_id: str
    case_title: str
    user_story: str
    language: str
    evidence_items: list[EvidenceItemState]
    timeline: list[dict[str, Any]]
    timeline_gaps: list[str]
    issue_categories: list[dict[str, Any]]
    risk_level: str
    risky_signals: list[str]
    urgent_help: list[str]
    legal_matches: list[dict[str, Any]]
    action_plan: list[dict[str, Any]]
    complaint_draft: dict[str, Any]
    draft_text: str
    human_approved: bool
    approved_draft: str
    approver: str
    followup_questions: list[str]
    followup_answers: list[str]
    followup_round: int
    intake_complete: bool
    verification: dict[str, Any]
    verify_retries: int
    stage: str
    llm_used: bool
    errors: Annotated[list[str], operator.add]


def empty_state() -> SaakshyaState:
    """Return a fully-populated empty state (useful for tests and the UI)."""
    return {
        "case_id": "",
        "case_title": "",
        "user_story": "",
        "language": "en",
        "evidence_items": [],
        "timeline": [],
        "timeline_gaps": [],
        "issue_categories": [],
        "risk_level": "low",
        "risky_signals": [],
        "urgent_help": [],
        "legal_matches": [],
        "action_plan": [],
        "complaint_draft": {},
        "draft_text": "",
        "human_approved": False,
        "approved_draft": "",
        "approver": "",
        "followup_questions": [],
        "followup_answers": [],
        "followup_round": 0,
        "intake_complete": False,
        "verification": {},
        "verify_retries": 0,
        "stage": "new",
        "llm_used": False,
        "errors": [],
    }


def normalise_category(value: str) -> str:
    """Map a free-text category to one of :data:`CATEGORIES`."""
    cleaned = (value or "").strip().lower().replace("-", "_").replace(" ", "_")
    if cleaned in CATEGORIES:
        return cleaned
    aliases = {
        "domestic": "domestic_violence",
        "dv": "domestic_violence",
        "sexual_harassment": "workplace_sexual_harassment",
        "workplace": "workplace_sexual_harassment",
        "posh": "workplace_sexual_harassment",
        "cyber": "cyber_harassment",
        "online_harassment": "cyber_harassment",
        "image_based_abuse": "cyber_harassment",
        "dowry": "dowry_related",
        "stalking_following": "stalking",
        "harassment": "other",
    }
    return aliases.get(cleaned, "other")
