"""Token-aware text chunker with overlap."""
from dataclasses import dataclass


@dataclass
class TextChunk:
    ordinal: int
    text: str
    token_count: int


def _approx_tokens(text: str) -> int:
    # ~4 chars per token is a reasonable approximation without a full tokenizer
    return max(1, len(text) // 4)


def chunk_text(text: str, chunk_size: int = 400, overlap: int = 64) -> list[TextChunk]:
    """Split text into overlapping chunks by approximate token count."""
    if not text.strip():
        return []

    words = text.split()
    chunks: list[TextChunk] = []
    # Approximate: 1 word ≈ 1.3 tokens
    words_per_chunk = max(1, int(chunk_size / 1.3))
    words_overlap = max(0, int(overlap / 1.3))
    step = words_per_chunk - words_overlap

    i = 0
    ordinal = 0
    while i < len(words):
        window = words[i : i + words_per_chunk]
        text_chunk = " ".join(window)
        chunks.append(TextChunk(
            ordinal=ordinal,
            text=text_chunk,
            token_count=_approx_tokens(text_chunk),
        ))
        ordinal += 1
        i += step
        if i >= len(words):
            break

    return chunks
