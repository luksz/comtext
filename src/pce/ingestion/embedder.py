"""Embedding worker: batched, content-hash dedup, runs as APScheduler job."""
import structlog
from fastembed import TextEmbedding
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from pce.config import settings
from pce.db.models import Chunk
from pce.db.session import get_session_factory

log = structlog.get_logger()

_model: TextEmbedding | None = None

# Stored as JSON in a separate table; for simplicity we pack floats into
# a JSON column on the Chunk row (swap for sqlite-vec later).


def get_model() -> TextEmbedding:
    global _model
    if _model is None:
        log.info("loading_embed_model", model=settings.embed_model)
        _model = TextEmbedding(model_name=settings.embed_model)
    return _model


async def embed_pending(batch_size: int | None = None) -> int:
    """Embed all chunks that haven't been embedded yet. Returns count processed."""
    bs = batch_size or settings.embed_batch_size
    factory = get_session_factory()

    async with factory() as session:
        result = await session.execute(
            select(Chunk).where(Chunk.embedded == False).limit(bs)  # noqa: E712
        )
        chunks = result.scalars().all()

    if not chunks:
        return 0

    model = get_model()
    texts = [c.text for c in chunks]
    embeddings = list(model.embed(texts))

    async with factory() as session:
        for chunk, vec in zip(chunks, embeddings):
            await session.execute(
                update(Chunk)
                .where(Chunk.id == chunk.id)
                .values(embedded=True, embedding=vec.tolist())
            )
        await session.commit()

    log.info("embedded_chunks", count=len(chunks))
    return len(chunks)
