"""Comtext tools available to all agents: search and write."""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

log = structlog.get_logger()

COMTEXT_TOOLS = [
    {
        "name": "search_comtext",
        "description": (
            "Search your personal context store (Comtext) for relevant information. "
            "Returns titles, sources, and content snippets ranked by relevance. "
            "Use this to find existing notes, code, browser history, or files related to the task. "
            "Run multiple searches with different queries to build a thorough picture."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query",
                },
                "top_k": {
                    "type": "integer",
                    "description": "Number of results to return (default: 5, max: 20)",
                    "default": 5,
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "write_note",
        "description": (
            "Save a note or artifact to Comtext so it persists and can be searched later. "
            "Use this to store research findings, plans, code, decisions, or any output "
            "worth keeping for future tasks."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Short descriptive title for the note",
                },
                "content": {
                    "type": "string",
                    "description": "Full content of the note (markdown supported)",
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional tags to categorise the note",
                    "default": [],
                },
            },
            "required": ["title", "content"],
        },
    },
]


async def _tool_search_comtext(query: str, top_k: int, session: AsyncSession) -> str:
    from pce.retrieval.search import hybrid_search

    results = await hybrid_search(query, session, top_k=min(top_k, 20))
    if not results:
        return f"No results found for query: {query!r}"

    lines: list[str] = []
    for i, r in enumerate(results, 1):
        label = r.title or r.path or r.url or r.item_id
        lines.append(f"[{i}] {label}  (source: {r.source}, score: {r.score:.3f})")
        lines.append(f"    {r.snippet[:250]}")
        if r.chunks:
            lines.append(f"    --- excerpt ---")
            lines.append(f"    {r.chunks[0][:400]}")
        lines.append("")

    return "\n".join(lines)


async def _tool_write_note(title: str, content: str, tags: list[str], session: AsyncSession) -> str:
    from sqlalchemy import select

    from pce.config import settings
    from pce.db.models import Chunk, Item, Kind, Source
    from pce.ingestion.chunker import chunk_text

    sid = hashlib.sha256(f"agent:{title}".encode()).hexdigest()[:32]
    bh = hashlib.sha256(content.encode()).hexdigest()
    now = datetime.now(timezone.utc)

    result = await session.execute(
        select(Item).where(Item.source == Source.agent, Item.source_id == sid)
    )
    existing = result.scalar_one_or_none()

    if existing:
        existing.title = title
        existing.body = content
        existing.body_hash = bh
        existing.accessed_at = now
        existing.meta = {"tags": tags}
        for chunk in list(existing.chunks):
            await session.delete(chunk)
        item = existing
    else:
        item = Item(
            source=Source.agent,
            source_id=sid,
            kind=Kind.note,
            title=title,
            body=content,
            body_hash=bh,
            accessed_at=now,
            meta={"tags": tags},
        )
        session.add(item)

    await session.flush()

    for tc in chunk_text(content, settings.chunk_size, settings.chunk_overlap):
        session.add(Chunk(
            item_id=item.id,
            ordinal=tc.ordinal,
            text=tc.text,
            token_count=tc.token_count,
            embedded=False,
        ))

    await session.commit()
    log.info("agent_note_written", title=title, item_id=item.id)
    return f"Note saved to Comtext (id: {item.id}, title: {title!r})"


async def execute_tool(name: str, tool_input: dict, session: AsyncSession) -> str:
    """Dispatch a tool call from an agent."""
    if name == "search_comtext":
        return await _tool_search_comtext(
            query=tool_input["query"],
            top_k=tool_input.get("top_k", 5),
            session=session,
        )
    if name == "write_note":
        return await _tool_write_note(
            title=tool_input["title"],
            content=tool_input["content"],
            tags=tool_input.get("tags", []),
            session=session,
        )
    return f"Unknown tool: {name}"
