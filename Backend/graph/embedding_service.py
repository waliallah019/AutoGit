"""Embedding service with local model caching."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field


@dataclass
class EmbeddingService:
    model_name: str = "all-MiniLM-L6-v2"
    _model: object | None = None
    _cache: dict[str, list[float]] = field(default_factory=dict)

    @property
    def available(self) -> bool:
        self._ensure_model()
        return self._model is not None

    def _ensure_model(self) -> None:
        if self._model is not None:
            return
        try:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self.model_name)
        except Exception:
            self._model = None

    @staticmethod
    def _key(text: str) -> str:
        return hashlib.sha1(text.encode("utf-8", errors="ignore")).hexdigest()

    def embed_text(self, text: str) -> list[float]:
        clean = (text or "").strip()
        if not clean:
            return []
        key = self._key(clean)
        if key in self._cache:
            return self._cache[key]

        self._ensure_model()
        if self._model is None:
            return []

        vec = self._model.encode(clean, normalize_embeddings=True).tolist()
        self._cache[key] = vec
        return vec

