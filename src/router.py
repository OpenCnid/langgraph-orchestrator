"""Router — classifies queries into modes A/B/C/D based on atlas retrieval confidence."""

import logging

from src.atlas import Atlas
from src.lib.config import settings
from src.lib.models import PieceMatch, RoutingDecision

logger = logging.getLogger(__name__)


def classify_query(
    query: str,
    atlas: Atlas,
    *,
    high_threshold: float | None = None,
    moderate_threshold: float | None = None,
) -> RoutingDecision:
    """Classify a query into routing mode A, B, C, or D.

    Mode selection logic:
    - A (Librarian): Single piece above high threshold, clearly dominant
    - B (Orchestrator): Multiple pieces above moderate threshold
    - C (Cartographer): No piece above moderate threshold — nothing to work with
    - D (Clarifier): Multiple weak matches exist but none above moderate — ambiguous

    The distinction between C and D: C means the atlas has nothing relevant.
    D means the atlas has candidates but can't determine which — needs human help.
    """
    high = high_threshold if high_threshold is not None else settings.confidence_high
    moderate = (
        moderate_threshold if moderate_threshold is not None else settings.confidence_moderate
    )

    matches = atlas.search(query, top_k=10)
    confidence_scores = {m.piece_id: m.score for m in matches}

    strong_matches = [m for m in matches if m.score >= high]
    moderate_matches = [m for m in matches if m.score >= moderate]
    weak_matches = [m for m in matches if m.score < moderate]

    # Mode A: single dominant match above high threshold
    if len(strong_matches) == 1 and (
        len(moderate_matches) == 1 or strong_matches[0].score > moderate_matches[1].score * 1.2
        if len(moderate_matches) > 1
        else True
    ):
        return RoutingDecision(
            mode="A",
            matched_pieces=[strong_matches[0]],
            confidence_scores=confidence_scores,
        )

    # Mode A also: multiple strong matches but one clearly dominates
    if len(strong_matches) >= 2:
        # If the top match significantly outscores the rest, still Mode A
        top = strong_matches[0]
        second = strong_matches[1]
        if top.score >= second.score * 1.2:
            return RoutingDecision(
                mode="A",
                matched_pieces=[top],
                confidence_scores=confidence_scores,
            )
        # Otherwise multiple strong matches → Mode B
        return RoutingDecision(
            mode="B",
            matched_pieces=strong_matches,
            confidence_scores=confidence_scores,
        )

    # Mode B: multiple matches above moderate threshold
    if len(moderate_matches) >= 2:
        return RoutingDecision(
            mode="B",
            matched_pieces=moderate_matches,
            confidence_scores=confidence_scores,
        )

    # Mode B: one strong match (already handled above) shouldn't reach here,
    # but one moderate match alone → Mode A (best available match)
    if len(moderate_matches) == 1:
        return RoutingDecision(
            mode="A",
            matched_pieces=moderate_matches,
            confidence_scores=confidence_scores,
        )

    # Below moderate threshold — distinguish C vs D
    # Mode D: multiple weak matches exist → ambiguous, ask human
    if len(weak_matches) >= 2:
        return RoutingDecision(
            mode="D",
            matched_pieces=weak_matches,
            confidence_scores=confidence_scores,
            clarification_prompt=_generate_clarification_prompt(query, weak_matches),
        )

    # Mode C: no meaningful matches — nothing in the atlas for this
    return RoutingDecision(
        mode="C",
        matched_pieces=weak_matches,
        confidence_scores=confidence_scores,
    )


def reroute_after_clarification(
    narrowed_query: str,
    atlas: Atlas,
    *,
    high_threshold: float | None = None,
    moderate_threshold: float | None = None,
) -> RoutingDecision:
    """Re-classify after human clarification. Guaranteed non-D result.

    If classification would return Mode D again, force Mode C instead
    to prevent infinite clarification loops.
    """
    decision = classify_query(
        narrowed_query,
        atlas,
        high_threshold=high_threshold,
        moderate_threshold=moderate_threshold,
    )
    if decision.mode == "D":
        logger.info("Re-routing would produce Mode D again; forcing Mode C to break loop")
        return RoutingDecision(
            mode="C",
            matched_pieces=decision.matched_pieces,
            confidence_scores=decision.confidence_scores,
        )
    return decision


def _generate_clarification_prompt(query: str, weak_matches: list[PieceMatch]) -> str:
    """Generate a clarification prompt listing the ambiguous matches."""
    piece_ids = [m.piece_id for m in weak_matches[:5]]
    pieces_list = ", ".join(piece_ids)
    return (
        f"Your query \"{query}\" matched multiple areas but none with high confidence. "
        f"Possible matches: {pieces_list}. "
        f"Could you clarify which area you're asking about?"
    )
