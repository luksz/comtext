# Comtext

A local-first personal context engine. Index your files, browser history, calendar, and email — then search and ask questions across all of it using hybrid retrieval and an LLM of your choice.

Everything runs on your machine. Your data stays yours.

---

## What it does

- **Indexes** your local files and browser activity into a searchable SQLite database
- **Embeds** content locally using `bge-small-en-v1.5` via `fastembed` — no external API calls for embeddings
- **Searches** with hybrid keyword + vector retrieval, fused with Reciprocal Rank Fusion (RRF)
- **Answers questions** via a RAG pipeline — retrieves relevant chunks, assembles context, queries a local (Ollama) or cloud (Anthropic) LLM with cited sources
- **Runs AI agent teams** — a Researcher → Planner → Coder → Reviewer pipeline grounded in your indexed context

---

## Prerequisites

- Python 3.12+
- [`uv`](https://docs.astral.sh/uv/) — fast Python package manager
- For local LLM: [Ollama](https://ollama.com) with a model pulled (e.g. `ollama pull llama3.2`)
- For cloud LLM / agent team: an Anthropic API key

---

## Setup

```bash
# 1. Clone
git clone https://github.com/luksz/Comtext.git
cd Comtext

# 2. Install dependencies
uv sync

# 3. Configure
cp .env.example .env
# Edit .env — at minimum set PCE_WATCH_DIRS and your LLM backend

# 4. Run database migrations
uv run alembic upgrade head

# 5. Start the server
uv run pce serve
```

The server starts on `http://127.0.0.1:8766`.

---

## Configuration

All settings use the `PCE_` prefix and can be set in `.env` or as environment variables.

| Variable | Default | Description |
|----------|---------|-------------|
| `PCE_DB_PATH` | `data/pce.db` | SQLite database path |
| `PCE_LLM_BACKEND` | `ollama` | `ollama` or `anthropic` |
| `PCE_OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server URL |
| `PCE_OLLAMA_MODEL` | `llama3.2` | Ollama model name |
| `PCE_ANTHROPIC_API_KEY` | — | Anthropic API key (required for cloud LLM + agent team) |
| `PCE_ANTHROPIC_MODEL` | `claude-sonnet-4-6` | Anthropic model for `/ask` |
| `PCE_AGENT_MODEL` | `claude-opus-4-7` | Anthropic model for the agent team |
| `PCE_EMBED_MODEL` | `BAAI/bge-small-en-v1.5` | Embedding model |
| `PCE_CHUNK_SIZE` | `400` | Chunk size in tokens |
| `PCE_CHUNK_OVERLAP` | `64` | Overlap between chunks in tokens |
| `PCE_RETRIEVAL_TOP_K` | `10` | Default number of results |
| `PCE_PORT` | `8766` | Server port |
| `PCE_LOG_LEVEL` | `INFO` | Log level |

---

## CLI

All commands are available as `uv run pce <command>` or `pce <command>` if the venv is activated.

### `pce serve`

Start the HTTP server.

```bash
uv run pce serve
uv run pce serve --port 9000 --reload   # custom port, hot reload
```

### `pce ingest <directory>`

Scan a directory and add all supported files to the context store. Supported extensions: `.py`, `.md`, `.txt`, `.ts`, `.js`, `.json`, `.yaml`, `.yml`, `.toml`, `.rst`.

```bash
uv run pce ingest ~/code/my-project
uv run pce ingest ~/Documents/notes
```

> Tip: For incremental updates, run the server and POST to `/ingest` — or set `PCE_WATCH_DIRS` to have the server watch directories automatically.

### `pce embed`

Embed all pending chunks that haven't been vectorised yet. The server also runs this automatically in the background every 60 seconds.

```bash
uv run pce embed
```

### `pce search <query>`

Hybrid keyword + vector search. Returns a ranked table of results.

```bash
uv run pce search "authentication middleware"
uv run pce search "meeting with design team" --top-k 5
```

### `pce ask <question>`

Full RAG pipeline: searches your context, assembles a prompt with cited sources, and queries the LLM.

```bash
uv run pce ask "where is the retry logic for the API client?"
uv run pce ask "what did I agree to in yesterday's standup?"
```

### `pce team <task>`

Run a 4-agent pipeline on a task. Agents search and write to your context store at each stage. Requires `PCE_ANTHROPIC_API_KEY`.

```bash
uv run pce team "write a design doc for adding a Slack connector"
uv run pce team "review the current search implementation and suggest improvements"
```

The pipeline:
1. **Researcher** — searches Comtext for relevant context
2. **Planner** — produces a detailed execution plan
3. **Coder** — implements the plan and saves output to Comtext
4. **Reviewer** — reviews the implementation and gives a verdict

The full team report is saved back to your context store and is searchable in future sessions.

---

## API

The server exposes a REST API on `http://127.0.0.1:8766`.

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/healthz` | Health check |
| `GET` | `/search?q=...&top_k=N` | Hybrid search |
| `POST` | `/ingest` | Trigger a directory scan |
| `POST` | `/embed` | Embed pending chunks |
| `POST` | `/ingest/browser` | Ingest a page from the browser extension |
| `POST` | `/ask` | RAG Q&A |
| `POST` | `/team/run` | Run the agent team |

**Example:**

```bash
curl -s "http://localhost:8766/search?q=authentication&top_k=5" | jq .
curl -s -X POST http://localhost:8766/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "where is the retry logic?"}' | jq .
```

---

## Browser extension

A Manifest V3 Chrome/Firefox extension is included in `browser-extension/`. It sends the active tab's content to `/ingest/browser` so visited pages are indexed automatically.

```bash
cd browser-extension
npm install
npm run build   # outputs to browser-extension/dist/
```

Load the `dist/` folder as an unpacked extension in your browser. The extension connects to `http://localhost:8766` by default.

---

## Architecture

```
Files / Browser / Calendar / Email
          │
          ▼
    Connectors (scan, watch, receive)
          │
          ▼
    Chunker (400 tok, 64 overlap)
          │
          ▼
    Embedder (bge-small-en-v1.5, local)
          │
          ▼
    SQLite  ◄────────────── Agent team writes notes back
    (Items + Chunks)
          │
          ▼
    Hybrid search
    Keyword (LIKE) + Vector (cosine) → RRF fusion
          │
          ▼
    LLM Router
    Ollama (local) │ Anthropic (cloud)
          │
          ▼
    Answer with [Source N] citations
```

---

## Roadmap

| Phase | Status |
|-------|--------|
| File indexing, hybrid search, RAG pipeline | Done |
| Browser extension + `/ingest/browser` | Done |
| Multi-agent team (`pce team`) | Done |
| Calendar connector (Google Calendar / MS Graph) | Planned |
| Email connector (Gmail / MS Graph) | Planned |
| Notes connector (Obsidian / Notion) | Planned |
| Dashboard frontend (Tauri + React) | Planned |
| OpenTelemetry traces, cost dashboard | Planned |

---

## Known limitations

- Vector embeddings are stored as JSON in SQLite. This works well at personal scale. If the index grows past ~100k chunks, swap for [`sqlite-vec`](https://github.com/asg017/sqlite-vec).
- Keyword search is LIKE-based, not BM25. Good enough for personal use; upgrade to FTS5 when retrieval quality plateaus.
- `pce ingest` from the CLI bypasses the server's session factory. For consistency, prefer using the running server's `/ingest` endpoint.
- The `Entity` table (people, projects, orgs) is modelled but not yet populated by any connector.

---

## License

MIT
