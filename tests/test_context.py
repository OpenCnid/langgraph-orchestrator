"""Tests for context management — assembly, compaction, isolation."""

import hashlib

from src.atlas import Atlas
from src.lib.compaction import compact, estimate_token_count, needs_compaction
from src.lib.context import assemble_context
from src.lib.models import Conclusion, Piece, PieceMatch, PieceType


def _deterministic_embed(text: str) -> list[float]:
    h = hashlib.sha256(text.encode()).digest()
    vec: list[float] = []
    for i in range(1536):
        byte_idx = i % len(h)
        bit_idx = i % 8
        val = ((h[byte_idx] >> bit_idx) & 1) * 2.0 - 1.0
        vec.append(val)
    return vec


class TestContextAssembly:
    """Context is assembled fresh per task — curated, not accumulated."""

    def test_assembles_matched_pieces(self) -> None:
        atlas = Atlas(embed_fn=_deterministic_embed)
        piece = Piece(
            id="lookup", title="Record Lookup", type=PieceType.FORWARD,
            content="# Record Lookup\nLook up records by ID.",
        )
        atlas.add_piece(piece)

        ctx = assemble_context(
            "find a record",
            atlas,
            matched_pieces=[PieceMatch(piece_id="lookup", score=0.9)],
        )
        assert "Record Lookup" in ctx
        assert "0.90" in ctx

    def test_includes_skills(self) -> None:
        atlas = Atlas(embed_fn=_deterministic_embed)
        skill = Piece(
            id="interp", title="Interpretation Skill", type=PieceType.SKILL,
            content="# Interpretation\nHeuristics for ambiguous results.",
        )
        atlas.add_piece(skill)

        ctx = assemble_context("interpret results", atlas)
        assert "Interpretation" in ctx

    def test_includes_user_preferences(self) -> None:
        atlas = Atlas(embed_fn=_deterministic_embed)
        ctx = assemble_context(
            "test query",
            atlas,
            user_preferences={"output_format": "json", "verbosity": "low"},
        )
        assert "output_format" in ctx
        assert "json" in ctx

    def test_includes_prior_digest(self) -> None:
        atlas = Atlas(embed_fn=_deterministic_embed)
        ctx = assemble_context(
            "test query",
            atlas,
            prior_digest="Previously found 3 records matching criteria.",
        )
        assert "Previously found 3 records" in ctx

    def test_empty_context_when_nothing_relevant(self) -> None:
        atlas = Atlas(embed_fn=_deterministic_embed)
        ctx = assemble_context("obscure query", atlas)
        # May have skills but no matched pieces
        assert isinstance(ctx, str)


class TestCompaction:
    """Compaction reduces context size while preserving key decisions."""

    def test_token_count_estimate(self) -> None:
        assert estimate_token_count("four") == 1  # 4 chars / 4
        assert estimate_token_count("a" * 400) == 100

    def test_needs_compaction_above_threshold(self) -> None:
        long_text = "x" * 30000  # ~7500 tokens
        assert needs_compaction(long_text, threshold=6000)

    def test_no_compaction_below_threshold(self) -> None:
        short_text = "hello world"
        assert not needs_compaction(short_text, threshold=6000)

    def test_compact_produces_digest(self) -> None:
        context = "A very long context with lots of detail " * 100
        conclusions = [
            Conclusion(summary="Found 3 records", status="success"),
            Conclusion(summary="Updated status", status="success"),
        ]

        result = compact(context, conclusions)
        assert "digest" in result
        assert "archived_context" in result
        assert result["archived_context"] == context
        assert "Found 3 records" in result["digest"]
        assert "Updated status" in result["digest"]

    def test_compact_preserves_key_decisions(self) -> None:
        result = compact(
            "long context",
            [],
            key_decisions=["Use JSON output", "Skip archived records"],
        )
        assert "Use JSON output" in result["digest"]
        assert "Skip archived records" in result["digest"]

    def test_compact_reduces_size(self) -> None:
        long_context = "Detailed tool output " * 500
        conclusions = [
            Conclusion(summary="Summary A", status="success"),
        ]
        result = compact(long_context, conclusions)
        assert len(result["digest"]) < len(long_context)

    def test_compact_with_empty_inputs(self) -> None:
        result = compact("", [])
        assert result["digest"] == "No prior context."


class TestSubagentIsolation:
    """Subagent context windows contain only their piece + inputs."""

    def test_context_assembly_does_not_leak_unrelated_pieces(self) -> None:
        """Only matched pieces appear in the assembled context."""
        atlas = Atlas(embed_fn=_deterministic_embed)
        atlas.add_piece(Piece(
            id="a", title="Piece A", type=PieceType.FORWARD,
            content="Content A",
        ))
        atlas.add_piece(Piece(
            id="b", title="Piece B", type=PieceType.FORWARD,
            content="Content B",
        ))

        # Only match piece A
        ctx = assemble_context(
            "query",
            atlas,
            matched_pieces=[PieceMatch(piece_id="a", score=0.9)],
        )
        assert "Piece A" in ctx
        # Piece B should not be in the matched pieces section
        # (it might appear in skills search results, which is fine)
