from sentence_transformers import SentenceTransformer
import numpy as np

model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")


def encode_normalized_text(text: str) -> np.ndarray:
    """
    Encode text to normalized embedding vector. 

    Primarily used to generate lookup key for normalized output and header
    values from parsed sections, for stage one of candidate selection.
    """
    if not text.strip():
        raise ValueError("Text is empty")

    normalized_text = model.encode(
        [text], normalize_embeddings=True)

    return normalized_text[0]
