# Comtext — Claude Code Context

## Project overview

Comtext is a local-first personal context engine. It indexes files, browser history, calendar, and email into a SQLite database with vector embeddings, then answers questions using hybrid search + RAG over a local or cloud LLM.

## Tech stack

- **Python 3.12**, `uv` for package management
- **FastAPI** + **uvicorn** for the HTTP server
- **SQLite** + **SQLAlchemy 2 (async)** + **aiosqlite** for persistence
- **Alembic** for DB migrations
- **fastembed** (`bge-small-en-v1.5`) for local vector embeddings
- **APScheduler** for background embedding worker
- **Typer** + **Rich** for the CLI
- **anthropic SDK** for cloud LLM and multi-agent pipeline
- **watchdog** for live file watching

## Repository layout

```
src/pce/
├── main.py              # FastAPI app, startup/shutdown, background scheduler
├── cli.py               # Typer CLI: serve, ingest, search, embed, ask, team
├── config.py            # Pydantic settings (PCE_* env vars)
├── api/routes.py        # REST endpoints
├── db/
│   ├── models.py        # SQLAlchemy ORM: Item, Chunk, Entity, SyncState
│   └── session.py       # Async session factory
├── ingestion/
│   ├── chunker.py       # Token-bounded text chunking (400 tok, 64 overlap)
│   └── embedder.py      # Embeds pending Chunks with fastembed
├── retrieval/search.py  # Hybrid keyword + vector search with RRF fusion
├── llm/router.py        # Routes to Ollama (local) or Anthropic (cloud)
├── connectors/
│   ├── files.py         # Recursive dir scan + watchdog live watcher
│   └── browser.py       # Receives browser page data via /ingest/browser
└── agents/              # Multi-agent pipeline (Week 4, not yet committed)
    ├── orchestrator.py  # Researcher → Planner → Coder → Reviewer loop
    ├── roles.py         # System prompts per agent role
    └── tools.py         # search_comtext + write_note tool definitions
browser-extension/       # Manifest V3 Chrome/Firefox extension (TypeScript + Vite)
alembic/                 # DB migration scripts
evals/                   # Evaluation cases (query → expected source)
data/                    # SQLite DB and indexed content (gitignored)
```

## Key commands

```bash
uv sync                        # install / sync dependencies
uv run pce serve               # start server on port 8766
uv run pce ingest <dir>        # ingest a directory
uv run pce embed               # embed pending chunks
uv run pce search "<query>"    # hybrid search
uv run pce ask "<question>"    # RAG Q&A
uv run pce team "<task>"       # multi-agent pipeline (requires ANTHROPIC_API_KEY)
uv run pytest                  # run tests
```

## API endpoints

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/healthz` | Health check |
| GET | `/search?q=...&top_k=N` | Hybrid search |
| POST | `/ingest` | Trigger directory scan |
| POST | `/embed` | Embed pending chunks |
| POST | `/ingest/browser` | Ingest browser page (from extension) |
| POST | `/ask` | RAG Q&A |
| POST | `/team/run` | Run multi-agent pipeline |

## Environment variables (prefix `PCE_`)

```
PCE_DB_PATH=data/pce.db
PCE_LLM_BACKEND=ollama          # "ollama" or "anthropic"
PCE_OLLAMA_MODEL=llama3.2
PCE_ANTHROPIC_API_KEY=sk-ant-...
PCE_ANTHROPIC_MODEL=claude-sonnet-4-6
PCE_AGENT_MODEL=claude-opus-4-7  # backbone for multi-agent team
PCE_PORT=8766
```

## Architecture decisions

- **Embeddings stored as JSON in SQLite** — fine at personal scale (<100k chunks). Swap for `sqlite-vec` if it grows large.
- **Keyword search is LIKE-based**, not FTS5/BM25 — acceptable for personal use, upgrade when retrieval plateaus.
- **RRF fusion** (Reciprocal Rank Fusion) merges keyword + vector rankings without needing score normalization.
- **`pce ingest` from CLI bypasses the server session factory** — prefer `POST /ingest` via the running server for consistency.
- **Agents use `thinking: {"type": "adaptive"}`** — lets Claude use extended thinking on hard reasoning steps.

## Current git state (as of Week 4)

- `src/pce/agents/` — new untracked directory (multi-agent feature, not yet committed)
- Modified: `api/routes.py`, `cli.py`, `config.py`, `db/models.py`, `uv.lock` — all part of the agent feature
- Everything else is clean on `main`
