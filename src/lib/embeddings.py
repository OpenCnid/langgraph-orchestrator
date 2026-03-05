"""Embedding index for atlas piece retrieval using FAISS."""

import logging

import faiss
import numpy as np

logger = logging.getLogger(__name__)


class EmbeddingIndex:
    """FAISS-based embedding index for piece similarity search."""

    def __init__(self, dimension: int = 1536) -> None:
        self._dimension = dimension
        self._index = faiss.IndexFlatIP(dimension)  # cosine sim on normalized vecs
        self._id_map: list[str] = []

    @property
    def size(self) -> int:
        return self._index.ntotal

    def add(self, piece_id: str, embedding: list[float]) -> None:
        """Add a piece embedding to the index."""
        vec = np.array([embedding], dtype=np.float32)
        faiss.normalize_L2(vec)
        self._index.add(vec)
        self._id_map.append(piece_id)

    def remove(self, piece_id: str) -> None:
        """Remove a piece from the index by rebuilding without it.

        FAISS IndexFlatIP doesn't support removal, so we rebuild.
        """
        if piece_id not in self._id_map:
            return

        idx = self._id_map.index(piece_id)
        # Reconstruct all vectors
        all_vecs = np.zeros((self._index.ntotal, self._dimension), dtype=np.float32)
        for i in range(self._index.ntotal):
            all_vecs[i] = self._index.reconstruct(i)

        # Remove the target
        keep_mask = list(range(self._index.ntotal))
        keep_mask.pop(idx)
        self._id_map.pop(idx)

        # Rebuild index
        self._index = faiss.IndexFlatIP(self._dimension)
        if keep_mask:
            self._index.add(all_vecs[keep_mask])

    def search(self, query_embedding: list[float], top_k: int = 5) -> list[tuple[str, float]]:
        """Search for the most similar pieces.

        Returns list of (piece_id, score) sorted by descending similarity.
        """
        if self._index.ntotal == 0:
            return []

        vec = np.array([query_embedding], dtype=np.float32)
        faiss.normalize_L2(vec)
        k = min(top_k, self._index.ntotal)
        scores, indices = self._index.search(vec, k)

        results: list[tuple[str, float]] = []
        for score, idx in zip(scores[0], indices[0]):
            if idx >= 0 and idx < len(self._id_map):
                results.append((self._id_map[idx], float(score)))
        return results

    def clear(self) -> None:
        """Clear the index."""
        self._index = faiss.IndexFlatIP(self._dimension)
        self._id_map.clear()
