"""Context assembly — curate fresh context per task, not accumulated.

Each task gets a context assembled from relevant pieces, skills,
user preferences, and retrieved docs — chosen for this task, not
carried over from previous ones.
"""

import logging
from typing import Any

from src.atlas import Atlas
from src.lib.models import PieceMatch, PieceType

logger = logging.getLogger(__name__)


def assemble_context(
    query: str,
    atlas: Atlas,
    *,
    matched_pieces: list[PieceMatch] | None = None,
    user_preferences: dict[str, Any] | None = None,
    prior_digest: str | None = None,
) -> str:
    """Assemble fresh context for a task.

    Curates relevant pieces, skills, and context — not accumulated history.
    """
    parts: list[str] = []

    # Prior context digest (from compaction)
    if prior_digest:
        parts.append(f"## Prior Context\n{prior_digest}")

    # User preferences
    if user_preferences:
        pref_lines = [f"- {k}: {v}" for k, v in user_preferences.items()]
        parts.append("## User Preferences\n" + "\n".join(pref_lines))

    # Matched pieces context
    if matched_pieces:
        parts.append("## Relevant Pieces")
        for match in matched_pieces:
            piece = atlas.get_piece(match.piece_id)
            if piece:
                parts.append(
                    f"### {piece.title} (score: {match.score:.2f})\n{piece.content}"
                )

    # Load relevant skills
    skills = atlas.search(query, top_k=3, piece_type=PieceType.SKILL)
    if skills:
        parts.append("## Available Skills")
        for match in skills:
            piece = atlas.get_piece(match.piece_id)
            if piece:
                parts.append(f"### {piece.title}\n{piece.content}")

    return "\n\n".join(parts) if parts else ""
