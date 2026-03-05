"""Parse piece markdown files into structured Piece objects."""

import re
from pathlib import Path

from src.lib.models import Piece, PieceMetadata, PieceStatus, PieceType


def _parse_front_matter(content: str) -> dict[str, str | list[str]]:
    """Extract metadata fields from markdown headers and bold lines."""
    result: dict[str, str | list[str]] = {}

    # Extract title from first H1
    title_match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
    if title_match:
        result["title"] = title_match.group(1).strip()

    # Extract bold key-value pairs like **Type:** forward
    for match in re.finditer(r"\*\*(\w[\w\s]*?):\*\*\s*(.+)", content):
        key = match.group(1).strip().lower().replace(" ", "_")
        value = match.group(2).strip()
        # Parse list values like [item1, item2]
        if value.startswith("[") and value.endswith("]"):
            items = [item.strip() for item in value[1:-1].split(",") if item.strip()]
            result[key] = items
        else:
            result[key] = value

    return result


def _extract_mermaid(content: str) -> str | None:
    """Extract the mermaid code block from markdown."""
    match = re.search(r"```mermaid\s*\n(.*?)```", content, re.DOTALL)
    return match.group(1).strip() if match else None


def _extract_prose(content: str) -> str:
    """Extract prose content outside of the mermaid block."""
    # Remove the mermaid block
    without_mermaid = re.sub(r"```mermaid\s*\n.*?```", "", content, flags=re.DOTALL)
    return without_mermaid.strip()


def parse_piece_file(file_path: Path) -> Piece:
    """Parse a piece markdown file into a Piece model.

    Raises ValueError if a workflow/recovery piece has no mermaid diagram.
    Skills are prompt files and do not require mermaid.
    """
    content = file_path.read_text(encoding="utf-8")
    front = _parse_front_matter(content)
    mermaid = _extract_mermaid(content)

    # Derive piece ID from filename without extension
    piece_id = file_path.stem

    # Parse type early — needed to decide if mermaid is required
    raw_type = front.get("type", "")
    if isinstance(raw_type, list):
        raw_type = raw_type[0] if raw_type else ""
    piece_type = PieceType(raw_type.lower()) if raw_type else _infer_type_from_path(file_path)

    # Skills are prompt files — mermaid is optional. Workflows and recovery require it.
    if mermaid is None and piece_type != PieceType.SKILL:
        raise ValueError(f"Piece {file_path} has no mermaid diagram")

    # Parse status
    raw_status = front.get("status", "active")
    if isinstance(raw_status, list):
        raw_status = raw_status[0] if raw_status else "active"
    status = PieceStatus(raw_status.lower())

    # Parse connections
    connections = front.get("connections", [])
    if isinstance(connections, str):
        connections = [connections]

    # Parse response shapes handled
    response_shapes = front.get("response_shapes_handled", [])
    if isinstance(response_shapes, str):
        response_shapes = [response_shapes]

    # Compact identifier
    compact_id = front.get("compact_identifier", "")
    if isinstance(compact_id, list):
        compact_id = compact_id[0] if compact_id else ""

    # Title
    title = front.get("title", "")
    if isinstance(title, list):
        title = title[0] if title else ""

    metadata = PieceMetadata(
        type=piece_type,
        connections=connections,
        response_shapes_handled=response_shapes,
        status=status,
    )

    return Piece(
        id=piece_id,
        compact_identifier=compact_id,
        title=title,
        type=piece_type,
        status=status,
        connections=connections,
        response_shapes_handled=response_shapes,
        content=content,
        metadata=metadata,
    )


def _infer_type_from_path(file_path: Path) -> PieceType:
    """Infer piece type from directory location."""
    parts = file_path.parts
    if "recovery" in parts:
        return PieceType.RECOVERY
    if "skills" in parts:
        return PieceType.SKILL
    return PieceType.FORWARD
