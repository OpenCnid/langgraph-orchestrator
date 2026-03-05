"""Tests for data models — P2."""

from src.lib.models import (
    Conclusion,
    Piece,
    PieceMatch,
    PieceMetadata,
    PieceStatus,
    PieceType,
    RoutingDecision,
    SpawnTask,
)


class TestPieceType:
    def test_enum_values(self) -> None:
        assert PieceType.FORWARD == "forward"
        assert PieceType.RECOVERY == "recovery"
        assert PieceType.SKILL == "skill"


class TestPieceStatus:
    def test_enum_values(self) -> None:
        assert PieceStatus.ACTIVE == "active"
        assert PieceStatus.ARCHIVED == "archived"
        assert PieceStatus.DRAFT == "draft"


class TestPiece:
    def test_minimal_piece(self) -> None:
        p = Piece(id="test", type=PieceType.FORWARD)
        assert p.id == "test"
        assert p.type == PieceType.FORWARD
        assert p.status == PieceStatus.ACTIVE
        assert p.connections == []
        assert p.response_shapes_handled == []
        assert p.content == ""

    def test_full_piece(self) -> None:
        meta = PieceMetadata(
            type=PieceType.RECOVERY,
            connections=["other_piece"],
            response_shapes_handled=["404", "empty"],
            status=PieceStatus.ACTIVE,
        )
        p = Piece(
            id="recovery_1",
            compact_identifier="❌",
            title="Not Found Recovery",
            type=PieceType.RECOVERY,
            status=PieceStatus.ACTIVE,
            connections=["other_piece"],
            response_shapes_handled=["404", "empty"],
            content="# Recovery piece",
            metadata=meta,
        )
        assert p.compact_identifier == "❌"
        assert p.response_shapes_handled == ["404", "empty"]
        assert p.metadata is not None
        assert p.metadata.type == PieceType.RECOVERY

    def test_skill_piece(self) -> None:
        p = Piece(id="interp", type=PieceType.SKILL, title="Interpretation")
        assert p.type == PieceType.SKILL


class TestConclusion:
    def test_success_conclusion(self) -> None:
        c = Conclusion(
            summary="Found 4 records",
            status="success",
            key_outputs={"count": 4},
        )
        assert c.status == "success"
        assert c.diagnostics is None

    def test_failed_conclusion_with_diagnostics(self) -> None:
        c = Conclusion(
            summary="Lookup failed",
            status="failed",
            diagnostics="Data source unreachable at node C",
        )
        assert c.status == "failed"
        assert c.diagnostics is not None

    def test_escalated_conclusion(self) -> None:
        c = Conclusion(
            summary="Retry limit exceeded",
            status="escalated",
            diagnostics="3 retries exhausted on node B",
        )
        assert c.status == "escalated"


class TestRoutingDecision:
    def test_mode_a(self) -> None:
        rd = RoutingDecision(
            mode="A",
            matched_pieces=[PieceMatch(piece_id="lookup", score=0.95)],
            confidence_scores={"lookup": 0.95},
        )
        assert rd.mode == "A"
        assert len(rd.matched_pieces) == 1

    def test_mode_d_with_clarification(self) -> None:
        rd = RoutingDecision(
            mode="D",
            clarification_prompt="Did you mean X or Y?",
        )
        assert rd.clarification_prompt is not None


class TestSpawnTask:
    def test_spawn_task(self) -> None:
        st = SpawnTask(
            piece_id="task_1",
            inputs={"record_id": "abc"},
            dependencies=["task_0"],
        )
        assert st.piece_id == "task_1"
        assert st.dependencies == ["task_0"]
