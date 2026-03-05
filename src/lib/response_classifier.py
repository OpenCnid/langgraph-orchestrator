"""Response shape classification — categorize tool responses for recovery routing."""

from enum import StrEnum

from pydantic import BaseModel


class ResponseShapeType(StrEnum):
    """Categories of tool response shapes for recovery matching."""

    VALIDATION = "validation"
    PARTIAL = "partial"
    CAPACITY = "capacity"
    CONSTRAINT = "constraint"
    SHAPE_MISMATCH = "shape_mismatch"
    UNKNOWN = "unknown"


class ResponseShape(BaseModel):
    """Classified response shape with metadata for recovery lookup."""

    shape_type: ResponseShapeType
    description: str
    raw_response: str
    fields_flagged: list[str] | None = None
    progress: dict[str, int] | None = None  # e.g. {"processed": 2, "total": 5}


# Keyword patterns for heuristic classification
_VALIDATION_KEYWORDS = [
    "invalid", "validation", "required field", "format error",
    "must be", "expected", "constraint violation",
]
_PARTIAL_KEYWORDS = [
    "partial", "incomplete", "processed", "of", "remaining",
    "batch", "truncated",
]
_CAPACITY_KEYWORDS = [
    "rate limit", "timeout", "too many requests", "429",
    "503", "retry after", "throttle", "capacity",
]
_CONSTRAINT_KEYWORDS = [
    "permission", "denied", "unauthorized", "forbidden", "403",
    "policy", "not allowed", "access denied",
]
_SHAPE_MISMATCH_KEYWORDS = [
    "unexpected", "schema", "type error", "mismatch",
    "incompatible", "wrong format",
]


def classify_response(response_text: str) -> ResponseShape:
    """Classify a tool response into a response shape category.

    Uses keyword-based heuristics. For production, this could be
    augmented with LLM-based classification.
    """
    lower = response_text.lower()

    # Check shape_mismatch before validation — "unexpected" and "schema"
    # are more specific than generic validation keywords
    if _matches_keywords(lower, _SHAPE_MISMATCH_KEYWORDS):
        return ResponseShape(
            shape_type=ResponseShapeType.SHAPE_MISMATCH,
            description="Response shape doesn't match expected format",
            raw_response=response_text,
        )

    if _matches_keywords(lower, _VALIDATION_KEYWORDS):
        return ResponseShape(
            shape_type=ResponseShapeType.VALIDATION,
            description="Response indicates validation failure on specific fields",
            raw_response=response_text,
        )

    if _matches_keywords(lower, _CAPACITY_KEYWORDS):
        return ResponseShape(
            shape_type=ResponseShapeType.CAPACITY,
            description="Response indicates rate limiting or capacity constraint",
            raw_response=response_text,
        )

    if _matches_keywords(lower, _CONSTRAINT_KEYWORDS):
        return ResponseShape(
            shape_type=ResponseShapeType.CONSTRAINT,
            description="Response indicates permission or policy constraint",
            raw_response=response_text,
        )

    if _matches_keywords(lower, _PARTIAL_KEYWORDS):
        return ResponseShape(
            shape_type=ResponseShapeType.PARTIAL,
            description="Response indicates partial completion",
            raw_response=response_text,
        )

    return ResponseShape(
        shape_type=ResponseShapeType.UNKNOWN,
        description="Response shape not recognized — may need a new recovery piece",
        raw_response=response_text,
    )


def _matches_keywords(text: str, keywords: list[str]) -> bool:
    """Check if text contains any of the keywords."""
    return any(kw in text for kw in keywords)
