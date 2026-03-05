"""Tests for recovery — response classification, recovery piece lookup, retry enforcement."""

import hashlib
import json

from src.atlas import Atlas
from src.lib.models import Piece, PieceStatus, PieceType
from src.lib.piece_runner import ExecutionState, execute_piece
from src.lib.response_classifier import ResponseShapeType, classify_response
from src.recovery import _find_recovery_piece, build_recovery_hook


def _deterministic_embed(text: str) -> list[float]:
    h = hashlib.sha256(text.encode()).digest()
    vec: list[float] = []
    for i in range(1536):
        byte_idx = i % len(h)
        bit_idx = i % 8
        val = ((h[byte_idx] >> bit_idx) & 1) * 2.0 - 1.0
        vec.append(val)
    return vec


def _make_recovery_piece(
    piece_id: str = "recovery_validation",
    shapes: list[str] | None = None,
) -> Piece:
    shapes = shapes or ["validation"]
    shapes_str = ", ".join(shapes)
    return Piece(
        id=piece_id,
        title=f"Recovery: {piece_id}",
        type=PieceType.RECOVERY,
        status=PieceStatus.ACTIVE,
        response_shapes_handled=shapes,
        content=(
            f"# Recovery: {piece_id}\n\n"
            f"**Type:** recovery\n"
            f"**Response Shapes Handled:** [{shapes_str}]\n\n"
            "```mermaid\n"
            "graph TD\n"
            "    A[Receive error] --> B[Diagnose]\n"
            "    B --> C[Suggest fix]\n"
            "```\n"
        ),
    )


class TestResponseShapeClassification:
    """Classify tool responses into shape categories."""

    def test_validation_response(self) -> None:
        shape = classify_response("Error: invalid email format in field 'email'")
        assert shape.shape_type == ResponseShapeType.VALIDATION

    def test_partial_response(self) -> None:
        shape = classify_response("Processed 3 of 10 records. Remaining: 7")
        assert shape.shape_type == ResponseShapeType.PARTIAL

    def test_capacity_response(self) -> None:
        shape = classify_response("Rate limit exceeded. Retry after 30 seconds.")
        assert shape.shape_type == ResponseShapeType.CAPACITY

    def test_constraint_response(self) -> None:
        shape = classify_response("403 Forbidden: Permission denied for this resource")
        assert shape.shape_type == ResponseShapeType.CONSTRAINT

    def test_shape_mismatch_response(self) -> None:
        shape = classify_response("Unexpected response format: schema mismatch")
        assert shape.shape_type == ResponseShapeType.SHAPE_MISMATCH

    def test_unknown_response(self) -> None:
        shape = classify_response("Everything is fine, nothing to see here")
        assert shape.shape_type == ResponseShapeType.UNKNOWN

    def test_response_preserves_raw_text(self) -> None:
        raw = "Error 429: Too many requests"
        shape = classify_response(raw)
        assert shape.raw_response == raw

    def test_case_insensitive_matching(self) -> None:
        shape = classify_response("RATE LIMIT EXCEEDED")
        assert shape.shape_type == ResponseShapeType.CAPACITY


class TestRecoveryPieceLookup:
    """Find recovery pieces by response shape."""

    def test_finds_matching_recovery_piece(self) -> None:
        atlas = Atlas(embed_fn=_deterministic_embed)
        recovery = _make_recovery_piece("val_recovery", ["validation"])
        atlas.add_piece(recovery)

        found = _find_recovery_piece(atlas, ResponseShapeType.VALIDATION)
        assert found is not None
        assert found.id == "val_recovery"

    def test_returns_none_for_no_match(self) -> None:
        atlas = Atlas(embed_fn=_deterministic_embed)
        found = _find_recovery_piece(atlas, ResponseShapeType.CAPACITY)
        assert found is None

    def test_skips_archived_recovery_pieces(self) -> None:
        atlas = Atlas(embed_fn=_deterministic_embed)
        recovery = _make_recovery_piece("old_recovery", ["validation"])
        recovery.status = PieceStatus.ARCHIVED
        atlas.add_piece(recovery)

        found = _find_recovery_piece(atlas, ResponseShapeType.VALIDATION)
        assert found is None


class TestRecoveryHook:
    """Recovery hook integration with piece_runner."""

    def test_recovery_hook_returns_guidance(self) -> None:
        atlas = Atlas(embed_fn=_deterministic_embed)
        recovery = _make_recovery_piece("val_recovery", ["validation"])
        atlas.add_piece(recovery)

        def mock_llm(system: str, user: str) -> str:
            return json.dumps({
                "summary": "Correct the email format and retry",
                "status": "partial",
            })

        hook = build_recovery_hook(atlas, mock_llm)
        state = ExecutionState(piece_id="main_piece", inputs={})

        result = hook(state, "Error: invalid email format")
        assert result is not None
        assert "email" in result.summary.lower() or "retry" in result.summary.lower()

    def test_recovery_hook_returns_none_for_unknown_shape(self) -> None:
        atlas = Atlas(embed_fn=_deterministic_embed)

        def mock_llm(system: str, user: str) -> str:
            return json.dumps({"summary": "OK", "status": "success"})

        hook = build_recovery_hook(atlas, mock_llm)
        state = ExecutionState(piece_id="main_piece", inputs={})

        result = hook(state, "Normal successful response data")
        assert result is None

    def test_recovery_hook_returns_none_when_no_recovery_piece(self) -> None:
        atlas = Atlas(embed_fn=_deterministic_embed)

        def mock_llm(system: str, user: str) -> str:
            return json.dumps({"summary": "OK", "status": "success"})

        hook = build_recovery_hook(atlas, mock_llm)
        state = ExecutionState(piece_id="main_piece", inputs={})

        # Validation error but no recovery piece in atlas
        result = hook(state, "Error: invalid field 'email'")
        assert result is None


class TestRetryLimitEnforcement:
    """Retry limits prevent unbounded recovery loops."""

    def test_retry_limit_stops_recovery(self) -> None:
        """Piece runner should stop after max_retries recovery attempts."""
        atlas = Atlas(embed_fn=_deterministic_embed)
        recovery = _make_recovery_piece("val_recovery", ["validation"])
        atlas.add_piece(recovery)

        def always_fail_llm(system: str, user: str) -> str:
            return json.dumps({
                "summary": "Invalid field",
                "status": "failed",
                "diagnostics": "validation error persists",
            })

        hook = build_recovery_hook(atlas, always_fail_llm)

        # Create a forward piece to execute
        piece = Piece(
            id="test_piece",
            title="Test",
            type=PieceType.FORWARD,
            status=PieceStatus.ACTIVE,
            content=(
                "# Test\n\n"
                "```mermaid\ngraph TD\n    A[Start] --> B[End]\n```\n"
            ),
        )

        result = execute_piece(
            piece,
            {},
            llm_fn=always_fail_llm,
            recovery_hook=hook,
            max_retries=2,
        )
        assert result.status == "escalated"
        assert "Retry limit" in result.summary or "exceeded" in (result.diagnostics or "")


class TestRecoveryEndToEnd:
    """End-to-end: failure → classify → recover → retry → success."""

    def test_recovery_then_success(self) -> None:
        atlas = Atlas(embed_fn=_deterministic_embed)
        recovery = _make_recovery_piece("val_recovery", ["validation"])
        atlas.add_piece(recovery)

        call_count = 0

        def improving_llm(system: str, user: str) -> str:
            nonlocal call_count
            call_count += 1
            if call_count <= 2:  # First two calls fail (main + recovery)
                return json.dumps({
                    "summary": "Invalid field error",
                    "status": "failed",
                    "diagnostics": "validation error",
                })
            return json.dumps({
                "summary": "Completed successfully after fix",
                "status": "success",
            })

        # Build recovery hook that uses the same LLM
        hook = build_recovery_hook(atlas, improving_llm)

        piece = Piece(
            id="main_piece",
            title="Main Workflow",
            type=PieceType.FORWARD,
            status=PieceStatus.ACTIVE,
            content=(
                "# Main\n\n"
                "```mermaid\ngraph TD\n    A[Start] --> B[End]\n```\n"
            ),
        )

        result = execute_piece(
            piece,
            {},
            llm_fn=improving_llm,
            recovery_hook=hook,
            max_retries=3,
        )
        # After recovery guidance, the third main attempt should succeed
        assert result.status == "success"
