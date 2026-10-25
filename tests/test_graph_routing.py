"""Graph behaviour: routing, follow-up loop, danger banner, human approval."""

from __future__ import annotations

import re
from pathlib import Path

from PIL import Image

from src import db
from src.graph.build import NODE_ORDER, build_graph, pending_interrupt, resume_pipeline, run_pipeline
from src.graph.deterministic import detect_danger, verify
from src.graph.nodes import route_after_intake, route_after_verifier
from src.graph.state import empty_state, normalise_category
from src.ingest import ingest_bytes

DANGEROUS_STORY = (
    "My husband hit me on 5 March 2026 and threatened to kill me if I leave. "
    "He also sends messages every night."
)


def _state_for(case: dict, **overrides):
    state = empty_state()
    state.update(
        {
            "case_id": case["id"],
            "case_title": case["title"],
            "user_story": case["user_story"],
            "language": case.get("language", "en"),
        }
    )
    state.update(overrides)
    return state


def test_node_list_is_complete() -> None:
    assert len(NODE_ORDER) == 10
    compiled = build_graph()
    graph_nodes = set(compiled.get_graph().nodes)
    assert set(NODE_ORDER).issubset(graph_nodes)


def test_routing_helpers() -> None:
    assert route_after_intake({"intake_complete": True}) == "safety_check"
    assert route_after_intake({"intake_complete": False}) == "wait_for_user"
    assert route_after_verifier({"verification": {"passed": True}}) == "human_review"
    assert (
        route_after_verifier({"verification": {"passed": False}, "verify_retries": 1})
        == "complaint_drafter"
    )
    assert (
        route_after_verifier({"verification": {"passed": False}, "verify_retries": 3})
        == "human_review"
    )


def test_danger_detection_and_banner() -> None:
    assert detect_danger("He threatened to kill me")[0] == "high"
    assert detect_danger("My neighbour says hello every morning")[0] == "low"
    case = db.create_case("Danger case", DANGEROUS_STORY, "en")
    result = run_pipeline(_state_for(case), run_index=1)
    assert result["risk_level"] == "high"
    assert any("112" in line for line in result["urgent_help"])
    assert pending_interrupt(result) is not None


def test_pipeline_drafts_with_citations_and_evidence_refs(tmp_path: Path) -> None:
    case = db.create_case("Evidence case", DANGEROUS_STORY, "en")
    image = tmp_path / "chat.png"
    Image.new("RGB", (200, 160), (240, 240, 245)).save(image)
    row = ingest_bytes(
        case["id"],
        image.read_bytes(),
        "chat.png",
        "screenshot",
        note="Messages from 5 March 2026: 'you will regret this'",
    )
    evidence = [dict(item) for item in db.list_evidence(case["id"])]
    result = run_pipeline(_state_for(case, evidence_items=evidence), run_index=1)
    draft = result["draft_text"]
    assert re.search(r"\[KB-\d+\]", draft)
    assert row["label"] in draft
    assert result["verification"]["passed"] is True
    assert pending_interrupt(result)["draft_text"] == draft


def test_followup_loop_asks_then_continues() -> None:
    case = db.create_case("Short story", "He troubles me.", "en")
    first = run_pipeline(_state_for(case), run_index=1)
    assert first["stage"] == "intake_questions"
    assert 1 <= len(first["followup_questions"]) <= 3
    assert pending_interrupt(first) is None

    answered = _state_for(
        case,
        followup_answers=[
            "My husband threatens me at home.",
            "It happened on 5 March 2026.",
            "I am afraid he will hurt me.",
        ],
        followup_round=2,
        intake_complete=True,
    )
    second = run_pipeline(answered, run_index=2)
    assert second["stage"] != "intake_questions"
    assert second["risk_level"] in {"medium", "high"}
    assert pending_interrupt(second) is not None


def test_interrupt_blocks_export_until_approved() -> None:
    case = db.create_case("Approval case", DANGEROUS_STORY, "en")
    result = run_pipeline(_state_for(case), run_index=1)
    assert result.get("human_approved") is False
    assert db.get_approval(case["id"]) is None

    resumed = resume_pipeline(
        case["id"],
        {"approved": True, "draft_text": "Edited by the survivor [KB-01]", "approver": "Tester"},
        run_index=1,
    )
    assert resumed["human_approved"] is True
    assert resumed["approved_draft"].startswith("Edited by the survivor")


def test_rejection_keeps_draft_unapproved() -> None:
    case = db.create_case("Reject case", DANGEROUS_STORY, "en")
    run_pipeline(_state_for(case), run_index=1)
    resumed = resume_pipeline(case["id"], {"approved": False}, run_index=1)
    assert resumed["human_approved"] is False
    assert resumed["stage"] == "changes_requested"


def test_verifier_detects_missing_and_invented_citations() -> None:
    passed = verify("Complaint citing [KB-01].", "story without dates", ["KB-01"])
    assert passed["passed"]
    assert not passed["problems"]

    uncited = verify("Complaint with no source.", "story", ["KB-01"])
    assert not uncited["passed"]
    assert any("cite" in problem for problem in uncited["problems"])

    unknown = verify("Complaint citing [KB-99].", "story", ["KB-01"])
    assert unknown["missing_citations"] == ["KB-99"]

    invented = verify("On 2026-01-01 [KB-01].", "story with no dates", ["KB-01"])
    assert invented["unsupported_facts"] == ["2026-01-01"]


def test_categories_are_normalised() -> None:
    assert normalise_category("Cyber Harassment") == "cyber_harassment"
    assert normalise_category("posh") == "workplace_sexual_harassment"
    assert normalise_category("something odd") == "other"
