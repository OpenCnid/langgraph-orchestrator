"""Tests for contradiction detection between subagent conclusions."""

import json

from src.lib.contradiction import detect_contradictions
from src.lib.models import Conclusion


def _conclusion(
    summary: str,
    status: str = "success",
    key_outputs: dict | None = None,
) -> Conclusion:
    return Conclusion(
        summary=summary,
        status=status,
        key_outputs=key_outputs or {},
    )


class TestHeuristicContradiction:
    """Heuristic-based contradiction detection via key_output comparison."""

    def test_no_contradictions_with_single_conclusion(self) -> None:
        results = detect_contradictions([_conclusion("Only one")])
        assert results == []

    def test_no_contradictions_when_compatible(self) -> None:
        c1 = _conclusion("Found 3 records", key_outputs={"count": 3, "piece_id": "a"})
        c2 = _conclusion("Updated status", key_outputs={"status": "done", "piece_id": "b"})
        results = detect_contradictions([c1, c2])
        assert results == []

    def test_detects_conflicting_key_outputs(self) -> None:
        c1 = _conclusion("Q3 revenue: 1.5M", key_outputs={"revenue": "1.5M", "piece_id": "a"})
        c2 = _conclusion("Q3 revenue: 2.1M", key_outputs={"revenue": "2.1M", "piece_id": "b"})
        results = detect_contradictions([c1, c2])
        assert len(results) == 1
        assert "revenue" in results[0]["description"]

    def test_skips_failed_conclusions(self) -> None:
        c1 = _conclusion("Success", key_outputs={"val": 1})
        c2 = _conclusion("Error", status="failed", key_outputs={"val": 2})
        results = detect_contradictions([c1, c2])
        assert results == []

    def test_multiple_pairs_checked(self) -> None:
        c1 = _conclusion("A", key_outputs={"x": 1, "piece_id": "a"})
        c2 = _conclusion("B", key_outputs={"x": 2, "piece_id": "b"})
        c3 = _conclusion("C", key_outputs={"x": 3, "piece_id": "c"})
        results = detect_contradictions([c1, c2, c3])
        # c1 vs c2, c1 vs c3, c2 vs c3 — all conflict on x
        assert len(results) == 3

    def test_empty_list_no_contradictions(self) -> None:
        assert detect_contradictions([]) == []


class TestLLMContradiction:
    """LLM-based semantic contradiction detection."""

    def test_llm_detects_contradiction(self) -> None:
        def llm_fn(system: str, user: str) -> str:
            return json.dumps({
                "contradicts": True,
                "description": "Revenue figures disagree",
            })

        c1 = _conclusion("Q3 at 1.5M", key_outputs={"piece_id": "a"})
        c2 = _conclusion("Q3 at 2.1M", key_outputs={"piece_id": "b"})
        results = detect_contradictions([c1, c2], llm_fn=llm_fn)
        assert len(results) == 1
        assert "Revenue" in results[0]["description"]

    def test_llm_no_contradiction(self) -> None:
        def llm_fn(system: str, user: str) -> str:
            return json.dumps({"contradicts": False, "description": ""})

        c1 = _conclusion("Found records", key_outputs={"piece_id": "a"})
        c2 = _conclusion("Updated status", key_outputs={"piece_id": "b"})
        results = detect_contradictions([c1, c2], llm_fn=llm_fn)
        assert results == []

    def test_llm_failure_gracefully_handled(self) -> None:
        def failing_llm(system: str, user: str) -> str:
            raise RuntimeError("API error")

        c1 = _conclusion("A", key_outputs={"piece_id": "a"})
        c2 = _conclusion("B", key_outputs={"piece_id": "b"})
        # Should not raise — gracefully returns no contradictions
        results = detect_contradictions([c1, c2], llm_fn=failing_llm)
        assert results == []


class TestContradictionInMerger:
    """Contradictions detected by merger appear in merged response."""

    def test_merger_reports_contradictions(self) -> None:
        import numpy as np

        from src.atlas import Atlas
        from src.graph import build_graph
        from src.lib.models import Piece, PieceType

        dim = 1536
        rng = np.random.RandomState(1)
        vec = rng.randn(dim).astype(np.float32)
        vec /= np.linalg.norm(vec)
        vec_list = vec.tolist()

        def embed(text: str) -> list[float]:
            return vec_list

        atlas = Atlas(embed_fn=embed)

        mermaid = "\n```mermaid\ngraph TD\n    A[Start] --> B[End]\n```\n"
        atlas.add_piece(Piece(
            id="a", title="Piece A", type=PieceType.FORWARD,
            content=f"# A\n{mermaid}",
        ))
        atlas.add_piece(Piece(
            id="b", title="Piece B", type=PieceType.FORWARD,
            content=f"# B\n{mermaid}",
        ))

        call_count = 0

        def conflicting_llm(system: str, user: str) -> str:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return json.dumps({
                    "summary": "Revenue: 1.5M",
                    "status": "success",
                    "key_outputs": {"revenue": "1.5M", "piece_id": "a"},
                })
            return json.dumps({
                "summary": "Revenue: 2.1M",
                "status": "success",
                "key_outputs": {"revenue": "2.1M", "piece_id": "b"},
            })

        graph = build_graph(atlas, llm_fn=conflicting_llm)
        app = graph.compile()

        result = app.invoke({"query": "shared query"})
        assert "CONFLICTS DETECTED" in result["merged_response"]
        assert "revenue" in result["merged_response"]
