"""Data models for pieces, conclusions, and routing decisions."""

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field


class PieceType(StrEnum):
    """Type of atlas piece."""

    FORWARD = "forward"
    RECOVERY = "recovery"
    SKILL = "skill"


class PieceStatus(StrEnum):
    """Lifecycle status of an atlas piece."""

    ACTIVE = "active"
    ARCHIVED = "archived"
    DRAFT = "draft"


class PieceMetadata(BaseModel):
    """Metadata block extracted from piece front matter."""

    type: PieceType
    connections: list[str] = Field(default_factory=list)
    response_shapes_handled: list[str] = Field(default_factory=list)
    status: PieceStatus = PieceStatus.ACTIVE


class Piece(BaseModel):
    """A puzzle piece — workflow, recovery anti-workflow, or skill."""

    id: str
    compact_identifier: str = ""
    title: str = ""
    type: PieceType
    status: PieceStatus = PieceStatus.ACTIVE
    connections: list[str] = Field(default_factory=list)
    response_shapes_handled: list[str] = Field(default_factory=list)
    content: str = ""
    metadata: PieceMetadata | None = None


class Conclusion(BaseModel):
    """Output contract for piece execution — crosses the isolation boundary."""

    summary: str
    status: Literal["success", "partial", "failed", "escalated"]
    key_outputs: dict[str, Any] = Field(default_factory=dict)
    diagnostics: str | None = None


class PieceMatch(BaseModel):
    """A piece matched by atlas retrieval with a similarity score."""

    piece_id: str
    score: float


class RoutingDecision(BaseModel):
    """Result of routing classification."""

    mode: Literal["A", "B", "C", "D"]
    matched_pieces: list[PieceMatch] = Field(default_factory=list)
    confidence_scores: dict[str, float] = Field(default_factory=dict)
    clarification_prompt: str | None = None


class SpawnTask(BaseModel):
    """A task to be spawned as a subagent in Mode B orchestration."""

    piece_id: str
    inputs: dict[str, Any] = Field(default_factory=dict)
    dependencies: list[str] = Field(default_factory=list)
