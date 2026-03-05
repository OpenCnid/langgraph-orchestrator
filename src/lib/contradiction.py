"""Contradiction detection — LLM-based pairwise comparison of conclusions.

Compares conclusions from multiple subagents for conflicting claims.
Used by the merger before finalizing the response.
"""

import json
import logging
from collections.abc import Callable

from src.lib.models import Conclusion

logger = logging.getLogger(__name__)

ContradictionCheckFn = Callable[[str, str], str]


def detect_contradictions(
    conclusions: list[Conclusion],
    *,
    llm_fn: ContradictionCheckFn | None = None,
) -> list[dict[str, str]]:
    """Check conclusions pairwise for contradictions.

    Args:
        conclusions: List of conclusions to compare
        llm_fn: Optional LLM callable for semantic contradiction detection.
                 Takes (system_prompt, comparison_text) -> JSON response.
                 If None, uses heuristic-based detection.

    Returns:
        List of dicts with keys: piece_a, piece_b, description
    """
    if len(conclusions) < 2:
        return []

    conflicts: list[dict[str, str]] = []

    for i in range(len(conclusions)):
        for j in range(i + 1, len(conclusions)):
            a = conclusions[i]
            b = conclusions[j]

            # Skip comparisons involving failed conclusions
            if a.status in ("failed", "escalated") or b.status in ("failed", "escalated"):
                continue

            if llm_fn is not None:
                conflict = _llm_based_check(a, b, llm_fn)
            else:
                conflict = _heuristic_check(a, b)

            if conflict:
                conflicts.append(conflict)

    return conflicts


_METADATA_KEYS = {"piece_id", "piece_type"}


def _heuristic_check(a: Conclusion, b: Conclusion) -> dict[str, str] | None:
    """Basic heuristic contradiction detection.

    Checks for obvious conflicts in key_outputs (same key, different values).
    Skips metadata keys (piece_id, piece_type) which are expected to differ.
    """
    for key in a.key_outputs:
        if key in _METADATA_KEYS:
            continue
        if key in b.key_outputs and a.key_outputs[key] != b.key_outputs[key]:
            return {
                "piece_a": a.key_outputs.get("piece_id", "unknown"),
                "piece_b": b.key_outputs.get("piece_id", "unknown"),
                "description": (
                    f"Conflicting values for '{key}': "
                    f"{a.key_outputs[key]} vs {b.key_outputs[key]}"
                ),
            }
    return None


def _llm_based_check(
    a: Conclusion,
    b: Conclusion,
    llm_fn: ContradictionCheckFn,
) -> dict[str, str] | None:
    """LLM-based semantic contradiction detection."""
    system_prompt = (
        "You are checking two conclusions for contradictions. "
        "Respond with JSON: {\"contradicts\": true/false, \"description\": \"...\"}"
    )
    comparison = (
        f"Conclusion A: {a.summary}\nKey outputs: {a.key_outputs}\n\n"
        f"Conclusion B: {b.summary}\nKey outputs: {b.key_outputs}"
    )

    try:
        response = llm_fn(system_prompt, comparison)
        data = json.loads(response)
        if data.get("contradicts"):
            return {
                "piece_a": a.key_outputs.get("piece_id", "unknown"),
                "piece_b": b.key_outputs.get("piece_id", "unknown"),
                "description": data.get("description", "Contradiction detected"),
            }
    except (json.JSONDecodeError, Exception) as e:
        logger.warning("Contradiction check failed: %s", e)

    return None
