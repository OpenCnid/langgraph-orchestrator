"""Main orchestrator graph — LangGraph StateGraph with mode-based routing."""

import logging
from typing import Any, Literal

from langgraph.graph import END, StateGraph

from src.atlas import Atlas
from src.lib.contradiction import detect_contradictions
from src.lib.models import Conclusion, SpawnTask
from src.lib.piece_runner import LLMCallable, execute_piece
from src.lib.state import OrchestratorState
from src.router import classify_query, reroute_after_clarification

logger = logging.getLogger(__name__)


def route(state: OrchestratorState, *, atlas: Atlas) -> dict[str, Any]:
    """Classify the query and determine which mode to use."""
    query = state["query"]
    human_input = state.get("human_input")

    if human_input:
        decision = reroute_after_clarification(human_input, atlas)
    else:
        decision = classify_query(query, atlas)

    return {"routing_decision": decision}


def route_condition(
    state: OrchestratorState,
) -> Literal["execute_a", "plan_b", "draft_c", "clarify_d"]:
    """Conditional edge: dispatch to the correct mode node based on routing decision."""
    mode = state["routing_decision"].mode
    return {
        "A": "execute_a",
        "B": "plan_b",
        "C": "draft_c",
        "D": "clarify_d",
    }[mode]


def execute_a(
    state: OrchestratorState,
    *,
    atlas: Atlas,
    llm_fn: LLMCallable,
) -> dict[str, Any]:
    """Mode A (Librarian): execute a single matched piece directly via piece_runner."""
    decision = state["routing_decision"]
    piece_match = decision.matched_pieces[0]
    piece = atlas.get_piece(piece_match.piece_id)

    if piece is None:
        conclusion = Conclusion(
            summary=f"Piece {piece_match.piece_id} not found in atlas",
            status="failed",
            diagnostics=f"Piece ID {piece_match.piece_id} was matched but not found",
        )
    else:
        conclusion = execute_piece(
            piece,
            {"query": state["query"]},
            llm_fn=llm_fn,
            atlas=atlas,
        )

    return {
        "subagent_conclusions": [conclusion],
        "merged_response": conclusion.summary,
    }


def plan_b(state: OrchestratorState, *, atlas: Atlas) -> dict[str, Any]:
    """Mode B (Orchestrator): plan multi-piece execution.

    Analyzes matched pieces, determines dependencies (sequential vs parallel).
    Pieces with shared connections are sequential; independent pieces are parallel.
    """
    decision = state["routing_decision"]
    spawn_plan: list[SpawnTask] = []

    # Build piece connection map for dependency analysis
    piece_ids = [m.piece_id for m in decision.matched_pieces]
    for match in decision.matched_pieces:
        piece = atlas.get_piece(match.piece_id)
        if piece is None:
            continue

        # Check if this piece depends on other matched pieces via connections
        deps = [
            conn for conn in piece.connections
            if conn in piece_ids and conn != match.piece_id
        ]

        spawn_plan.append(
            SpawnTask(
                piece_id=match.piece_id,
                inputs={"query": state["query"]},
                dependencies=deps,
            )
        )

    return {"spawn_plan": spawn_plan}


def spawn_b(
    state: OrchestratorState,
    *,
    atlas: Atlas,
    llm_fn: LLMCallable,
) -> dict[str, Any]:
    """Mode B: execute each piece via piece_runner and collect conclusions.

    Executes pieces sequentially, passing prior conclusions as context
    for dependent pieces.
    """
    conclusions: list[Conclusion] = []
    conclusion_map: dict[str, Conclusion] = {}

    for task in state.get("spawn_plan", []):
        piece = atlas.get_piece(task.piece_id)
        if piece is None:
            conclusion = Conclusion(
                summary=f"Piece {task.piece_id} not found",
                status="failed",
                diagnostics=f"Piece {task.piece_id} missing from atlas",
            )
            conclusions.append(conclusion)
            conclusion_map[task.piece_id] = conclusion
            continue

        # Build inputs — include prior conclusions from dependencies
        inputs = dict(task.inputs)
        for dep_id in task.dependencies:
            if dep_id in conclusion_map:
                dep_conclusion = conclusion_map[dep_id]
                inputs[f"dep_{dep_id}_summary"] = dep_conclusion.summary
                inputs[f"dep_{dep_id}_outputs"] = dep_conclusion.key_outputs

        conclusion = execute_piece(
            piece,
            inputs,
            llm_fn=llm_fn,
            atlas=atlas,
        )
        conclusions.append(conclusion)
        conclusion_map[task.piece_id] = conclusion

    return {"subagent_conclusions": conclusions}


def merge_b(state: OrchestratorState) -> dict[str, Any]:
    """Mode B: merge all subagent conclusions into a coherent response.

    Checks for contradictions between conclusions before finalizing.
    """
    conclusions = state.get("subagent_conclusions", [])

    if not conclusions:
        return {"merged_response": "No conclusions to merge."}

    failed = [c for c in conclusions if c.status in ("failed", "escalated")]
    succeeded = [c for c in conclusions if c.status in ("success", "partial")]

    # Check for contradictions among successful conclusions
    contradictions = detect_contradictions(succeeded)

    parts: list[str] = []
    for c in succeeded:
        parts.append(c.summary)

    if contradictions:
        conflict_descriptions = "; ".join(c["description"] for c in contradictions)
        parts.append(f"[CONFLICTS DETECTED: {conflict_descriptions}]")

    if failed:
        parts.append(
            f"({len(failed)} piece(s) failed: "
            + "; ".join(c.diagnostics or c.summary for c in failed)
            + ")"
        )

    return {"merged_response": " | ".join(parts) if parts else "All pieces failed."}


def draft_c(state: OrchestratorState) -> dict[str, Any]:
    """Mode C (Cartographer): no matching piece found — halt and draft.

    Does NOT improvise. Creates a draft description of what a piece would need.
    """
    query = state["query"]
    conclusion = Conclusion(
        summary=f"No matching piece found for query: {query}",
        status="escalated",
        diagnostics=(
            f"Query '{query}' produced no confident matches. "
            "A new piece may need to be created covering this domain."
        ),
    )
    return {
        "subagent_conclusions": [conclusion],
        "merged_response": conclusion.summary,
    }


def clarify_d(state: OrchestratorState) -> dict[str, Any]:
    """Mode D (Clarifier): query is ambiguous — request human clarification."""
    decision = state["routing_decision"]
    prompt = decision.clarification_prompt or (
        "Your query is ambiguous. Could you provide more detail?"
    )
    return {
        "merged_response": prompt,
        "human_input": None,
    }


def build_graph(
    atlas: Atlas,
    llm_fn: LLMCallable | None = None,
) -> StateGraph:
    """Build the orchestrator StateGraph with mode-based routing.

    Args:
        atlas: Piece registry for retrieval and lookup
        llm_fn: LLM callable for piece execution. If None, uses a default
                 that returns the piece title (for testing graph topology only).
    """
    if llm_fn is None:
        def llm_fn(system: str, user: str) -> str:  # type: ignore[misc]
            return '{"summary": "Executed (no LLM configured)", "status": "success"}'

    graph = StateGraph(OrchestratorState)

    # Bind dependencies to nodes via closures
    graph.add_node("route", lambda s: route(s, atlas=atlas))
    graph.add_node(
        "execute_a", lambda s: execute_a(s, atlas=atlas, llm_fn=llm_fn)
    )
    graph.add_node("plan_b", lambda s: plan_b(s, atlas=atlas))
    graph.add_node(
        "spawn_b", lambda s: spawn_b(s, atlas=atlas, llm_fn=llm_fn)
    )
    graph.add_node("merge_b", merge_b)
    graph.add_node("draft_c", draft_c)
    graph.add_node("clarify_d", clarify_d)

    graph.set_entry_point("route")

    graph.add_conditional_edges(
        "route",
        route_condition,
        {
            "execute_a": "execute_a",
            "plan_b": "plan_b",
            "draft_c": "draft_c",
            "clarify_d": "clarify_d",
        },
    )

    graph.add_edge("execute_a", END)
    graph.add_edge("plan_b", "spawn_b")
    graph.add_edge("spawn_b", "merge_b")
    graph.add_edge("merge_b", END)
    graph.add_edge("draft_c", END)
    graph.add_edge("clarify_d", END)

    return graph
