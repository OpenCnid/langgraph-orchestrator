"""Tests for the router — mode classification A/B/C/D and re-routing.

Uses a controllable embedding function that maps specific strings to known vectors,
because the hash-based default doesn't preserve similarity (similar text → different hashes).
"""

import numpy as np

from src.atlas import Atlas
from src.lib.models import Piece, PieceType
from src.router import classify_query, reroute_after_clarification

# Dimension must match EmbeddingIndex default
DIM = 1536


def _vec(seed: int) -> list[float]:
    """Generate a deterministic unit vector from a seed."""
    rng = np.random.RandomState(seed)
    v = rng.randn(DIM).astype(np.float32)
    v /= np.linalg.norm(v)
    return v.tolist()


# Pre-computed vectors for test pieces and queries
VEC_LOOKUP = _vec(1)
VEC_BILLING = _vec(2)
VEC_SUPPORT = _vec(3)
VEC_HR = _vec(4)
VEC_OPS = _vec(5)
VEC_UNRELATED = _vec(99)


def _controllable_embed(text_to_vec: dict[str, list[float]]) -> callable:
    """Create an embed function that maps known texts to pre-defined vectors.

    Unknown texts get a random-ish vector that won't match anything well.
    """

    def embed(text: str) -> list[float]:
        for key, vec in text_to_vec.items():
            if key in text:
                return vec
        return VEC_UNRELATED

    return embed


def _make_piece(piece_id: str, title: str, content: str = "") -> Piece:
    return Piece(
        id=piece_id,
        title=title,
        type=PieceType.FORWARD,
        content=content or title,
    )


class TestModeAClassification:
    """Mode A: single piece matches with high confidence."""

    def test_single_exact_match_returns_mode_a(self) -> None:
        """When the query embedding matches a piece's embedding, should route to A."""
        embed_fn = _controllable_embed({"lookup": VEC_LOOKUP})
        atlas = Atlas(embed_fn=embed_fn)
        atlas.add_piece(_make_piece("lookup", "lookup record"))

        result = classify_query("lookup this record", atlas)
        assert result.mode == "A"
        assert len(result.matched_pieces) == 1
        assert result.matched_pieces[0].piece_id == "lookup"

    def test_mode_a_returns_confidence_scores(self) -> None:
        embed_fn = _controllable_embed({"lookup": VEC_LOOKUP})
        atlas = Atlas(embed_fn=embed_fn)
        atlas.add_piece(_make_piece("lookup", "lookup record"))

        result = classify_query("lookup this", atlas)
        assert "lookup" in result.confidence_scores
        assert result.confidence_scores["lookup"] > 0.8

    def test_single_moderate_match_is_mode_a(self) -> None:
        """A single match above moderate but below high is still A — best available."""
        # Blend query vector with piece vector to get a moderate cosine similarity
        lookup_vec = np.array(VEC_LOOKUP, dtype=np.float32)
        other_vec = np.array(VEC_BILLING, dtype=np.float32)
        # 70% lookup + 30% other gives moderate similarity (~0.7)
        blended = 0.7 * lookup_vec + 0.3 * other_vec
        blended /= np.linalg.norm(blended)

        embed_fn = _controllable_embed({
            "lookup": VEC_LOOKUP,
            "partial": blended.tolist(),
        })
        atlas = Atlas(embed_fn=embed_fn)
        atlas.add_piece(_make_piece("lookup", "lookup record"))

        result = classify_query(
            "partial match query",
            atlas,
            high_threshold=0.99,
            moderate_threshold=0.3,
        )
        assert result.mode == "A"
        assert result.matched_pieces[0].piece_id == "lookup"

    def test_dominant_match_over_others_is_mode_a(self) -> None:
        """One strong match that clearly dominates weaker ones → A."""
        embed_fn = _controllable_embed({
            "lookup": VEC_LOOKUP,
            "billing": VEC_BILLING,
            "support": VEC_SUPPORT,
        })
        atlas = Atlas(embed_fn=embed_fn)
        atlas.add_piece(_make_piece("lookup", "lookup record"))
        atlas.add_piece(_make_piece("billing", "billing process"))
        atlas.add_piece(_make_piece("support", "support tickets"))

        result = classify_query("lookup this item", atlas)
        assert result.mode == "A"
        assert result.matched_pieces[0].piece_id == "lookup"


class TestModeBClassification:
    """Mode B: multiple pieces match above moderate threshold."""

    def test_two_identical_matches_returns_mode_b(self) -> None:
        """Two pieces with identical embeddings → both score equally → Mode B."""
        # Both pieces map to the same vector
        embed_fn = _controllable_embed({"shared": VEC_LOOKUP})
        atlas = Atlas(embed_fn=embed_fn)
        atlas.add_piece(_make_piece("action_a", "shared content"))
        atlas.add_piece(_make_piece("action_b", "shared content"))

        result = classify_query("shared content query", atlas)
        assert result.mode == "B"
        piece_ids = {m.piece_id for m in result.matched_pieces}
        assert "action_a" in piece_ids
        assert "action_b" in piece_ids

    def test_two_moderate_matches(self) -> None:
        """Two matches above moderate → Mode B."""
        # Create two similar but not identical vectors
        v1 = np.array(VEC_LOOKUP, dtype=np.float32)
        v2 = v1.copy()
        v2[:10] += 0.1
        v2 /= np.linalg.norm(v2)
        v2_list = v2.tolist()

        embed_fn = _controllable_embed({
            "alpha": VEC_LOOKUP,
            "beta": v2_list,
            "query": VEC_LOOKUP,  # query matches both well
        })
        atlas = Atlas(embed_fn=embed_fn)
        atlas.add_piece(_make_piece("alpha", "alpha piece"))
        atlas.add_piece(_make_piece("beta", "beta piece"))

        result = classify_query(
            "query for both",
            atlas,
            high_threshold=0.99,
            moderate_threshold=0.5,
        )
        assert result.mode == "B"
        piece_ids = {m.piece_id for m in result.matched_pieces}
        assert "alpha" in piece_ids
        assert "beta" in piece_ids

    def test_multiple_strong_matches_mode_b(self) -> None:
        """Multiple matches above high threshold with similar scores → Mode B."""
        embed_fn = _controllable_embed({"shared": VEC_LOOKUP})
        atlas = Atlas(embed_fn=embed_fn)
        atlas.add_piece(_make_piece("a", "shared workflow a"))
        atlas.add_piece(_make_piece("b", "shared workflow b"))

        result = classify_query("shared query", atlas, high_threshold=0.5)
        assert result.mode == "B"


class TestModeCClassification:
    """Mode C: no piece matches with sufficient confidence."""

    def test_empty_atlas_returns_mode_c(self) -> None:
        embed_fn = _controllable_embed({})
        atlas = Atlas(embed_fn=embed_fn)
        result = classify_query("anything at all", atlas)
        assert result.mode == "C"
        assert len(result.matched_pieces) == 0

    def test_single_weak_match_is_mode_c(self) -> None:
        """Single weak match below moderate → Mode C (not D, which needs >=2)."""
        embed_fn = _controllable_embed({
            "obscure": VEC_LOOKUP,
            "unrelated_query": VEC_UNRELATED,
        })
        atlas = Atlas(embed_fn=embed_fn)
        atlas.add_piece(_make_piece("obscure", "obscure piece"))

        result = classify_query(
            "unrelated_query entirely",
            atlas,
            high_threshold=0.99,
            moderate_threshold=0.99,
        )
        # Only 1 weak match → Mode C
        assert result.mode == "C"


class TestModeDClassification:
    """Mode D: multiple weak matches across unrelated domains."""

    def test_multiple_weak_matches_returns_mode_d(self) -> None:
        """Multiple matches below moderate → ambiguous → Mode D."""
        # Create a query vector that partially matches multiple pieces
        # (blended so cosine sim is above noise floor but below moderate).
        blend = np.array(VEC_BILLING) + np.array(VEC_HR) + np.array(VEC_OPS)
        blend = blend / np.linalg.norm(blend)
        vec_ambiguous = blend.tolist()

        embed_fn = _controllable_embed({
            "finance": VEC_BILLING,
            "hr": VEC_HR,
            "ops": VEC_OPS,
            "help": vec_ambiguous,
        })
        atlas = Atlas(embed_fn=embed_fn)
        atlas.add_piece(_make_piece("finance", "finance quarterly revenue"))
        atlas.add_piece(_make_piece("hr", "hr employee onboarding"))
        atlas.add_piece(_make_piece("ops", "ops staging deploy"))

        result = classify_query(
            "help me with something",
            atlas,
            high_threshold=0.99,
            moderate_threshold=0.99,
        )
        assert result.mode == "D"
        assert result.clarification_prompt is not None
        assert len(result.matched_pieces) >= 2

    def test_mode_d_includes_clarification_prompt(self) -> None:
        # Blend query vector to partially match both pieces
        blend = np.array(VEC_BILLING) + np.array(VEC_SUPPORT)
        blend = blend / np.linalg.norm(blend)
        vec_partial = blend.tolist()

        embed_fn = _controllable_embed({
            "billing": VEC_BILLING,
            "support": VEC_SUPPORT,
            "customer": vec_partial,
        })
        atlas = Atlas(embed_fn=embed_fn)
        atlas.add_piece(_make_piece("billing", "billing invoices"))
        atlas.add_piece(_make_piece("support", "support tickets"))

        result = classify_query(
            "customer issue",
            atlas,
            high_threshold=0.99,
            moderate_threshold=0.99,
        )
        assert result.mode == "D"
        assert result.clarification_prompt is not None
        assert "customer issue" in result.clarification_prompt


class TestThresholdConfigurability:
    """Thresholds should be configurable via parameters."""

    def test_custom_thresholds_change_mode(self) -> None:
        """Lowering thresholds can change classification from C/D to A."""
        embed_fn = _controllable_embed({"lookup": VEC_LOOKUP})
        atlas = Atlas(embed_fn=embed_fn)
        atlas.add_piece(_make_piece("lookup", "lookup record"))

        # With impossible thresholds → not Mode A
        result_strict = classify_query(
            "lookup this",
            atlas,
            high_threshold=1.01,
            moderate_threshold=1.01,
        )
        assert result_strict.mode in ("C", "D")

        # With very low thresholds → Mode A
        result_loose = classify_query(
            "lookup this",
            atlas,
            high_threshold=0.01,
            moderate_threshold=0.01,
        )
        assert result_loose.mode == "A"


class TestModeDRerouting:
    """Mode D re-routing: must not produce D again."""

    def test_reroute_prevents_mode_d(self) -> None:
        """Re-routing after clarification must not return Mode D."""
        embed_fn = _controllable_embed({
            "billing": VEC_BILLING,
            "support": VEC_SUPPORT,
            "customer": VEC_UNRELATED,
        })
        atlas = Atlas(embed_fn=embed_fn)
        atlas.add_piece(_make_piece("billing", "billing invoices"))
        atlas.add_piece(_make_piece("support", "support tickets"))

        result = reroute_after_clarification(
            "customer issue",
            atlas,
            high_threshold=0.99,
            moderate_threshold=0.99,
        )
        assert result.mode != "D"
        assert result.mode == "C"

    def test_reroute_allows_mode_a(self) -> None:
        """If narrowed query matches clearly, re-routing returns A."""
        embed_fn = _controllable_embed({"billing": VEC_BILLING})
        atlas = Atlas(embed_fn=embed_fn)
        atlas.add_piece(_make_piece("billing", "billing process"))

        result = reroute_after_clarification("billing question", atlas)
        assert result.mode == "A"

    def test_reroute_allows_mode_b(self) -> None:
        """Re-routing can return Mode B if multiple matches are found."""
        embed_fn = _controllable_embed({"shared": VEC_LOOKUP})
        atlas = Atlas(embed_fn=embed_fn)
        atlas.add_piece(_make_piece("alpha", "shared text alpha"))
        atlas.add_piece(_make_piece("beta", "shared text beta"))

        result = reroute_after_clarification(
            "shared request",
            atlas,
            high_threshold=0.99,
            moderate_threshold=0.5,
        )
        assert result.mode == "B"


class TestEdgeCases:
    """Edge cases and boundary conditions."""

    def test_no_clarification_prompt_for_non_d_modes(self) -> None:
        embed_fn = _controllable_embed({"lookup": VEC_LOOKUP})
        atlas = Atlas(embed_fn=embed_fn)
        atlas.add_piece(_make_piece("lookup", "lookup record"))

        result = classify_query("lookup this", atlas)
        assert result.clarification_prompt is None

    def test_confidence_scores_populated(self) -> None:
        embed_fn = _controllable_embed({
            "first": VEC_LOOKUP,
            "second": VEC_BILLING,
        })
        atlas = Atlas(embed_fn=embed_fn)
        atlas.add_piece(_make_piece("a", "first piece"))
        atlas.add_piece(_make_piece("b", "second piece"))

        result = classify_query("first piece query", atlas)
        assert len(result.confidence_scores) > 0

    def test_matched_pieces_have_valid_scores(self) -> None:
        embed_fn = _controllable_embed({"lookup": VEC_LOOKUP})
        atlas = Atlas(embed_fn=embed_fn)
        atlas.add_piece(_make_piece("lookup", "lookup record"))

        result = classify_query("lookup this", atlas)
        for m in result.matched_pieces:
            assert isinstance(m.score, float)
            assert -1.0 <= m.score <= 1.0
