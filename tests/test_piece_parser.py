"""Tests for piece markdown parser — P2, P6.1."""

from pathlib import Path

import pytest

from src.lib.models import PieceStatus, PieceType
from src.lib.piece_parser import parse_piece_file

FIXTURES = Path(__file__).parent.parent / "pieces"


class TestParsePieceFile:
    def test_parse_forward_piece(self) -> None:
        piece = parse_piece_file(FIXTURES / "forward" / "sample_lookup.md")
        assert piece.id == "sample_lookup"
        assert piece.type == PieceType.FORWARD
        assert piece.status == PieceStatus.ACTIVE
        assert piece.compact_identifier == "🔍"
        assert "sample_not_found" in piece.connections
        assert "```mermaid" in piece.content
        assert piece.title == "🔍 Record Lookup"

    def test_parse_recovery_piece(self) -> None:
        piece = parse_piece_file(FIXTURES / "recovery" / "sample_not_found.md")
        assert piece.id == "sample_not_found"
        assert piece.type == PieceType.RECOVERY
        assert piece.status == PieceStatus.ACTIVE
        assert piece.compact_identifier == "❌"
        assert "no_results" in piece.response_shapes_handled
        assert "empty_response" in piece.response_shapes_handled
        assert "404" in piece.response_shapes_handled

    def test_parse_skill_piece(self) -> None:
        piece = parse_piece_file(FIXTURES / "skills" / "sample_interpretation.md")
        assert piece.id == "sample_interpretation"
        assert piece.type == PieceType.SKILL
        assert piece.status == PieceStatus.ACTIVE
        assert piece.compact_identifier == "🧠"
        assert "sample_lookup" in piece.connections

    def test_reject_piece_without_mermaid(self, tmp_path: Path) -> None:
        no_mermaid = tmp_path / "bad.md"
        bad_content = "# Bad Piece\n**Type:** forward\n**Status:** active\nNo diagram."
        no_mermaid.write_text(bad_content)
        with pytest.raises(ValueError, match="no mermaid diagram"):
            parse_piece_file(no_mermaid)

    def test_infer_type_from_path(self, tmp_path: Path) -> None:
        """When no Type: header, infer from directory path."""
        recovery_dir = tmp_path / "recovery"
        recovery_dir.mkdir()
        piece_file = recovery_dir / "test_piece.md"
        piece_file.write_text("# Test\n```mermaid\ngraph TD\n    A-->B\n```\n")
        piece = parse_piece_file(piece_file)
        assert piece.type == PieceType.RECOVERY
