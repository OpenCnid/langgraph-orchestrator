"""LangGraph state schema for the orchestrator."""

from typing import Any, TypedDict

from src.lib.models import Conclusion, RoutingDecision, SpawnTask


class OrchestratorState(TypedDict, total=False):
    """Top-level state threaded through the orchestrator graph.

    Uses total=False so nodes only need to return the fields they update.
    LangGraph merges partial updates into the full state.
    """

    query: str
    routing_decision: RoutingDecision
    spawn_plan: list[SpawnTask]
    subagent_conclusions: list[Conclusion]
    merged_response: str
    context_digest: str
    memory_log: list[dict[str, Any]]
    human_input: str | None


class SubagentState(TypedDict, total=False):
    """State for an isolated subagent execution.

    Enforces the isolation contract: subagent receives ONLY piece content + inputs,
    returns ONLY a Conclusion. No access to main orchestrator state.
    """

    piece_id: str
    piece_content: str
    inputs: dict[str, Any]
    conclusion: Conclusion
