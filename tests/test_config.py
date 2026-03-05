"""Tests for configuration module — P1.3."""

import pytest

from src.lib.config import Settings


class TestSettings:
    def test_defaults(self) -> None:
        s = Settings()
        assert s.confidence_high == 0.85
        assert s.confidence_moderate == 0.60
        assert s.retry_limit == 3
        assert s.compaction_trigger == 6000
        assert s.embedding_model == "text-embedding-3-small"
        assert s.llm_model == "gpt-4o"
        assert s.pieces_dir == "pieces"

    def test_overrides_from_env(self, monkeypatch: "pytest.MonkeyPatch") -> None:
        monkeypatch.setenv("ORCH_CONFIDENCE_HIGH", "0.90")
        monkeypatch.setenv("ORCH_RETRY_LIMIT", "5")
        s = Settings()
        assert s.confidence_high == 0.90
        assert s.retry_limit == 5
