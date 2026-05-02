"""Browser connector: receives tab/history events from the Chrome extension."""
import hashlib
from datetime import datetime, timezone
from urllib.parse import urlparse

import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from pce.db.models import Chunk, Item, Kind, Source
from pce.db.session import get_session_factory
from pce.ingestion.chunker import chunk_text
from pce.config import settings

log = structlog.get_logger()

# Domains that should never be ingested
DOMAIN_BLOCKLIST = {
    # Banking
    "chase.com", "bankofamerica.com", "wellsfargo.com", "citibank.com",
    "hsbc.com", "barclays.co.uk", "lloydsbank.com", "natwest.com",
    # Health
    "mychart.com", "patientgateway.org", "healthgrades.com",
    # Auth pages (usually have no useful content)
    "accounts.google.com", "login.microsoftonline.com", "auth0.com",
}

# Query string params to strip (sensitive or noisy)
STRIP_PARAMS = {"token", "password", "secret", "key", "auth", "session", "access_token"}


def _is_blocked(url: str) -> bool:
    try:
        host = urlparse(url).netloc.lower().lstrip("www.")
        return any(host == d or host.endswith("." + d) for d in DOMAIN_BLOCKLIST)
    except Exception:
        return True


def _canonical_url(url: str) -> str:
    """Strip sensitive query params and fragments."""
    try:
        p = urlparse(url)
        if p.query:
            from urllib.parse import parse_qs, urlencode
            params = {k: v for k, v in parse_qs(p.query).items()
                      if k.lower() not in STRIP_PARAMS}
            query = urlencode({k: v[0] for k, v in params.items()})
        else:
            query = ""
        return p._replace(query=query, fragment="").geturl()
    except Exception:
        return url


def _source_id(url: str) -> str:
    return hashlib.sha256(_canonical_url(url).encode()).hexdigest()[:32]


def _body_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


async def ingest_page(
    url: str,
    title: str,
    body: str,
    session: AsyncSession,
) -> bool:
    """
    Upsert a browser page into the context store.
    - If same URL + same content hash → update accessed_at only (cheap).
    - If same URL + different content → re-chunk and re-embed.
    - If new URL → insert.
    Returns True if the item was inserted or updated.
    """
    if _is_blocked(url):
        log.debug("browser_page_blocked", url=url)
        return False

    canonical = _canonical_url(url)
    sid = _source_id(canonical)
    bh = _body_hash(body)
    now = datetime.now(timezone.utc)

    result = await session.execute(
        select(Item).where(Item.source == Source.browser, Item.source_id == sid)
    )
    existing = result.scalar_one_or_none()

    if existing:
        if existing.body_hash == bh:
            # Content unchanged — just touch accessed_at
            existing.accessed_at = now
            await session.commit()
            return False

        # Content changed — update and re-chunk
        existing.title = title
        existing.body = body
        existing.body_hash = bh
        existing.url = canonical
        existing.accessed_at = now
        for chunk in list(existing.chunks):
            await session.delete(chunk)
        item = existing
    else:
        item = Item(
            source=Source.browser,
            source_id=sid,
            kind=Kind.page,
            title=title,
            body=body,
            body_hash=bh,
            url=canonical,
            accessed_at=now,
        )
        session.add(item)

    await session.flush()

    for tc in chunk_text(body, settings.chunk_size, settings.chunk_overlap):
        session.add(Chunk(
            item_id=item.id,
            ordinal=tc.ordinal,
            text=tc.text,
            token_count=tc.token_count,
            embedded=False,
        ))

    await session.commit()
    log.info("browser_page_ingested", url=canonical, title=title, new=existing is None)
    return True
