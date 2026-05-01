"""Hybrid retrieval: keyword LIKE + vector cosine, fused with RRF."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from pce.config import settings

log = structlog.get_logger()

RRF_K = 60


@dataclass
class SearchResult:
    item_id: str
    title: str
    path: str | None
    url: str | None
    source: str
    snippet: str
    score: float
    chunks: list[str] = field(default_factory=list)  # top chunk texts for context assembly


async def keyword_search(query: str, session: AsyncSession, limit: int = 30) -> list[tuple[str, float]]:
    """Simple LIKE-based keyword search over title and body."""
    terms = query.split()
    if not terms:
        return []

    # Score by number of terms that match
    clauses = " OR ".join(["title LIKE :pat OR body LIKE :pat"] * len(terms))
    sql = text(f"SELECT id FROM items WHERE {clauses} LIMIT :limit")
    params = {f"pat": f"%{terms[0]}%", "limit": limit}
    # For multiple terms, score each individually and sum
    scores: dict[str, float] = {}
    for term in terms:
        pat = f"%{term}%"
        result = await session.execute(
            text("SELECT id FROM items WHERE title LIKE :pat OR body LIKE :pat LIMIT :limit"),
            {"pat": pat, "limit": limit},
        )
        for (item_id,) in result.fetchall():
            scores[item_id] = scores.get(item_id, 0.0) + 1.0

    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return ranked[:limit]


async def vector_search(query: str, session: AsyncSession, limit: int = 30) -> list[tuple[str, float]]:
    """Cosine similarity search over embedded chunks. Returns [(item_id, score)]."""
    from pce.ingestion.embedder import get_model
    model = get_model()
    q_vec = np.array(next(model.embed([query])))

    result = await session.execute(
        text("SELECT item_id, embedding FROM chunks WHERE embedded = 1 AND embedding IS NOT NULL LIMIT 5000")
    )
    rows = result.fetchall()

    if not rows:
        return []

    scores: dict[str, float] = {}
    for item_id, embedding in rows:
        vec = np.array(embedding)
        norm = np.linalg.norm(q_vec) * np.linalg.norm(vec)
        if norm == 0:
            continue
        sim = float(np.dot(q_vec, vec) / norm)
        scores[item_id] = max(scores.get(item_id, -1.0), sim)

    return sorted(scores.items(), key=lambda x: x[1], reverse=True)[:limit]


def _rrf(ranked_lists: list[list[tuple[str, float]]], k: int = RRF_K) -> list[tuple[str, float]]:
    fused: dict[str, float] = {}
    for ranked in ranked_lists:
        for rank, (item_id, _) in enumerate(ranked, start=1):
            fused[item_id] = fused.get(item_id, 0.0) + 1.0 / (k + rank)
    return sorted(fused.items(), key=lambda x: x[1], reverse=True)


async def _fetch_items(item_ids: list[str], session: AsyncSession) -> dict[str, dict]:
    if not item_ids:
        return {}
    placeholders = ",".join(f":id{i}" for i in range(len(item_ids)))
    result = await session.execute(
        text(f"SELECT id, title, path, url, source, body FROM items WHERE id IN ({placeholders})"),
        {f"id{i}": v for i, v in enumerate(item_ids)},
    )
    return {row[0]: dict(zip(["id", "title", "path", "url", "source", "body"], row)) for row in result.fetchall()}


async def _fetch_top_chunks(item_id: str, session: AsyncSession, n: int = 3) -> list[str]:
    result = await session.execute(
        text("SELECT text FROM chunks WHERE item_id = :iid ORDER BY ordinal LIMIT :n"),
        {"iid": item_id, "n": n},
    )
    return [row[0] for row in result.fetchall()]


async def hybrid_search(query: str, session: AsyncSession, top_k: int | None = None) -> list[SearchResult]:
    k = top_k or settings.retrieval_top_k

    kw_results = await keyword_search(query, session, limit=30)
    vec_results = await vector_search(query, session, limit=30)

    fused = _rrf([kw_results, vec_results])[:k]
    if not fused:
        return []

    item_ids = [item_id for item_id, _ in fused]
    score_map = dict(fused)
    items = await _fetch_items(item_ids, session)

    out = []
    for item_id in item_ids:
        row = items.get(item_id)
        if not row:
            continue
        body = row["body"] or ""
        snippet = body[:300].replace("\n", " ")
        chunks = await _fetch_top_chunks(item_id, session)
        out.append(SearchResult(
            item_id=item_id,
            title=row["title"] or "",
            path=row["path"],
            url=row["url"],
            source=row["source"],
            snippet=snippet,
            score=score_map[item_id],
            chunks=chunks,
        ))

    log.info("search_complete", query=query, results=len(out))
    return out
