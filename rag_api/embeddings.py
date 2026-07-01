from functools import lru_cache
from typing import List, Optional

from sentence_transformers import SentenceTransformer

from rag_api.config import EMBEDDING_MODEL


@lru_cache(maxsize=1)
def load_model() -> SentenceTransformer:
    """
    Load the embedding model only once.
    """
    print(f"Loading embedding model: {EMBEDDING_MODEL}")

    model = SentenceTransformer(
        EMBEDDING_MODEL
    )

    return model


def get_embedding(text: str) -> Optional[List[float]]:
    """
    Generate embedding for a chunk of text.

    Returns
    -------
    List[float]
        Embedding vector
    """

    if not text or not text.strip():
        return None

    try:

        model = load_model()

        embedding = model.encode(
            text,
            convert_to_numpy=True,
            normalize_embeddings=True
        )

        return embedding.tolist()

    except Exception as e:

        print("Embedding error:", e)

        return None