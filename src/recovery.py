"""Recovery executor — classifies unexpected responses and routes to recovery pieces.

Integrates with piece_runner's recovery hooks. When a tool returns something
unexpected, the recovery system:
1. Classifies the response shape
2. Looks up a matching recovery piece in the atlas
3. Executes the recovery piece
4. Returns guidance for the forward loop to retry

If no recovery piece exists, triggers Mode C behavior (draft diagnostic).
"""

import logging

from src.atlas import Atlas
from src.lib.models import Conclusion, Piece, PieceStatus, PieceType
from src.lib.piece_runner import ExecutionState, LLMCallable, execute_piece
from src.lib.response_classifier import ResponseShapeType, classify_response

logger = logging.getLogger(__name__)


def build_recovery_hook(
    atlas: Atlas,
    llm_fn: LLMCallable,
    max_retries: int = 3,
) -> callable:
    """Build a recovery hook function for use with piece_runner.

    The returned function matches the RecoveryHook signature:
    (ExecutionState, str) -> Conclusion | None

    Returns Conclusion with recovery guidance if a matching piece is found,
    or None to let the failure pass through without recovery.
    """

    def recovery_hook(state: ExecutionState, llm_output: str) -> Conclusion | None:
        # Classify the response shape
        shape = classify_response(llm_output)
        logger.info(
            "Recovery: piece=%s shape=%s", state.piece_id, shape.shape_type
        )

        if shape.shape_type == ResponseShapeType.UNKNOWN:
            # No known shape — draft a diagnostic (Mode C within recovery)
            logger.info(
                "Unknown response shape for piece %s — drafting diagnostic",
                state.piece_id,
            )
            return None  # Let failure pass through — caller should escalate

        # Look up a matching recovery piece by response shape
        recovery_piece = _find_recovery_piece(atlas, shape.shape_type)

        if recovery_piece is None:
            logger.info(
                "No recovery piece for shape %s — escalating",
                shape.shape_type,
            )
            return None

        # Execute the recovery piece to get guidance
        recovery_conclusion = execute_piece(
            recovery_piece,
            {
                "original_piece_id": state.piece_id,
                "response_shape": shape.shape_type.value,
                "response_description": shape.description,
                "raw_response": shape.raw_response,
            },
            llm_fn=llm_fn,
            atlas=atlas,
        )

        return recovery_conclusion

    return recovery_hook


def _find_recovery_piece(
    atlas: Atlas,
    shape_type: ResponseShapeType,
) -> Piece | None:
    """Find a recovery piece that handles the given response shape."""
    recovery_pieces = atlas.list_pieces(
        piece_type=PieceType.RECOVERY,
        status=PieceStatus.ACTIVE,
    )

    for piece in recovery_pieces:
        if shape_type.value in piece.response_shapes_handled:
            return piece

    # Fall back to search by shape type name
    matches = atlas.search(
        shape_type.value,
        top_k=3,
        piece_type=PieceType.RECOVERY,
    )
    for match in matches:
        piece = atlas.get_piece(match.piece_id)
        if piece and piece.status == PieceStatus.ACTIVE:
            return piece

    return None


def create_recovery_conclusion(
    piece_id: str,
    shape_type: str,
    diagnostics: str,
) -> Conclusion:
    """Create an escalated conclusion when recovery fails or is unavailable."""
    return Conclusion(
        summary=f"Recovery failed for piece {piece_id}: {shape_type}",
        status="escalated",
        key_outputs={"piece_id": piece_id, "shape_type": shape_type},
        diagnostics=diagnostics,
    )
