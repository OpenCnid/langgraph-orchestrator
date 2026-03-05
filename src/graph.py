"""Main orchestrator graph — LangGraph StateGraph with mode-based routing."""

import logging
from typing import Any, Literal

from langgraph.graph import END, StateGraph

from src.atlas import Atlas
from src.lib.models import Conclusion, SpawnTask
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


def execute_a(state: OrchestratorState, *, atlas: Atlas) -> dict[str, Any]:
    """Mode A (Librarian): execute a single matched piece directly.

    Full piece execution via piece_runner is wired in P6/P7.
    """
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
        # P7 will wire full piece execution here via piece_runner
        conclusion = Conclusion(
            summary=f"Executed piece: {piece.title}",
            status="success",
            key_outputs={"piece_id": piece.id, "piece_type": str(piece.type)},
        )

    return {
        "subagent_conclusions": [conclusion],
        "merged_response": conclusion.summary,
    }


def plan_b(state: OrchestratorState, *, atlas: Atlas) -> dict[str, Any]:
    """Mode B (Orchestrator): plan multi-piece execution.

    Analyzes matched pieces and determines dependencies.
    Full planner logic in P8.
    """
    decision = state["routing_decision"]
    spawn_plan: list[SpawnTask] = []

    for match in decision.matched_pieces:
        piece = atlas.get_piece(match.piece_id)
        if piece is None:
            continue
        spawn_plan.append(
            SpawnTask(
                piece_id=match.piece_id,
                inputs={"query": state["query"]},
            )
        )

    return {"spawn_plan": spawn_plan}


def spawn_b(state: OrchestratorState, *, atlas: Atlas) -> dict[str, Any]:
    """Mode B: spawn subagents per piece and collect conclusions.

    P8 will use LangGraph Send() for true parallel fan-out.
    """
    conclusions: list[Conclusion] = []

    for task in state.get("spawn_plan", []):
        piece = atlas.get_piece(task.piece_id)
        if piece is None:
            conclusions.append(
                Conclusion(
                    summary=f"Piece {task.piece_id} not found",
                    status="failed",
                    diagnostics=f"Piece {task.piece_id} missing from atlas",
                )
            )
            continue

        # P8 will execute each piece in an isolated subgraph
        conclusions.append(
            Conclusion(
                summary=f"Executed piece: {piece.title}",
                status="success",
                key_outputs={"piece_id": piece.id},
            )
        )

    return {"subagent_conclusions": conclusions}


def merge_b(state: OrchestratorState) -> dict[str, Any]:
    """Mode B: merge all subagent conclusions into a coherent response.

    P8 will add contradiction detection and partial failure handling.
    """
    conclusions = state.get("subagent_conclusions", [])

    if not conclusions:
        return {"merged_response": "No conclusions to merge."}

    failed = [c for c in conclusions if c.status in ("failed", "escalated")]
    succeeded = [c for c in conclusions if c.status in ("success", "partial")]

    parts: list[str] = []
    for c in succeeded:
        parts.append(c.summary)

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
    P9 will save the draft to atlas.
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
    """Mode D (Clarifier): query is ambiguous — request human clarification.

    Returns the clarification prompt. P10 will wire LangGraph interrupt
    for actual human-in-the-loop.
    """
    decision = state["routing_decision"]
    prompt = decision.clarification_prompt or (
        "Your query is ambiguous. Could you provide more detail?"
    )
    return {
        "merged_response": prompt,
        "human_input": None,  # awaiting human response
    }


def build_graph(atlas: Atlas) -> StateGraph:
    """Build the orchestrator StateGraph with mode-based routing.

    The atlas is injected via closure so nodes can access it without
    it being in the state (it's infrastructure, not workflow data).
    """
    graph = StateGraph(OrchestratorState)

    # Bind atlas to nodes that need it
    graph.add_node("route", lambda s: route(s, atlas=atlas))
    graph.add_node("execute_a", lambda s: execute_a(s, atlas=atlas))
    graph.add_node("plan_b", lambda s: plan_b(s, atlas=atlas))
    graph.add_node("spawn_b", lambda s: spawn_b(s, atlas=atlas))
    graph.add_node("merge_b", merge_b)
    graph.add_node("draft_c", draft_c)
    graph.add_node("clarify_d", clarify_d)

    # Entry point
    graph.set_entry_point("route")

    # Conditional routing from route node
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

    # Mode A: execute → end
    graph.add_edge("execute_a", END)

    # Mode B: plan → spawn → merge → end
    graph.add_edge("plan_b", "spawn_b")
    graph.add_edge("spawn_b", "merge_b")
    graph.add_edge("merge_b", END)

    # Mode C: draft → end
    graph.add_edge("draft_c", END)

    # Mode D: clarify → end (human provides input, then re-invoked)
    graph.add_edge("clarify_d", END)

    return graph
