# Future Work

This document tracks what has been built and what comes next. Pick it up from any phase.

## What's been built (Weeks 1–2)

### Infrastructure
- `uv` project with Python 3.12, FastAPI, SQLite, Alembic migrations
- Async SQLAlchemy with `aiosqlite`
- Structured logging via `structlog`
- Config via `.env` / environment variables (prefix `PCE_`)
- Background scheduler (APScheduler 3.x) for periodic embedding

### Data model
- `Item` — canonical record for any content source (file, browser page, email, etc.)
- `Chunk` — text pieces cut from items, with stored vector embeddings
- `Entity` — people, projects, orgs (ready but not yet populated)
- `SyncState` — tracks incremental sync cursors per source

### Connectors
- **Local files** — recursive directory scan + watchdog live watcher
- Extensions watched: `.py`, `.md`, `.txt`, `.ts`, `.js`, `.json`, `.yaml`, `.toml`, `.rst`
- Content-hash dedup (re-embeds only when file actually changes)

### Retrieval
- Keyword search (LIKE-based, multi-term scoring)
- Vector search (cosine similarity over `fastembed` `bge-small-en-v1.5` embeddings stored as JSON)
- RRF fusion (Reciprocal Rank Fusion combining both)

### LLM router
- Ollama backend (local, default) — calls `/api/chat`
- Anthropic backend (cloud) — uses `anthropic` SDK
- Latency + token logging on every call
- Prompt assembly with `[Source N]` citations

### API endpoints
- `GET /healthz`
- `GET /search?q=...&top_k=N`
- `POST /ingest` — trigger directory scan
- `POST /embed` — run embedding worker once
- `POST /ask` — full RAG pipeline (search → assemble → LLM → answer)

### CLI (`pce` command)
- `pce serve` — start the server (port 8766)
- `pce ingest <dir>` — ingest a directory
- `pce search <query>` — keyword + vector search, pretty table output
- `pce embed` — embed pending chunks
- `pce ask <question>` — full question-answering with citations

---

## What's next

### Immediate (finish Week 2)
- [ ] Test the full pipeline end-to-end with a real directory
- [ ] Run `pce embed` after ingesting and verify vectors are stored
- [ ] Ask at least 3 real questions with `pce ask` and record the answers
- [ ] Populate `evals/cases.yaml` with 10 real (query, expected file) pairs
- [ ] Run `pytest evals/` and record the baseline recall@5, recall@10, MRR scores

### Week 3–4 — Browser extension
- Build a Chrome/Firefox Manifest V3 extension (TypeScript + Vite)
- Native messaging host: small Python bridge connecting the extension to the FastAPI backend
- Capture: open tabs on focus change, history additions, page metadata
- Privacy filter: domain blocklist for sensitive sites, regex denylist for query strings
- Page content extraction on dwell > 15s (Mozilla Readability or trafilatura)
- Dedup by canonical URL — update `accessed_at`, re-embed only on content change
- Add `source=browser` items to the retrieval pipeline

### Week 5–7 — Calendar & email
- OAuth2 flow with token persistence (OS keychain via `keyring`)
- **Calendar**: Google Calendar API or MS Graph, incremental sync via `syncToken` / `deltaLink`
- Map calendar event → `Item(kind=event)`, participants → `Entity(kind=person)`
- **Email**: Gmail API or MS Graph (not raw IMAP)
- Strip quoted replies and signatures before chunking (`talon` library)
- Per-label allow/denylist; never ingest spam or trash
- **Entity resolution**: merge same person across email + calendar + browser by email address

### Week 8 — Notes connector
- Obsidian (recommended — filesystem-based, no auth) or Notion (API)
- Parse markdown, extract frontmatter, resolve `[[wikilinks]]` to `Item` relationships
- Link notes to entities via name matching

### Week 9–10 — Dashboard frontend
- Tauri shell with React/TS (or Next.js on localhost if Tauri feels heavy)
- Home view: today's calendar, recent items, LLM-generated daily brief
- Search bar with filter chips: source, time range, entity
- Chat UI talking to `/ask` with conversation history
- Citations panel — every answer expandable to source items

### Week 11–12 — Hardening
- OpenTelemetry traces + structured log export
- Nightly SQLite backup (`VACUUM INTO` + encrypted rclone)
- Token cost dashboard: tokens in/out per backend, $/day cap with hard stop
- Connector retry/backoff, dead-letter queue for bad items
- Alerts if a connector hasn't synced in N hours

---

## Known issues / tech debt

- Vector embeddings stored as JSON in SQLite — fine at personal scale, but swap for `sqlite-vec` when the index grows large (>100k chunks)
- Keyword search is LIKE-based, not true BM25 — good enough for now, upgrade to FTS5 when retrieval quality plateaus
- `pce ingest` from the CLI bypasses the server's DB session factory — run `pce serve` and use the `/ingest` endpoint instead for consistency
- The `Entity` table is defined but not yet populated by any connector

## Running the project

```bash
# Install deps (only needed once)
pip install uv
uv sync

# Activate venv
source .venv/bin/activate

# Copy and edit config
cp .env.example .env

# Start the server
pce serve

# In another terminal — ingest a folder
pce ingest ~/path/to/your/code

# Embed chunks (or wait ~1 min for scheduler)
pce embed

# Search
pce search "retry logic"

# Ask a question (requires Ollama running locally, or set PCE_LLM_BACKEND=anthropic)
pce ask "where is the authentication middleware defined"
```
