# LogLens Architecture

## Overview

LogLens is a developer-focused CLI tool that converts raw system logs into structured JSON, builds a queryable intelligence layer using `jq`, and uses an LLM to synthesize human-readable insights — all without a vector database, chunking pipeline, or embedding step.

**Core Philosophy:** Logs are structured data in disguise. LogLens just removes the disguise.

---

## System Architecture

LogLens follows a structured 5-stage pipeline for processing logs and answering queries:

```
Raw Log File
    ↓
[1. Ingestion]  → Parser streams logs to JSON
    ↓
[2. Discovery]  → Schema & ID Map discovery (cached)
    ↓
[3. Detection]  → Skills system detects log domain (cached)
    ↓
[4. Retrieval]  → Two-Pass Retrieval (Exploration → Extraction)
    ↓
[5. Synthesis]  → Narrative answer + Evidence block
```

### Module Structure

```
src/loglens/
├── cli.py                # Main CLI entry point (Typer)
├── agent.py              # Core Agent: Retrieval, Synthesis, Briefing
├── skills.py             # Domain Knowledge system (Nginx, Python, etc.)
├── parser.py             # Log parsing (JSON, logfmt, Nginx, Systemd)
├── schema.py             # Schema discovery (streaming ijson)
├── id_map.py             # Entity relationship mapping
├── memory.py             # Conversation history persistence
├── config.py             # API keys and provider/model management
└── __init__.py           # Package init
```

### Key Components

#### `agent.py` - The Brain
- **Briefing**: Runs fast JQ scans at startup to surface errors and latency before the user asks anything.
- **Two-Pass Retrieval**: 
    - *Pass 1 (Exploration)*: LLM writes a JQ query to sample raw records and confirm field values.
    - *Pass 2 (Extraction)*: LLM writes a precise JQ query to filter and group the exact data needed.
- **Synthesis**: Converts raw JQ output into a narrative answer, supporting details, and an **Evidence** block showing raw logs.

#### `skills.py` - Domain Knowledge
Pluggable system using `.toml` files to teach the agent:
- **Domain Context**: What thresholds matter (e.g., "500 errors are critical").
- **JQ Hints**: Mapping natural concepts to field names (e.g., "failure rate" → `response_status >= 400`).

#### `parser.py` - Log Streaming
- Handles streaming large files without loading them into memory.
- Supports structured JSON, Nginx (access/error), Systemd (journalctl), and Logfmt.

---

## Data Flow: Query Lifecycle

1. **User asks a question** in `cli.py`.
2. **Context Loading**: `agent.py` loads the cached `schema.json` and `id_map.json`.
3. **Skill Selection**: `skills.py` detects the log type based on field signals.
4. **Pass 1 (Exploration)**: LLM generates a JQ program to find "keyword matches" and sample data.
5. **Pass 2 (Extraction)**: LLM generates a JQ program to extract the final dataset.
6. **Synthesis**: LLM reads the raw data and the question to produce:
    - **ANSWER**: Direct 1-sentence response.
    - **DETAILS**: Bullet points with data-backed insights.
    - **EVIDENCE**: 2-5 exact log lines as "ground truth."
7. **Display**: `cli.py` renders the answer in a green panel and the evidence in a red-bordered "Evidence" panel.
8. **Persistence**: `memory.py` saves the turn to history for follow-up questions.

---

## Caching Strategy

### `.loglens/` Directory

```
.loglens/
├── schema.json          # Field types & structure (persistent)
├── id_map.json          # Entity relationships (persistent)
├── meta.json            # Log domain & context (persistent)
├── history.json         # Conversation history (persistent)
└── .gitignore           # Cache not tracked in git
```

**Why cache?**
- Schema building is I/O intensive (full log scan)
- ID map building scans all records
- Domain detection is one-time inference
- History enables follow-up questions with context

**Invalidation:**
- Automatic if log file mtime changes
- Manual: `loglens ingest --refresh logs/app.log`

---

## Log Format Support

### Structured JSON
```json
{
  "timestamp": "2024-01-15T10:32:00Z",
  "level": "ERROR",
  "logger": "app.services.auth",
  "message": "JWT validation failed",
  "trace_id": "abc123",
  "request_id": "req456",
  "error": "TokenExpired"
}
```

### Plaintext (Standard)
```
2024-01-15 10:32:00 ERROR [app.services.auth] JWT validation failed (trace_id=abc123)
2024-01-15 10:32:01 INFO [app.api] Request completed (request_id=req456)
```

### Nginx Access Logs
```
127.0.0.1 - - [15/Jan/2024:10:32:00 +0000] "GET /api/user HTTP/1.1" 500 1234
```

### Systemd / Journald
```
Jan 15 10:32:00 server auth[12345]: JWT validation failed
```

### Logfmt
```
timestamp=2024-01-15T10:32:00Z level=ERROR logger=app.services.auth message="JWT validation failed" trace_id=abc123
```

---

## Technology Stack

| Component | Technology | Rationale |
|-----------|------------|-----------|
| CLI Framework | **Typer** | Type-safe, async-friendly, great UX |
| JSON Processing | **ijson** | Memory-efficient streaming |
| Query Engine | **jq** | Battle-tested, portable, safe sandbox |
| Data Validation | **Pydantic** | Type safety, schema enforcement |
| LLM Integration | **OpenAI API** (configurable) | State-of-the-art reasoning |
| Testing | **pytest** | Standard Python testing |
| Code Quality | **ruff + black** | Fast linting & formatting |
| Package Manager | **uv** | Fast, reliable Python dependency management |

---

## Design Principles

1. **No Vector DB** — Logs are already structured; build queryable indices instead
2. **No Chunking** — Process entire logs; let LLM + jq handle filtering
3. **Local-First** — Cache schemas and history locally; no cloud dependency
4. **Composable** — jq is the universal query language; integrate with any tool
5. **Type-Safe** — Pydantic ensures schema consistency
6. **Stateless Queries** — Each query can run independently (but with shared cache)
7. **Memory as Context** — Keep conversation history for multi-turn Q&A

---

## Error Handling

- **Malformed Logs:** Graceful skipping with error reporting
- **Parse Failures:** Fallback to plaintext with type inference
- **jq Errors:** Retry with refined query via LLM
- **LLM Timeouts:** Return raw jq output without synthesis
- **Cache Issues:** Automatic refresh on validation failure

---

## Security Considerations

- **jq Sandbox:** All queries execute in jq's safe sandbox (no file system access)
- **LLM Prompts:** Never send raw log content to LLM; only schema + sample rows
- **Local Cache:** All sensitive data stays local (`.loglens/` not in git)
- **No Credentials in Logs:** User responsible for scrubbing (can pre-process)

---

## Future Extensions

- **Multi-file Queries:** Query across multiple log files
- **Streaming Mode:** Real-time log analysis
- **Custom Domains:** User-defined log type patterns
- **Plugin System:** Custom parsers and domain handlers
- **Web UI:** Dashboard for log querying and history
- **Export:** JSON, CSV, XLSX outputs
- **Cloud Backend:** Optional: sync cache across machines

---

## Development Workflow

```bash
# Install with uv
uv sync

# Run CLI
python -m loglens.cli query test.log -q "Find errors"

# Run tests
pytest tests/ -v

# Format & lint
black src/ tests/
ruff check src/ tests/
```

---

## References

- [Typer Documentation](https://typer.tiangolo.com/)
- [jq Manual](https://stedolan.github.io/jq/)
- [Pydantic Documentation](https://docs.pydantic.dev/)
- [OpenAI API](https://platform.openai.com/docs)
