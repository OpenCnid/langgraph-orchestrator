"""Tests for the orchestrator graph — routing, execution, merging."""

import json

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


MERMAID_CONTENT = """
```mermaid
graph TD
    A[Start] --> B[Process]
    B --> C[End]
```
"""


def _make_piece(piece_id: str, title: str) -> Piece:
    content = f"# {title}\n\n**Type:** forward\n**Status:** active\n\n{MERMAID_CONTENT}"
    return Piece(id=piece_id, title=title, type=PieceType.FORWARD, content=content)


def _mock_llm_fn(system: str, user: str) -> str:
    return json.dumps({"summary": "Executed successfully", "status": "success"})


class TestGraphTopologyModeA:
    """Route node dispatches to execute_a for Mode A queries."""

    def test_mode_a_single_match(self) -> None:
        embed_fn = _controllable_embed({"lookup": VEC_LOOKUP})
        atlas = Atlas(embed_fn=embed_fn)
        atlas.add_piece(_make_piece("lookup", "lookup record"))

        graph = build_graph(atlas, llm_fn=_mock_llm_fn)
        app = graph.compile()

        result = app.invoke({"query": "lookup this record"})
        assert result["routing_decision"].mode == "A"
        assert "merged_response" in result
        assert result["merged_response"] != ""
        assert len(result["subagent_conclusions"]) == 1
        assert result["subagent_conclusions"][0].status == "success"

    def test_mode_a_uses_piece_runner(self) -> None:
        """Mode A should execute the piece via piece_runner, not return a stub."""
        prompts_received: list[str] = []

        def tracking_llm(system: str, user: str) -> str:
            prompts_received.append(system)
            return json.dumps({
                "summary": "Found 3 records",
                "status": "success",
                "key_outputs": {"count": 3},
            })

        embed_fn = _controllable_embed({"lookup": VEC_LOOKUP})
        atlas = Atlas(embed_fn=embed_fn)
        atlas.add_piece(_make_piece("lookup", "lookup record"))

        graph = build_graph(atlas, llm_fn=tracking_llm)
        app = graph.compile()

        result = app.invoke({"query": "lookup this record"})
        assert len(prompts_received) == 1
        assert "mermaid" in prompts_received[0].lower()
        assert result["subagent_conclusions"][0].summary == "Found 3 records"


class TestGraphTopologyModeB:
    """Route node dispatches through plan_b → spawn_b → merge_b for Mode B."""

    def test_mode_b_multiple_matches(self) -> None:
        embed_fn = _controllable_embed({"shared": VEC_LOOKUP})
        atlas = Atlas(embed_fn=embed_fn)
        atlas.add_piece(_make_piece("alpha", "shared workflow alpha"))
        atlas.add_piece(_make_piece("beta", "shared workflow beta"))

        graph = build_graph(atlas, llm_fn=_mock_llm_fn)
        app = graph.compile()

        result = app.invoke({"query": "shared task request"})
        assert result["routing_decision"].mode == "B"
        assert "merged_response" in result
        assert len(result["subagent_conclusions"]) >= 2
        assert len(result["spawn_plan"]) >= 2

    def test_mode_b_spawn_plan_has_correct_piece_ids(self) -> None:
        embed_fn = _controllable_embed({"shared": VEC_LOOKUP})
        atlas = Atlas(embed_fn=embed_fn)
        atlas.add_piece(_make_piece("alpha", "shared workflow alpha"))
        atlas.add_piece(_make_piece("beta", "shared workflow beta"))

        graph = build_graph(atlas, llm_fn=_mock_llm_fn)
        app = graph.compile()

        result = app.invoke({"query": "shared task"})
        plan_ids = {t.piece_id for t in result["spawn_plan"]}
        assert "alpha" in plan_ids
        assert "beta" in plan_ids

    def test_mode_b_uses_piece_runner(self) -> None:
        """Mode B should execute each piece via piece_runner."""
        call_count = 0

        def counting_llm(system: str, user: str) -> str:
            nonlocal call_count
            call_count += 1
            return json.dumps({
                "summary": f"Piece {call_count} done",
                "status": "success",
            })

        embed_fn = _controllable_embed({"shared": VEC_LOOKUP})
        atlas = Atlas(embed_fn=embed_fn)
        atlas.add_piece(_make_piece("alpha", "shared workflow alpha"))
        atlas.add_piece(_make_piece("beta", "shared workflow beta"))

        graph = build_graph(atlas, llm_fn=counting_llm)
        app = graph.compile()

        result = app.invoke({"query": "shared task"})
        assert call_count == 2
        assert len(result["subagent_conclusions"]) == 2

    def test_mode_b_dependency_analysis(self) -> None:
        """Planner detects dependencies via piece connections."""
        embed_fn = _controllable_embed({"shared": VEC_LOOKUP})
        atlas = Atlas(embed_fn=embed_fn)

        # Beta depends on alpha via connections
        p1 = _make_piece("alpha", "shared workflow alpha")
        p2 = Piece(
            id="beta",
            title="shared workflow beta",
            type=PieceType.FORWARD,
            content=f"# Beta\n\n**Connections:** [alpha]\n\n{MERMAID_CONTENT}",
            connections=["alpha"],
        )
        atlas.add_piece(p1)
        atlas.add_piece(p2)

        graph = build_graph(atlas, llm_fn=_mock_llm_fn)
        app = graph.compile()

        result = app.invoke({"query": "shared task"})
        # Find beta's spawn task
        beta_task = next(
            (t for t in result["spawn_plan"] if t.piece_id == "beta"), None
        )
        assert beta_task is not None
        assert "alpha" in beta_task.dependencies


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

        result = app.invoke({"query": "help me with something"})
        mode = result["routing_decision"].mode
        assert mode in ("C", "D")
        assert "merged_response" in result


class TestGraphMerger:
    """Merger synthesizes conclusions from multiple pieces."""

    def test_merger_combines_successes(self) -> None:
        embed_fn = _controllable_embed({"shared": VEC_LOOKUP})
        atlas = Atlas(embed_fn=embed_fn)
        atlas.add_piece(_make_piece("alpha", "shared workflow alpha"))
        atlas.add_piece(_make_piece("beta", "shared workflow beta"))

        graph = build_graph(atlas, llm_fn=_mock_llm_fn)
        app = graph.compile()

        result = app.invoke({"query": "shared request"})
        assert result["merged_response"]

    def test_merger_handles_partial_failure(self) -> None:
        """If one piece fails, merger reports both successes and failures."""
        call_count = 0

        def mixed_llm(system: str, user: str) -> str:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return json.dumps({
                    "summary": "Success",
                    "status": "success",
                })
            return json.dumps({
                "summary": "Error occurred",
                "status": "failed",
                "diagnostics": "Data source unavailable",
            })

        embed_fn = _controllable_embed({"shared": VEC_LOOKUP})
        atlas = Atlas(embed_fn=embed_fn)
        atlas.add_piece(_make_piece("alpha", "shared workflow alpha"))
        atlas.add_piece(_make_piece("beta", "shared workflow beta"))

        graph = build_graph(atlas, llm_fn=mixed_llm)
        app = graph.compile()

        result = app.invoke({"query": "shared task"})
        response = result["merged_response"]
        assert "Success" in response
        assert "failed" in response.lower()


class TestSubagentIsolation:
    """Subagent state schema enforces isolation contract (P5.3)."""

    def test_subagent_state_has_only_piece_and_inputs(self) -> None:
        from src.lib.state import SubagentState

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
