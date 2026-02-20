"""
Embedding service using nomic-embed-text-v1.5 (768 dimensions).

Lazy-loads the model on first use (~270MB download).
All vectors are L2-normalized before return.
"""

import logging
import threading
from typing import List

import numpy as np

logger = logging.getLogger(__name__)

# nomic-embed-text-v1.5 requires a task prefix for best results
_SEARCH_QUERY_PREFIX = "search_query: "
_SEARCH_DOCUMENT_PREFIX = "search_document: "

_MODEL_NAME = "nomic-ai/nomic-embed-text-v1.5"
_DIMENSIONS = 768


class EmbeddingService:
    """Local embedding generation with nomic-embed-text-v1.5.

    Thread-safe lazy model loading. Provides single and batch embedding
    with L2 normalization.
    """

    def __init__(self) -> None:
        self._model = None
        self._lock = threading.Lock()

    def _load_model(self):
        """Load model on first use. Thread-safe via lock."""
        if self._model is not None:
            return
        with self._lock:
            if self._model is not None:
                return
            from sentence_transformers import SentenceTransformer

            logger.info("Loading embedding model: %s", _MODEL_NAME)
            self._model = SentenceTransformer(
                _MODEL_NAME,
                trust_remote_code=True,
            )
            logger.info("Embedding model loaded successfully")

    @property
    def model_name(self) -> str:
        return _MODEL_NAME

    @property
    def dimensions(self) -> int:
        return _DIMENSIONS

    def embed_single(self, text: str, *, is_query: bool = True) -> List[float]:
        """Embed a single text string. Returns 768-dim L2-normalized vector.

        Args:
            text: The text to embed.
            is_query: If True, uses search_query prefix (for search queries).
                      If False, uses search_document prefix (for indexing).
        """
        self._load_model()
        prefix = _SEARCH_QUERY_PREFIX if is_query else _SEARCH_DOCUMENT_PREFIX
        prefixed = prefix + text

        embedding = self._model.encode(
            prefixed,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return embedding.tolist()

    def embed_batch(
        self,
        texts: List[str],
        *,
        batch_size: int = 32,
        is_query: bool = False,
    ) -> List[List[float]]:
        """Embed a batch of texts. Returns list of 768-dim L2-normalized vectors.

        Args:
            texts: List of texts to embed.
            batch_size: Encode batch size (controls memory usage).
            is_query: If True, uses search_query prefix. Default False
                      (batch embedding is typically for document indexing).
        """
        if not texts:
            return []

        self._load_model()
        prefix = _SEARCH_QUERY_PREFIX if is_query else _SEARCH_DOCUMENT_PREFIX
        prefixed = [prefix + t for t in texts]

        embeddings = self._model.encode(
            prefixed,
            batch_size=batch_size,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return embeddings.tolist()


# Module-level singleton
embedding_service = EmbeddingService()
