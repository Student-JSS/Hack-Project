"""Graph construction and the run/resume helpers used by the Streamlit UI.

The graph is compiled once per process. A checkpointer (in memory by default, or
SQLite when ``CHECKPOINT_BACKEND=sqlite``) keeps the state of the paused
``human_review`` node so approval can resume the same thread.
"""

from __future__ import annotations

import sqlite3
from functools import lru_cache
from typing import Any, Callable

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command

from src.config import get_logger, get_settings
from src.graph.nodes import (
    action_plan_node,
    classifier_node,
    complaint_drafter_node,
    evidence_analyzer_node,
    human_review_node,
    intake_node,
    rights_rag_node,
    route_after_intake,
    route_after_verifier,
    safety_check_node,
    timeline_builder_node,
    verifier_node,
)
from src.graph.state import SaakshyaState

LOGGER = get_logger("graph.build")

NODES = {
    "intake": intake_node,
    "safety_check": safety_check_node,
    "evidence_analyzer": evidence_analyzer_node,
    "timeline_builder": timeline_builder_node,
    "classifier": classifier_node,
    "rights_rag": rights_rag_node,
    "action_plan": action_plan_node,
    "complaint_drafter": complaint_drafter_node,
    "verifier": verifier_node,
    "human_review": human_review_node,
}

NODE_ORDER: tuple[str, ...] = tuple(NODES)
NODE_LABELS: dict[str, str] = {
    "intake": "Intake & follow-up questions",
    "safety_check": "Safety check (danger routing)",
    "evidence_analyzer": "Evidence analyzer (OCR text -> facts)",
    "timeline_builder": "Timeline builder",
    "classifier": "Issue classifier",
    "rights_rag": "Rights retrieval (cited KB)",
    "action_plan": "Action plan",
    "complaint_drafter": "Complaint drafter",
    "verifier": "Verifier (citation + fact check)",
    "human_review": "Human review (interrupt: approve to continue)",
}

CHECKPOINTER: Any | None = None


def _checkpointer() -> Any:
    """MemorySaver by default; SqliteSaver when configured and available."""
    global CHECKPOINTER
    if CHECKPOINTER is not None:
        return CHECKPOINTER
    settings = get_settings()
    if settings.checkpoint_backend == "sqlite":
        try:
            from langgraph.checkpoint.sqlite import SqliteSaver

            settings.checkpoint_db_path.parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(str(settings.checkpoint_db_path), check_same_thread=False)
            CHECKPOINTER = SqliteSaver(connection)
            LOGGER.info("Using SQLite checkpointer")
            return CHECKPOINTER
        except Exception as exc:
            LOGGER.warning(
                "SQLite checkpointer unavailable (%s); falling back to memory.", type(exc).__name__
            )
    CHECKPOINTER = InMemorySaver()
    return CHECKPOINTER


def build_graph(checkpointer: Any | None = None) -> Any:
    """Build and compile the StateGraph (accepts an explicit checkpointer)."""
    graph = StateGraph(SaakshyaState)
    for name, node in NODES.items():
        graph.add_node(name, node)

    graph.add_edge(START, "intake")
    graph.add_conditional_edges(
        "intake",
        route_after_intake,
        {"safety_check": "safety_check", "wait_for_user": END},
    )
    graph.add_edge("safety_check", "evidence_analyzer")
    graph.add_edge("evidence_analyzer", "timeline_builder")
    graph.add_edge("timeline_builder", "classifier")
    graph.add_edge("classifier", "rights_rag")
    graph.add_edge("rights_rag", "action_plan")
    graph.add_edge("action_plan", "complaint_drafter")
    graph.add_edge("complaint_drafter", "verifier")
    graph.add_conditional_edges(
        "verifier",
        route_after_verifier,
        {"complaint_drafter": "complaint_drafter", "human_review": "human_review"},
    )
    graph.add_edge("human_review", END)
    return graph.compile(checkpointer=checkpointer or _checkpointer())


@lru_cache(maxsize=1)
def get_graph() -> Any:
    """Compiled graph singleton with the configured checkpointer."""
    LOGGER.info("Compiling the Saakshya graph")
    return build_graph()


def reset_graph() -> None:
    """Clear the compiled graph and the checkpointer (tests)."""
    global CHECKPOINTER
    get_graph.cache_clear()
    CHECKPOINTER = None


def thread_config(case_id: str, run_index: int = 0) -> dict[str, Any]:
    """Config for one analysis run; the interrupt resumes on the same thread."""
    return {
        "configurable": {"thread_id": f"{case_id}:{run_index}"},
        "recursion_limit": 80,
    }


def pending_interrupt(result: dict[str, Any] | None) -> dict[str, Any] | None:
    """Return the interrupt payload attached to a paused run, if any."""
    if not result:
        return None
    interrupts = result.get("__interrupt__") or ()
    for item in interrupts:
        value = item if isinstance(item, dict) else getattr(item, "value", None)
        if isinstance(value, dict):
            return value
    return None


def stream_pipeline(
    state: SaakshyaState | None = None,
    run_index: int = 0,
    on_node: Callable[[str, Any], None] | None = None,
    case_id: str | None = None,
    resume: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run the graph node by node so the UI can show progress.

    Pass ``resume`` to continue a paused ``human_review`` instead of starting a
    new run. Returns the final state with ``__interrupt__`` attached when the
    graph paused for approval.
    """
    app = get_graph()
    cid = case_id or str((state or {}).get("case_id") or "case")
    config = thread_config(cid, run_index)
    inputs: Any = Command(resume=resume) if resume is not None else dict(state or {})
    interrupt_payload: dict[str, Any] | None = None
    for chunk in app.stream(inputs, config, stream_mode="updates"):
        for key, value in chunk.items():
            if key == "__interrupt__":
                for item in value or ():
                    payload = item if isinstance(item, dict) else getattr(item, "value", None)
                    if isinstance(payload, dict):
                        interrupt_payload = payload
                continue
            if on_node is not None:
                on_node(key, value)
    result = dict(app.get_state(config).values)
    if interrupt_payload is not None:
        result["__interrupt__"] = [interrupt_payload]
    return result


def run_pipeline(state: SaakshyaState, run_index: int = 0) -> dict[str, Any]:
    """Run (or re-run) the pipeline for a case until it pauses or completes."""
    app = get_graph()
    case_id = str(state.get("case_id") or "case")
    config = thread_config(case_id, run_index)
    LOGGER.info("Starting pipeline run %s for case %s", run_index, case_id)
    return app.invoke(dict(state), config)


def resume_pipeline(case_id: str, decision: dict[str, Any], run_index: int = 0) -> dict[str, Any]:
    """Resume a paused human_review node with the survivor's decision."""
    app = get_graph()
    config = thread_config(case_id, run_index)
    LOGGER.info("Resuming case %s after human review", case_id)
    return app.invoke(Command(resume=decision), config)


def snapshot(case_id: str, run_index: int = 0) -> Any:
    """Return the LangGraph state snapshot for a thread (debug/UI)."""
    return get_graph().get_state(thread_config(case_id, run_index))


def graph_mermaid() -> str:
    """Mermaid source of the compiled flow (shown in the UI and README)."""
    return """graph TD
    START([start]) --> intake[intake<br/>follow-up questions]
    intake -->|missing info| WAIT([wait for answers])
    intake -->|enough info| safety[safety_check]
    safety -->|risk = high: urgent help banner, keep going| evidence[evidence_analyzer]
    safety -->|risk = low / medium| evidence
    evidence --> timeline[timeline_builder]
    timeline --> classify[classifier]
    classify --> rights[rights_rag<br/>cited KB]
    rights --> plan[action_plan]
    plan --> draft[complaint_drafter]
    draft --> verify{verifier}
    verify -->|failed and retries <= 2| draft
    verify -->|passed or retries exhausted| review[[human_review<br/>interrupt]]
    review -->|approved| END([end])
    review -->|changes requested| END
"""


def graph_node_table() -> list[dict[str, Any]]:
    """Node list for the UI (name, label, short description)."""
    descriptions = {
        "intake": "Reads the story, asks up to 3 questions, loops back through the UI.",
        "safety_check": "Flags immediate danger and shows 112/181/1091/1930 first.",
        "evidence_analyzer": "Pulls dates, senders, threats and quotes out of each item.",
        "timeline_builder": "Merges story + evidence, flags items with no date.",
        "classifier": "Multi-label classification with confidence.",
        "rights_rag": "BM25 retrieval over 13 curated KB entries, each with a citation.",
        "action_plan": "Prioritised steps in her language.",
        "complaint_drafter": "Draft with E1/E2 references and SHA-256 hashes.",
        "verifier": "Checks citations and invented dates; retries the drafter.",
        "human_review": "Interrupt: nothing is exported until she approves.",
    }
    return [
        {"name": name, "label": NODE_LABELS[name], "description": descriptions[name]}
        for name in NODE_ORDER
    ]
