from pathlib import Path

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from pce.db.session import get_db
from pce.retrieval.search import hybrid_search

log = structlog.get_logger()
router = APIRouter()


class SearchResponse(BaseModel):
    results: list[dict]
    total: int


class IngestRequest(BaseModel):
    directory: str


class IngestResponse(BaseModel):
    ingested: int


class AskRequest(BaseModel):
    question: str
    top_k: int = 10


class AskResponse(BaseModel):
    answer: str
    sources: list[dict]
    backend: str
    latency_ms: int


@router.get("/healthz")
async def healthz():
    return {"status": "ok"}


@router.get("/search", response_model=SearchResponse)
async def search(
    q: str = Query(..., min_length=1),
    top_k: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    results = await hybrid_search(q, db, top_k=top_k)
    return SearchResponse(
        results=[
            {
                "item_id": r.item_id,
                "title": r.title,
                "source": r.source,
                "path": r.path,
                "url": r.url,
                "snippet": r.snippet,
                "score": round(r.score, 4),
            }
            for r in results
        ],
        total=len(results),
    )


@router.post("/ingest", response_model=IngestResponse)
async def ingest(body: IngestRequest):
    from pce.connectors.files import scan_directory
    directory = Path(body.directory)
    if not directory.exists():
        raise HTTPException(status_code=400, detail=f"Directory not found: {directory}")
    count = await scan_directory(directory)
    return IngestResponse(ingested=count)


@router.post("/embed")
async def embed_pending():
    from pce.ingestion.embedder import embed_pending as _embed
    count = await _embed()
    return {"embedded": count}


@router.post("/ask", response_model=AskResponse)
async def ask(body: AskRequest, db: AsyncSession = Depends(get_db)):
    from pce.llm.router import ask as llm_ask

    results = await hybrid_search(body.question, db, top_k=body.top_k)
    if not results:
        return AskResponse(
            answer="I couldn't find any relevant context to answer that question.",
            sources=[],
            backend="none",
            latency_ms=0,
        )

    sources = [
        {
            "item_id": r.item_id,
            "title": r.title,
            "source": r.source,
            "path": r.path,
            "url": r.url,
            "snippet": r.snippet,
            "chunks": r.chunks,
        }
        for r in results
    ]

    llm_resp = await llm_ask(body.question, sources)

    return AskResponse(
        answer=llm_resp.answer,
        sources=[{k: v for k, v in s.items() if k != "chunks"} for s in sources],
        backend=llm_resp.backend,
        latency_ms=llm_resp.latency_ms,
    )
