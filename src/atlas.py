"""Atlas — piece registry with embedding retrieval and lifecycle management."""

import logging
from collections.abc import Callable
from pathlib import Path

from src.lib.config import settings
from src.lib.embeddings import EmbeddingIndex
from src.lib.models import Piece, PieceMatch, PieceStatus, PieceType
from src.lib.piece_parser import parse_piece_file

EmbedFunction = Callable[[str], list[float]]

logger = logging.getLogger(__name__)


def _make_embedding_text(piece: Piece) -> str:
    """Build the text to embed for a piece — compact identifier + title + prose."""
    parts: list[str] = []
    if piece.compact_identifier:
        parts.append(piece.compact_identifier)
    if piece.title:
        parts.append(piece.title)
    # Use full content as prose description for richer embeddings
    if piece.content:
        parts.append(piece.content)
    return " ".join(parts)


class Atlas:
    """Central registry for puzzle pieces with embedding-based retrieval."""

    def __init__(self, embed_fn: "EmbedFunction | None" = None) -> None:
        self._pieces: dict[str, Piece] = {}
        self._index = EmbeddingIndex()
        self._embed_fn = embed_fn or _default_embed_fn

    def load_from_directory(self, pieces_dir: str | Path | None = None) -> int:
        """Load all piece files from the pieces directory tree.

        Returns the number of pieces loaded.
        """
        base = Path(pieces_dir) if pieces_dir else Path(settings.pieces_dir)
        count = 0
        for md_file in sorted(base.rglob("*.md")):
            try:
                piece = parse_piece_file(md_file)
                self.add_piece(piece)
                count += 1
            except (ValueError, Exception) as e:
                logger.warning("Failed to load piece %s: %s", md_file, e)
        return count

    def add_piece(self, piece: Piece) -> None:
        """Add a piece to the atlas and index it."""
        self._pieces[piece.id] = piece
        text = _make_embedding_text(piece)
        embedding = self._embed_fn(text)
        self._index.add(piece.id, embedding)

    def get_piece(self, piece_id: str) -> Piece | None:
        """Get a piece by ID."""
        return self._pieces.get(piece_id)

    def list_pieces(
        self,
        piece_type: PieceType | None = None,
        status: PieceStatus | None = None,
    ) -> list[Piece]:
        """List pieces, optionally filtered by type and/or status."""
        result = list(self._pieces.values())
        if piece_type is not None:
            result = [p for p in result if p.type == piece_type]
        if status is not None:
            result = [p for p in result if p.status == status]
        return result

    def archive_piece(self, piece_id: str) -> bool:
        """Archive a piece (never delete). Returns True if the piece was found."""
        piece = self._pieces.get(piece_id)
        if piece is None:
            return False
        piece.status = PieceStatus.ARCHIVED
        if piece.metadata:
            piece.metadata.status = PieceStatus.ARCHIVED
        return True

    def promote_draft(self, piece_id: str) -> bool:
        """Promote a draft piece to active. Returns True if successful."""
        piece = self._pieces.get(piece_id)
        if piece is None or piece.status != PieceStatus.DRAFT:
            return False
        piece.status = PieceStatus.ACTIVE
        if piece.metadata:
            piece.metadata.status = PieceStatus.ACTIVE
        return True

    def search(
        self,
        query: str,
        top_k: int = 5,
        piece_type: PieceType | None = None,
    ) -> list[PieceMatch]:
        """Search for pieces matching a query via embedding similarity.

        Optionally filter by piece type.
        """
        embedding = self._embed_fn(query)
        raw_results = self._index.search(embedding, top_k=top_k * 3 if piece_type else top_k)

        matches: list[PieceMatch] = []
        for piece_id, score in raw_results:
            piece = self._pieces.get(piece_id)
            if piece is None:
                continue
            if piece_type is not None and piece.type != piece_type:
                continue
            if piece.status == PieceStatus.ARCHIVED:
                continue
            matches.append(PieceMatch(piece_id=piece_id, score=score))
            if len(matches) >= top_k:
                break

        return matches

    def cascade_check(self, piece_id: str) -> list[str]:
        """Find pieces that depend on the given piece via connections.

        Returns list of dependent piece IDs.
        """
        dependents: list[str] = []
        for pid, piece in self._pieces.items():
            if pid == piece_id:
                continue
            if piece_id in piece.connections:
                dependents.append(pid)
        return dependents

    @property
    def piece_count(self) -> int:
        return len(self._pieces)



def _default_embed_fn(text: str) -> list[float]:
    """Simple deterministic embedding for testing — hash-based.

    In production, replace with OpenAI/sentence-transformer embeddings.
    """
    import hashlib

    h = hashlib.sha256(text.encode()).digest()
    # Expand hash to 1536 dimensions deterministically
    vec: list[float] = []
    for i in range(1536):
        byte_idx = i % len(h)
        bit_idx = i % 8
        val = ((h[byte_idx] >> bit_idx) & 1) * 2.0 - 1.0  # -1.0 or 1.0
        vec.append(val)
    return vec
