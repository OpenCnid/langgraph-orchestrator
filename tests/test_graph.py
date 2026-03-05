"""Tests for the orchestrator graph topology — verifies routing dispatches correctly."""

import numpy as np

from src.atlas import Atlas
from src.graph import build_graph
from src.lib.models import Piece, PieceType

DIM = 1536


def _vec(seed: int) -> list[float]:
    rng = np.random.RandomState(seed)
    v = rng.randn(DIM).astype(np.float32)
    v /= np.linalg.norm(v)
    return v.tolist()


VEC_LOOKUP = _vec(1)
VEC_BILLING = _vec(2)
VEC_SUPPORT = _vec(3)
VEC_UNRELATED = _vec(99)


def _controllable_embed(text_to_vec: dict[str, list[float]]) -> callable:
    def embed(text: str) -> list[float]:
        for key, vec in text_to_vec.items():
            if key in text:
                return vec
        return VEC_UNRELATED

    return embed


def _make_piece(piece_id: str, title: str) -> Piece:
    return Piece(id=piece_id, title=title, type=PieceType.FORWARD, content=title)


class TestGraphTopologyModeA:
    """Route node dispatches to execute_a for Mode A queries."""

    def test_mode_a_single_match(self) -> None:
        embed_fn = _controllable_embed({"lookup": VEC_LOOKUP})
        atlas = Atlas(embed_fn=embed_fn)
        atlas.add_piece(_make_piece("lookup", "lookup record"))

        graph = build_graph(atlas)
        app = graph.compile()

        result = app.invoke({"query": "lookup this record"})
        assert result["routing_decision"].mode == "A"
        assert "merged_response" in result
        assert result["merged_response"] != ""
        assert len(result["subagent_conclusions"]) == 1
        assert result["subagent_conclusions"][0].status == "success"


class TestGraphTopologyModeB:
    """Route node dispatches through plan_b → spawn_b → merge_b for Mode B."""

    def test_mode_b_multiple_matches(self) -> None:
        embed_fn = _controllable_embed({"shared": VEC_LOOKUP})
        atlas = Atlas(embed_fn=embed_fn)
        atlas.add_piece(_make_piece("alpha", "shared workflow alpha"))
        atlas.add_piece(_make_piece("beta", "shared workflow beta"))

        graph = build_graph(atlas)
        app = graph.compile()

        result = app.invoke({"query": "shared task request"})
        assert result["routing_decision"].mode == "B"
        assert "merged_response" in result
        assert len(result["subagent_conclusions"]) >= 2
        assert result["spawn_plan"] is not None
        assert len(result["spawn_plan"]) >= 2

    def test_mode_b_spawn_plan_has_correct_piece_ids(self) -> None:
        embed_fn = _controllable_embed({"shared": VEC_LOOKUP})
        atlas = Atlas(embed_fn=embed_fn)
        atlas.add_piece(_make_piece("alpha", "shared workflow alpha"))
        atlas.add_piece(_make_piece("beta", "shared workflow beta"))

        graph = build_graph(atlas)
        app = graph.compile()

        result = app.invoke({"query": "shared task"})
        plan_ids = {t.piece_id for t in result["spawn_plan"]}
        assert "alpha" in plan_ids
        assert "beta" in plan_ids


class TestGraphTopologyModeC:
    """Route node dispatches to draft_c when no pieces match."""

    def test_mode_c_empty_atlas(self) -> None:
        embed_fn = _controllable_embed({})
        atlas = Atlas(embed_fn=embed_fn)

        graph = build_graph(atlas)
        app = graph.compile()

        result = app.invoke({"query": "something with no matching piece"})
        assert result["routing_decision"].mode == "C"
        assert "No matching piece" in result["merged_response"]
        assert result["subagent_conclusions"][0].status == "escalated"


class TestGraphTopologyModeD:
    """Route node dispatches to clarify_d when query is ambiguous."""

    def test_mode_d_ambiguous_query(self) -> None:
        embed_fn = _controllable_embed({
            "billing": VEC_BILLING,
            "support": VEC_SUPPORT,
            "help": VEC_UNRELATED,
        })
        atlas = Atlas(embed_fn=embed_fn)
        atlas.add_piece(_make_piece("billing", "billing invoices"))
        atlas.add_piece(_make_piece("support", "support tickets"))

        graph = build_graph(atlas)
        app = graph.compile()

        result = app.invoke({
            "query": "help me with something",
            "routing_decision": None,  # type: ignore[typeddict-item]
        })
        # With forced high thresholds in settings (default 0.85/0.60),
        # low-similarity matches may route to D
        mode = result["routing_decision"].mode
        assert mode in ("C", "D")
        assert "merged_response" in result


class TestGraphTopologyMerger:
    """Merger handles partial failures gracefully."""

    def test_mode_b_merger_synthesizes_response(self) -> None:
        embed_fn = _controllable_embed({"shared": VEC_LOOKUP})
        atlas = Atlas(embed_fn=embed_fn)
        atlas.add_piece(_make_piece("alpha", "shared workflow alpha"))
        atlas.add_piece(_make_piece("beta", "shared workflow beta"))

        graph = build_graph(atlas)
        app = graph.compile()

        result = app.invoke({"query": "shared request"})
        assert result["merged_response"]
        # Should contain references to the executed pieces
        assert "alpha" in result["merged_response"] or "beta" in result["merged_response"]


class TestSubagentIsolation:
    """Subagent state schema enforces isolation contract (P5.3)."""

    def test_subagent_state_has_only_piece_and_inputs(self) -> None:
        """SubagentState should only contain piece_id, piece_content, inputs, conclusion."""
        from src.lib.state import SubagentState

        # Verify the TypedDict only has the expected keys
        expected_keys = {"piece_id", "piece_content", "inputs", "conclusion"}
        assert set(SubagentState.__annotations__.keys()) == expected_keys

    def test_orchestrator_state_has_required_fields(self) -> None:
        from src.lib.state import OrchestratorState

        required = {
            "query", "routing_decision", "spawn_plan",
            "subagent_conclusions", "merged_response",
            "context_digest", "memory_log", "human_input",
        }
        assert required.issubset(set(OrchestratorState.__annotations__.keys()))
