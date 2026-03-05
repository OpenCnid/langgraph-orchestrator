"""Tests for memory — execution history, user profile, session summary, review cycle."""

import hashlib
import tempfile
from pathlib import Path

from src.atlas import Atlas
from src.lib.models import Piece, PieceType
from src.memory import MemoryStore, review_cycle


def _deterministic_embed(text: str) -> list[float]:
    h = hashlib.sha256(text.encode()).digest()
    vec: list[float] = []
    for i in range(1536):
        byte_idx = i % len(h)
        bit_idx = i % 8
        val = ((h[byte_idx] >> bit_idx) & 1) * 2.0 - 1.0
        vec.append(val)
    return vec


class TestExecutionHistory:
    """Execution history records both successes and failures."""

    def test_record_success(self) -> None:
        mem = MemoryStore()
        mem.record_execution(
            query="look up record",
            mode="A",
            piece_ids=["lookup"],
            status="success",
            summary="Found 3 records",
        )
        history = mem.get_history()
        assert len(history) == 1
        assert history[0].status == "success"

    def test_record_failure(self) -> None:
        mem = MemoryStore()
        mem.record_execution(
            query="broken query",
            mode="B",
            piece_ids=["alpha", "beta"],
            status="failed",
            summary="Alpha failed",
            diagnostics="Data source unavailable",
        )
        failures = mem.get_failures()
        assert len(failures) == 1
        assert failures[0].diagnostics == "Data source unavailable"

    def test_failures_never_deleted(self) -> None:
        """Failures are archived, never deleted."""
        mem = MemoryStore()
        mem.record_execution(
            query="fail", mode="A", piece_ids=["x"],
            status="failed", summary="Error",
        )
        mem.archive_record(0)

        # Archived but still accessible
        all_records = mem.get_history(include_archived=True)
        assert len(all_records) == 1
        assert all_records[0].archived is True

        # Not in default view
        active = mem.get_history()
        assert len(active) == 0

        # Still in failures list
        failures = mem.get_failures()
        assert len(failures) == 1

    def test_mixed_history(self) -> None:
        mem = MemoryStore()
        mem.record_execution(
            query="q1", mode="A", piece_ids=["a"],
            status="success", summary="OK",
        )
        mem.record_execution(
            query="q2", mode="B", piece_ids=["b"],
            status="failed", summary="Error",
        )
        mem.record_execution(
            query="q3", mode="A", piece_ids=["c"],
            status="success", summary="Done",
        )
        assert len(mem.get_history()) == 3
        assert len(mem.get_failures()) == 1


class TestUserProfile:
    """User profile captures preferences and observed patterns."""

    def test_set_preference(self) -> None:
        mem = MemoryStore()
        mem.set_preference("output_format", "json")
        profile = mem.get_profile()
        assert profile.explicit_preferences["output_format"] == "json"

    def test_observe_pattern(self) -> None:
        mem = MemoryStore()
        mem.observe_pattern("prefers_verbose_output", True)
        profile = mem.get_profile()
        assert profile.observed_patterns["prefers_verbose_output"] is True

    def test_preference_overwrite(self) -> None:
        mem = MemoryStore()
        mem.set_preference("format", "text")
        mem.set_preference("format", "json")
        assert mem.get_profile().explicit_preferences["format"] == "json"


class TestSessionSummary:
    """Session summaries are under 1k tokens."""

    def test_summary_under_1k_tokens(self) -> None:
        mem = MemoryStore()
        for i in range(20):
            mem.record_execution(
                query=f"query {i}", mode="A", piece_ids=[f"p{i}"],
                status="success", summary=f"Result {i}",
            )
        summary = mem.generate_session_summary()
        # ~4 chars per token, 1000 tokens = 4000 chars
        assert len(summary) <= 4000

    def test_summary_includes_recent_history(self) -> None:
        mem = MemoryStore()
        mem.record_execution(
            query="test", mode="A", piece_ids=["x"],
            status="success", summary="Found records",
        )
        summary = mem.generate_session_summary()
        assert "Found records" in summary

    def test_summary_includes_failures(self) -> None:
        mem = MemoryStore()
        mem.record_execution(
            query="fail", mode="B", piece_ids=["y"],
            status="failed", summary="Broke", diagnostics="DB down",
        )
        summary = mem.generate_session_summary()
        assert "Broke" in summary
        assert "DB down" in summary

    def test_summary_includes_preferences(self) -> None:
        mem = MemoryStore()
        mem.set_preference("output", "json")
        summary = mem.generate_session_summary()
        assert "output" in summary
        assert "json" in summary

    def test_empty_summary(self) -> None:
        mem = MemoryStore()
        summary = mem.generate_session_summary()
        assert "No prior session data" in summary


class TestMemoryPersistence:
    """Memory saves and loads from disk."""

    def test_save_and_load(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test_memory"

            # Save
            mem1 = MemoryStore(storage_path=path)
            mem1.record_execution(
                query="test", mode="A", piece_ids=["x"],
                status="success", summary="OK",
            )
            mem1.set_preference("format", "json")
            mem1.save()

            # Load
            mem2 = MemoryStore(storage_path=path)
            mem2.load()

            assert len(mem2.get_history()) == 1
            assert mem2.get_history()[0].summary == "OK"
            assert mem2.get_profile().explicit_preferences["format"] == "json"


class TestReviewCycle:
    """Review cycle records execution and checks for cascade impacts."""

    def test_review_records_execution(self) -> None:
        mem = MemoryStore()
        atlas = Atlas(embed_fn=_deterministic_embed)

        result = review_cycle(
            mem, atlas,
            query="test", mode="A", piece_ids=["x"],
            status="success", summary="Done",
        )
        assert result["recorded"]
        assert len(mem.get_history()) == 1

    def test_review_flags_cascade_on_failure(self) -> None:
        mem = MemoryStore()
        atlas = Atlas(embed_fn=_deterministic_embed)

        # Add pieces with connections
        atlas.add_piece(Piece(
            id="base", title="Base", type=PieceType.FORWARD,
            content="base content",
        ))
        atlas.add_piece(Piece(
            id="dependent", title="Dependent", type=PieceType.FORWARD,
            content="depends on base", connections=["base"],
        ))

        result = review_cycle(
            mem, atlas,
            query="test", mode="A", piece_ids=["base"],
            status="failed", summary="Base failed",
        )
        assert "cascade_flagged" in result
        assert "dependent" in result["cascade_flagged"]

    def test_review_no_cascade_on_success(self) -> None:
        mem = MemoryStore()
        atlas = Atlas(embed_fn=_deterministic_embed)

        result = review_cycle(
            mem, atlas,
            query="test", mode="A", piece_ids=["x"],
            status="success", summary="OK",
        )
        assert "cascade_flagged" not in result
