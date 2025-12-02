from __future__ import annotations

import hashlib
import math
import random
from typing import List, Protocol


class EmbedderProtocol(Protocol):
    dims: int

    def get_embeddings(self, texts: List[str]) -> List[List[float]]:
        ...


class DeterministicEmbedder:
    """
    Lightweight, deterministic embedder for agentic/offline test runs.
    Produces normalized vectors derived from a stable hash of the input text.
    """

    def __init__(self, dims: int = 384):
        self.dims = dims

    def get_embeddings(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []

        embeddings: List[List[float]] = []
        for text in texts:
            seed = int(hashlib.sha256((text or "").encode("utf-8")).hexdigest(), 16)
            rng = random.Random(seed)
            vec = [rng.random() for _ in range(self.dims)]
            norm = math.sqrt(sum(v * v for v in vec)) or 1.0
            embeddings.append([v / norm for v in vec])
        return embeddings
