"""End-to-end integration tests — query → route → execute → response for all modes."""

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


VEC_A = _vec(1)
VEC_B = _vec(2)
VEC_C = _vec(3)
VEC_UNRELATED = _vec(99)

MERMAID = """
```mermaid
graph TD
    A[Start] --> B{Check}
    B -->|OK| C[Process]
    B -->|Fail| D[Error]
    C --> E[Done]
```
"""


def _embed(text_to_vec: dict[str, list[float]]) -> callable:
    def fn(text: str) -> list[float]:
        for key, vec in text_to_vec.items():
            if key in text:
                return vec
        return VEC_UNRELATED

    return fn


def _make_piece(pid: str, title: str, connections: list[str] | None = None) -> Piece:
    conn_str = ", ".join(connections or [])
    content = f"# {title}\n\n**Type:** forward\n**Connections:** [{conn_str}]\n{MERMAID}"
    return Piece(
        id=pid, title=title, type=PieceType.FORWARD,
        content=content, connections=connections or [],
    )


class TestEndToEndModeA:
    """Complete flow: query → route(A) → execute → conclusion → response."""

    def test_mode_a_full_flow(self) -> None:
        atlas = Atlas(embed_fn=_embed({"lookup": VEC_A}))
        atlas.add_piece(_make_piece("lookup", "lookup record"))

        call_log: list[dict[str, str]] = []

        def llm_fn(system: str, user: str) -> str:
            call_log.append({"system": system[:100], "user": user[:100]})
            return json.dumps({
                "summary": "Found record R-123 with status active",
                "status": "success",
                "key_outputs": {"record_id": "R-123", "status": "active"},
            })

        graph = build_graph(atlas, llm_fn=llm_fn)
        app = graph.compile()

        result = app.invoke({"query": "lookup record R-123"})

        # Verify routing
        assert result["routing_decision"].mode == "A"

        # Verify execution
        assert len(call_log) == 1
        sys_lower = call_log[0]["system"].lower()
        assert "mermaid" in sys_lower or "workflow" in sys_lower

        # Verify conclusion
        conclusions = result["subagent_conclusions"]
        assert len(conclusions) == 1
        assert conclusions[0].status == "success"
        assert "R-123" in conclusions[0].summary

        # Verify response
        assert "R-123" in result["merged_response"]


class TestEndToEndModeB:
    """Complete flow: query → route(B) → plan → spawn → merge → response."""

    def test_mode_b_parallel_execution(self) -> None:
        atlas = Atlas(embed_fn=_embed({"shared": VEC_A}))
        atlas.add_piece(_make_piece("billing", "shared billing workflow"))
        atlas.add_piece(_make_piece("support", "shared support workflow"))

        pieces_executed: list[str] = []

        def llm_fn(system: str, user: str) -> str:
            # Track which piece is being executed
            if "billing" in system.lower():
                pieces_executed.append("billing")
                return json.dumps({
                    "summary": "Billing: 5 invoices processed",
                    "status": "success",
                    "key_outputs": {"invoices": 5, "piece_id": "billing"},
                })
            pieces_executed.append("support")
            return json.dumps({
                "summary": "Support: 3 tickets resolved",
                "status": "success",
                "key_outputs": {"tickets": 3, "piece_id": "support"},
            })

        graph = build_graph(atlas, llm_fn=llm_fn)
        app = graph.compile()

        result = app.invoke({"query": "shared quarterly review"})

        assert result["routing_decision"].mode == "B"
        assert len(result["subagent_conclusions"]) == 2
        assert len(result["spawn_plan"]) == 2

        # Both pieces should have been executed
        assert len(pieces_executed) == 2

        # Merged response should contain both summaries
        response = result["merged_response"]
        assert "invoices" in response.lower() or "tickets" in response.lower()

    def test_mode_b_with_dependency_chain(self) -> None:
        """Sequential execution where piece B depends on piece A."""
        atlas = Atlas(embed_fn=_embed({"shared": VEC_A}))
        atlas.add_piece(_make_piece("base", "shared base workflow"))
        atlas.add_piece(_make_piece(
            "derived", "shared derived workflow",
            connections=["base"],
        ))

        execution_order: list[str] = []

        def llm_fn(system: str, user: str) -> str:
            if "base" in system.lower():
                execution_order.append("base")
                return json.dumps({
                    "summary": "Base data collected",
                    "status": "success",
                    "key_outputs": {"data": "collected"},
                })
            execution_order.append("derived")
            return json.dumps({
                "summary": "Derived analysis complete",
                "status": "success",
            })

        graph = build_graph(atlas, llm_fn=llm_fn)
        app = graph.compile()

        result = app.invoke({"query": "shared analysis"})
        assert result["routing_decision"].mode == "B"
        assert len(result["subagent_conclusions"]) == 2


class TestEndToEndModeC:
    """Complete flow: query → route(C) → draft → halt."""

    def test_mode_c_creates_draft_and_halts(self) -> None:
        atlas = Atlas(embed_fn=_embed({}))

        graph = build_graph(atlas)
        app = graph.compile()

        result = app.invoke({"query": "quantum entanglement analysis"})

        assert result["routing_decision"].mode == "C"
        assert result["subagent_conclusions"][0].status == "escalated"
        assert "Draft created" in result["merged_response"]

        # Verify draft piece was saved to atlas
        draft_id = result["subagent_conclusions"][0].key_outputs["draft_piece_id"]
        draft = atlas.get_piece(draft_id)
        assert draft is not None
        assert draft.status.value == "draft"


class TestEndToEndModeD:
    """Complete flow: query → route(D) → clarify → await input."""

    def test_mode_d_returns_clarification(self) -> None:
        atlas = Atlas(embed_fn=_embed({
            "billing": VEC_B,
            "support": VEC_C,
            "vague": VEC_UNRELATED,
        }))
        atlas.add_piece(_make_piece("billing", "billing workflow"))
        atlas.add_piece(_make_piece("support", "support workflow"))

        graph = build_graph(atlas)
        app = graph.compile()

        result = app.invoke({
            "query": "vague request about something",
        })

        mode = result["routing_decision"].mode
        assert mode in ("C", "D")
        if mode == "D":
            assert result["routing_decision"].clarification_prompt is not None


class TestEndToEndWithMemory:
    """Integration with memory — review cycle after execution."""

    def test_execution_and_review(self) -> None:
        from src.memory import MemoryStore, review_cycle

        atlas = Atlas(embed_fn=_embed({"lookup": VEC_A}))
        atlas.add_piece(_make_piece("lookup", "lookup record"))

        def llm_fn(system: str, user: str) -> str:
            return json.dumps({
                "summary": "Found record",
                "status": "success",
            })

        graph = build_graph(atlas, llm_fn=llm_fn)
        app = graph.compile()

        result = app.invoke({"query": "lookup something"})
        conclusion = result["subagent_conclusions"][0]

        # Review cycle
        mem = MemoryStore()
        review = review_cycle(
            mem, atlas,
            query="lookup something",
            mode=result["routing_decision"].mode,
            piece_ids=[m.piece_id for m in result["routing_decision"].matched_pieces],
            status=conclusion.status,
            summary=conclusion.summary,
        )
        assert review["recorded"]
        assert len(mem.get_history()) == 1
