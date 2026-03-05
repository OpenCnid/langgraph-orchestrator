"""Memory — execution history and user profile persistence.

Two kinds of signal:
- Execution history: what worked/broke (proven routes + failures)
- User profile: how the user prefers to work (explicit + observed)

Failures are archived, never deleted — a removed failure record means
the system encounters the same situation with no warning.
"""

import json
import logging
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class ExecutionRecord(BaseModel):
    """A single execution outcome — success or failure."""

    query: str
    mode: str  # A, B, C, D
    piece_ids: list[str] = Field(default_factory=list)
    status: str  # success, partial, failed, escalated
    summary: str
    diagnostics: str | None = None
    archived: bool = False


class UserProfile(BaseModel):
    """User preferences and observed patterns."""

    explicit_preferences: dict[str, Any] = Field(default_factory=dict)
    observed_patterns: dict[str, Any] = Field(default_factory=dict)


class MemoryStore:
    """Persistent memory for execution history and user profile."""

    def __init__(self, storage_path: Path | None = None) -> None:
        self._storage_path = storage_path or Path(".memory")
        self._history: list[ExecutionRecord] = []
        self._profile = UserProfile()

    def record_execution(
        self,
        query: str,
        mode: str,
        piece_ids: list[str],
        status: str,
        summary: str,
        diagnostics: str | None = None,
    ) -> None:
        """Log an execution outcome — both successes and failures."""
        record = ExecutionRecord(
            query=query,
            mode=mode,
            piece_ids=piece_ids,
            status=status,
            summary=summary,
            diagnostics=diagnostics,
        )
        self._history.append(record)

    def get_history(
        self,
        *,
        include_archived: bool = False,
    ) -> list[ExecutionRecord]:
        """Get execution history. Failures are always included (archived, not deleted)."""
        if include_archived:
            return list(self._history)
        return [r for r in self._history if not r.archived]

    def get_failures(self) -> list[ExecutionRecord]:
        """Get all failure records (never deleted)."""
        return [
            r for r in self._history
            if r.status in ("failed", "escalated")
        ]

    def archive_record(self, index: int) -> bool:
        """Archive a record — mark as archived but never delete."""
        if 0 <= index < len(self._history):
            self._history[index].archived = True
            return True
        return False

    def set_preference(self, key: str, value: Any) -> None:
        """Set an explicit user preference."""
        self._profile.explicit_preferences[key] = value

    def observe_pattern(self, key: str, value: Any) -> None:
        """Record an observed user pattern."""
        self._profile.observed_patterns[key] = value

    def get_profile(self) -> UserProfile:
        """Get the current user profile."""
        return self._profile

    def generate_session_summary(self, max_tokens: int = 1000) -> str:
        """Produce a session summary under ~1k tokens for next session start.

        Summarizes recent history and user profile.
        """
        parts: list[str] = []

        # Recent execution history
        recent = self._history[-10:]  # Last 10 records
        if recent:
            parts.append("## Recent Executions")
            for r in recent:
                status_marker = "+" if r.status == "success" else "-"
                parts.append(f"  {status_marker} [{r.mode}] {r.summary}")

        # Failure patterns
        failures = self.get_failures()
        if failures:
            parts.append(f"## Failures ({len(failures)} total)")
            for f in failures[-5:]:  # Last 5 failures
                parts.append(f"  - {f.summary}: {f.diagnostics or 'no diagnostics'}")

        # User preferences
        if self._profile.explicit_preferences:
            parts.append("## Preferences")
            for k, v in self._profile.explicit_preferences.items():
                parts.append(f"  - {k}: {v}")

        summary = "\n".join(parts) if parts else "No prior session data."

        # Rough truncation to token limit (~4 chars/token)
        max_chars = max_tokens * 4
        if len(summary) > max_chars:
            summary = summary[:max_chars] + "\n  [truncated]"

        return summary

    def save(self) -> None:
        """Save memory to disk."""
        self._storage_path.mkdir(parents=True, exist_ok=True)

        history_path = self._storage_path / "history.json"
        history_data = [r.model_dump() for r in self._history]
        history_path.write_text(json.dumps(history_data, indent=2))

        profile_path = self._storage_path / "profile.json"
        profile_path.write_text(self._profile.model_dump_json(indent=2))

    def load(self) -> None:
        """Load memory from disk."""
        history_path = self._storage_path / "history.json"
        if history_path.exists():
            data = json.loads(history_path.read_text())
            self._history = [ExecutionRecord(**r) for r in data]

        profile_path = self._storage_path / "profile.json"
        if profile_path.exists():
            self._profile = UserProfile.model_validate_json(
                profile_path.read_text()
            )


def review_cycle(
    memory: MemoryStore,
    atlas: Any,  # Atlas type — avoid circular import
    query: str,
    mode: str,
    piece_ids: list[str],
    status: str,
    summary: str,
    diagnostics: str | None = None,
) -> dict[str, Any]:
    """Execute the review cycle after an outcome.

    1. Classify — success or failure
    2. Write memory — record execution
    3. For failures: check if atlas pieces need updating
    4. Return review results
    """
    # Record execution
    memory.record_execution(
        query=query,
        mode=mode,
        piece_ids=piece_ids,
        status=status,
        summary=summary,
        diagnostics=diagnostics,
    )

    result: dict[str, Any] = {"recorded": True, "status": status}

    # For failures, check if pieces should be archived
    if status in ("failed", "escalated"):
        cascade_results: list[str] = []
        for pid in piece_ids:
            dependents = atlas.cascade_check(pid)
            if dependents:
                cascade_results.extend(dependents)
        if cascade_results:
            result["cascade_flagged"] = cascade_results

    return result
