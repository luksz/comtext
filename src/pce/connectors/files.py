"""Local filesystem connector: initial scan + watchdog-based live updates."""
import hashlib
from pathlib import Path

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from pce.config import settings
from pce.db.models import Chunk, Item, Kind, Source
from pce.db.session import get_session_factory
from pce.ingestion.chunker import chunk_text

log = structlog.get_logger()

_observer: Observer | None = None


def _source_id(path: Path) -> str:
    return hashlib.sha256(str(path.resolve()).encode()).hexdigest()[:32]


def _body_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _is_watched(path: Path) -> bool:
    return path.suffix.lower() in settings.watch_extensions


async def ingest_file(path: Path, session: AsyncSession) -> bool:
    """Ingest a single file. Returns True if it was new or updated."""
    if not path.is_file() or not _is_watched(path):
        return False

    try:
        body = path.read_text(errors="replace")
    except Exception as exc:
        log.warning("file_read_error", path=str(path), error=str(exc))
        return False

    sid = _source_id(path)
    bh = _body_hash(body)

    result = await session.execute(
        select(Item).where(Item.source == Source.file, Item.source_id == sid)
    )
    existing = result.scalar_one_or_none()

    if existing and existing.body_hash == bh:
        return False  # unchanged

    if existing:
        existing.title = path.name
        existing.body = body
        existing.body_hash = bh
        existing.path = str(path.resolve())
        # delete old chunks so they get re-embedded
        for chunk in list(existing.chunks):
            await session.delete(chunk)
        item = existing
    else:
        item = Item(
            source=Source.file,
            source_id=sid,
            kind=Kind.code_file if path.suffix in {".py", ".ts", ".js"} else Kind.document,
            title=path.name,
            body=body,
            body_hash=bh,
            path=str(path.resolve()),
        )
        session.add(item)

    await session.flush()  # get item.id

    for tc in chunk_text(body, settings.chunk_size, settings.chunk_overlap):
        session.add(Chunk(
            item_id=item.id,
            ordinal=tc.ordinal,
            text=tc.text,
            token_count=tc.token_count,
            embedded=False,
        ))

    await session.commit()
    log.info("file_ingested", path=str(path), new=existing is None)
    return True


async def scan_directory(directory: str | Path) -> int:
    """Walk a directory and ingest all matching files. Returns count ingested."""
    directory = Path(directory)
    factory = get_session_factory()
    count = 0

    async with factory() as session:
        for path in directory.rglob("*"):
            # Respect common ignore patterns
            if any(part.startswith(".") or part in {"__pycache__", "node_modules", ".venv"}
                   for part in path.parts):
                continue
            if await ingest_file(path, session):
                count += 1

    log.info("scan_complete", directory=str(directory), ingested=count)
    return count


class _FileHandler(FileSystemEventHandler):
    def __init__(self, loop):
        self._loop = loop

    def _schedule(self, path: str):
        import asyncio
        factory = get_session_factory()

        async def _run():
            async with factory() as session:
                await ingest_file(Path(path), session)

        asyncio.run_coroutine_threadsafe(_run(), self._loop)

    def on_modified(self, event):
        if not event.is_directory:
            self._schedule(event.src_path)

    def on_created(self, event):
        if not event.is_directory:
            self._schedule(event.src_path)


def start_watcher(loop) -> None:
    global _observer
    if _observer or not settings.watch_dirs:
        return

    _observer = Observer()
    handler = _FileHandler(loop)
    for d in settings.watch_dirs:
        _observer.schedule(handler, d, recursive=True)
    _observer.start()
    log.info("file_watcher_started", dirs=settings.watch_dirs)


def stop_watcher() -> None:
    global _observer
    if _observer:
        _observer.stop()
        _observer.join()
        _observer = None
