"""Piece execution engine — loads pieces, interprets workflows, returns conclusions.

The engine treats the LLM as the workflow interpreter: piece content (mermaid diagram
+ prose) is injected into context, and the LLM follows the workflow step by step.
The LLM callable is injectable for testability.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from src.atlas import Atlas
from src.lib.models import Conclusion, Piece, PieceStatus, PieceType
from src.lib.piece_parser import _extract_mermaid, _extract_prose

logger = logging.getLogger(__name__)

# Type for the LLM callable: takes a system prompt and user prompt, returns text
LLMCallable = Callable[[str, str], str]

# Type for recovery hook: receives piece, execution state, response → optional Conclusion
RecoveryHook = Callable[["ExecutionState", str], Conclusion | None]


@dataclass
class ExecutionState:
    """Per-execution state — fully isolated, not shared between concurrent executions."""

    piece_id: str
    inputs: dict[str, Any]
    node_outputs: dict[str, Any] = field(default_factory=dict)
    current_node: str = ""
    execution_trace: list[str] = field(default_factory=list)
    error_state: dict[str, Any] | None = None
    skills_loaded: list[str] = field(default_factory=list)


def validate_piece(piece: Piece) -> None:
    """Validate a piece is executable. Raises ValueError if not.

    - Must be active status (draft/archived rejected at load time)
    - Forward/recovery pieces must have a mermaid diagram
    """
    if piece.status != PieceStatus.ACTIVE:
        raise ValueError(
            f"Piece '{piece.id}' has status '{piece.status}' — "
            f"only active pieces can be executed"
        )
    if piece.type != PieceType.SKILL and _extract_mermaid(piece.content) is None:
        raise ValueError(f"Piece '{piece.id}' has no mermaid diagram")


def load_piece_components(piece: Piece) -> dict[str, Any]:
    """Parse a piece into its executable components.

    Returns dict with:
    - mermaid: the mermaid diagram text (None for skills)
    - prose: surrounding markdown text
    - metadata: piece metadata dict
    - full_content: the complete piece content
    """
    mermaid = _extract_mermaid(piece.content)
    prose = _extract_prose(piece.content)

    return {
        "mermaid": mermaid,
        "prose": prose,
        "metadata": {
            "id": piece.id,
            "type": str(piece.type),
            "title": piece.title,
            "connections": piece.connections,
            "response_shapes_handled": piece.response_shapes_handled,
        },
        "full_content": piece.content,
    }


def _build_system_prompt(components: dict[str, Any], skills_context: str = "") -> str:
    """Build the system prompt for LLM workflow interpretation."""
    parts = [
        "You are executing a workflow defined by the following piece.",
        "Follow the mermaid diagram step by step. At each node, determine the action",
        "and follow the appropriate edge based on conditions.",
        "",
        "## Piece Content",
        components["full_content"],
    ]

    if skills_context:
        parts.extend([
            "",
            "## Loaded Skills (for decision nodes only)",
            skills_context,
        ])

    parts.extend([
        "",
        "## Output Format",
        "Respond with a JSON object containing:",
        '- "summary": a concise natural-language finding',
        '- "status": one of "success", "partial", "failed", "escalated"',
        '- "key_outputs": a dict of named values (keep minimal)',
        '- "diagnostics": null on success, or a description of what went wrong',
    ])

    return "\n".join(parts)


def _build_user_prompt(inputs: dict[str, Any]) -> str:
    """Build the user prompt with execution inputs."""
    if not inputs:
        return "Execute the workflow with no specific inputs."
    parts = ["Execute the workflow with these inputs:"]
    for key, value in inputs.items():
        parts.append(f"- {key}: {value}")
    return "\n".join(parts)


def _parse_llm_conclusion(llm_output: str, piece_id: str) -> Conclusion:
    """Parse LLM output into a Conclusion.

    Tries JSON parsing first, falls back to treating output as summary text.
    """
    import json

    try:
        data = json.loads(llm_output)
        return Conclusion(
            summary=data.get("summary", llm_output),
            status=data.get("status", "success"),
            key_outputs=data.get("key_outputs", {}),
            diagnostics=data.get("diagnostics"),
        )
    except (json.JSONDecodeError, KeyError):
        # Fall back: treat the entire output as the summary
        return Conclusion(
            summary=llm_output,
            status="success",
            key_outputs={"piece_id": piece_id},
        )


def load_skills_for_decision(
    piece: Piece,
    atlas: Atlas | None,
) -> str:
    """Load relevant skills from the atlas for LLM-bridged decision nodes.

    Skills are scoped: loaded for the decision, then unloaded after.
    Returns the combined skill content as a string.
    """
    if atlas is None:
        return ""

    # Find skills connected to this piece
    skill_contents: list[str] = []
    for conn_id in piece.connections:
        conn_piece = atlas.get_piece(conn_id)
        if (
            conn_piece
            and conn_piece.type == PieceType.SKILL
            and conn_piece.status == PieceStatus.ACTIVE
        ):
            skill_contents.append(
                f"### Skill: {conn_piece.title}\n{conn_piece.content}"
            )

    # Also search for skills matching the piece title
    if not skill_contents:
        skill_matches = atlas.search(piece.title, top_k=3, piece_type=PieceType.SKILL)
        for match in skill_matches:
            skill_piece = atlas.get_piece(match.piece_id)
            if skill_piece and skill_piece.status == PieceStatus.ACTIVE:
                skill_contents.append(
                    f"### Skill: {skill_piece.title}\n{skill_piece.content}"
                )

    return "\n\n".join(skill_contents)


def execute_piece(
    piece: Piece,
    inputs: dict[str, Any],
    *,
    llm_fn: LLMCallable,
    atlas: Atlas | None = None,
    recovery_hook: RecoveryHook | None = None,
    max_retries: int = 3,
) -> Conclusion:
    """Execute a piece workflow and return a Conclusion.

    This is the main entry point for the piece execution engine.

    Args:
        piece: The piece to execute (must be active)
        inputs: Input dict for the workflow
        llm_fn: Callable that takes (system_prompt, user_prompt) and returns text
        atlas: Optional atlas for skill loading
        recovery_hook: Optional hook for recovery on unexpected responses
        max_retries: Max recovery loop iterations before escalating
    """
    # Validate
    validate_piece(piece)

    # Load components
    components = load_piece_components(piece)

    # Create execution state
    state = ExecutionState(piece_id=piece.id, inputs=inputs)

    # Load skills for LLM-bridged decisions
    skills_context = ""
    if atlas:
        skills_context = load_skills_for_decision(piece, atlas)
        if skills_context:
            state.skills_loaded = [
                conn_id for conn_id in piece.connections
                if atlas.get_piece(conn_id) and atlas.get_piece(conn_id).type == PieceType.SKILL  # type: ignore[union-attr]
            ]

    # Build prompts
    system_prompt = _build_system_prompt(components, skills_context)
    user_prompt = _build_user_prompt(inputs)

    # Execute via LLM
    retries = 0
    while retries <= max_retries:
        state.execution_trace.append(f"attempt_{retries}")

        try:
            llm_output = llm_fn(system_prompt, user_prompt)
        except Exception as e:
            logger.error("LLM call failed for piece %s: %s", piece.id, e)
            return Conclusion(
                summary=f"LLM execution failed for piece {piece.id}",
                status="failed",
                diagnostics=str(e),
            )

        conclusion = _parse_llm_conclusion(llm_output, piece.id)

        # Post-execution recovery hook
        if recovery_hook and conclusion.status in ("failed", "escalated"):
            recovery_result = recovery_hook(state, llm_output)
            if recovery_result is not None:
                retries += 1
                if retries > max_retries:
                    return Conclusion(
                        summary=f"Retry limit ({max_retries}) exceeded for piece {piece.id}",
                        status="escalated",
                        diagnostics=(
                            f"Recovery attempted {retries} times. "
                            f"Last error: {conclusion.diagnostics}"
                        ),
                    )
                # Recovery says try again — update user prompt with recovery guidance
                user_prompt = (
                    f"Previous attempt failed: {conclusion.diagnostics}. "
                    f"Recovery guidance: {recovery_result.summary}. "
                    f"Please retry the workflow."
                )
                continue

        # No recovery needed or no hook — return result
        return conclusion

    # Should not reach here, but safety net
    return Conclusion(
        summary=f"Execution of piece {piece.id} completed with retries exhausted",
        status="escalated",
        diagnostics=f"Max retries ({max_retries}) reached",
    )
