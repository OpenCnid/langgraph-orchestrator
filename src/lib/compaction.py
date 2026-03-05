"""Context compaction — collapse accumulated history into short digests.

Over a long session, the context window accumulates tool results,
intermediate outputs, and recovery traces. Compaction periodically:
1. Collapses history into a short digest
2. Preserves key decisions at the top (high attention position)
3. Resets the window for what comes next
"""

import logging
from typing import Any

from src.lib.config import settings
from src.lib.models import Conclusion

logger = logging.getLogger(__name__)


def estimate_token_count(text: str) -> int:
    """Rough token count estimate — ~4 chars per token for English."""
    return len(text) // 4


def needs_compaction(
    context: str,
    threshold: int | None = None,
) -> bool:
    """Check if context exceeds the compaction threshold."""
    limit = threshold if threshold is not None else settings.compaction_trigger
    return estimate_token_count(context) > limit


def compact(
    context: str,
    conclusions: list[Conclusion],
    *,
    key_decisions: list[str] | None = None,
) -> dict[str, Any]:
    """Compact context by collapsing into a digest.

    Returns dict with:
    - digest: short summary of the compacted context
    - archived_context: the full context before compaction (for memory)
    - key_decisions: preserved at top of new context
    """
    # Extract key information from conclusions
    conclusion_summaries = [
        f"- [{c.status}] {c.summary}" for c in conclusions
    ]

    # Build digest
    digest_parts: list[str] = []

    if key_decisions:
        digest_parts.append("Key decisions:\n" + "\n".join(f"- {d}" for d in key_decisions))

    if conclusion_summaries:
        digest_parts.append("Prior results:\n" + "\n".join(conclusion_summaries))

    digest = "\n\n".join(digest_parts) if digest_parts else "No prior context."

    return {
        "digest": digest,
        "archived_context": context,
        "key_decisions": key_decisions or [],
    }
