from __future__ import annotations
import logging
from typing import List
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

class LocalEmbedder:
    """
    A wrapper class to handle loading and using a local
    sentence-transformer model for generating embeddings.
    """

    # Using a common, high-performance, lightweight model.
    # This can be changed to any model compatible with sentence-transformers.
    MODEL_NAME = 'all-MiniLM-L6-v2'

    def __init__(self):
        """
        Initializes the embedder by loading the model from Hugging Face.
        This operation may take a moment the first time it's run
        as it downloads the model.
        """
        logger.debug("Loading local embedding model: %s...", self.MODEL_NAME)
        self.model = SentenceTransformer(self.MODEL_NAME)
        self.dims = self.model.get_sentence_embedding_dimension()
        logger.debug("Local embedder initialized (dims: %s).", self.dims)

    def get_embeddings(self, texts: List[str]) -> List[List[float]]:
        """
        Generates embeddings for a list of text strings.

        Args:
            texts: A list of strings to embed.

        Returns:
            A list of embedding vectors (each as a list of floats).
        """
        if not texts:
            return []

        # We encode directly to a list of lists (of floats)
        # convert_to_numpy=False and tolist() is redundant if we don't need numpy arrays
        embeddings = self.model.encode(texts)

        # Ensure the output is a standard list of lists
        if hasattr(embeddings, 'tolist'):
            return embeddings.tolist()
        return [list(map(float, vec)) for vec in embeddings]
