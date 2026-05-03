# LogLens Architecture

## Overview

LogLens is a developer-focused CLI tool that converts raw system logs into structured JSON, builds a queryable intelligence layer using `jq`, and uses an LLM to synthesize human-readable insights — all without a vector database, chunking pipeline, or embedding step.

**Core Philosophy:** Logs are structured data in disguise. LogLens just removes the disguise.

---

## System Architecture

### 8-Step Pipeline

LogLens follows a structured 8-step pipeline for processing logs and answering queries:

```
Raw Log File
    ↓
[1. Log Parser] → Structured JSON
    ↓
[2. Schema Discovery] → Schema + ID Map (cached)
    ↓
[3. ID Map Builder] → Entity relationship map (cached)
    ↓
[4. Domain Detection] → Log domain context (cached)
    ↓
[5. jq Code Generation] → Query programs via CoT
    ↓
[6. Two-Pass Retrieval] → Explore → Retry Loop
    ↓
[7. Insight Synthesis] → Actionable answers
    ↓
[8. Memory & History] → Conversation history (cached)
```

### Pipeline Stages

| # | Stage | Component | Role | Cached |
|---|-------|-----------|------|--------|
| 1 | Input | Log Parser | Converts `.log` to structured JSON with typed fields | No |
| 2 | Analysis | Schema Discovery | Builds structural map via streaming `ijson` | Yes |
| 3 | Analysis | ID Map Builder | Detects entity relationships and builds lookup | Yes |
| 4 | Context | Domain Detection | Identifies log domain and injects context | Yes |
| 5 | Query Gen | jq Code Gen (CoT) | LLM generates `jq` step-by-step programs | No |
| 6 | Retrieval | Two-Pass Query | Pass 1 explores, Pass 2 extracts with retry | No |
| 7 | Output | Insight Synthesis | Synthesizes raw data into insights | No |
| 8 | State | Memory & History | Maintains conversation state | Yes |

---

## Module Structure

```
src/loglens/
├── __init__.py           # Package initialization
├── cli.py                # Main CLI interface (Typer)
├── parser.py             # Log parsing module
├── schema.py             # Schema discovery
├── id_map.py             # Entity relationship mapping
├── llm.py                # LLM integration (CoT, synthesis)
├── jq_engine.py          # jq query execution
├── domain.py             # Log domain detection
└── cache.py              # Schema/history caching
```

### Key Modules

#### `cli.py` - Main CLI (Typer)
- `query`: Natural language query on logs
- `ingest`: Parse and cache log structure
- `chat`: Interactive session mode

#### `parser.py` - Log Parsing
Supports:
- Structured JSON logs (structlog, Winston, Bunyan)
- Plaintext logs (INFO/ERROR/WARNING/DEBUG)
- Nginx access/error logs
- Systemd/journald logs
- Python tracebacks
- Logfmt key=value format

#### `schema.py` - Schema Discovery
- Scans JSON structure via `ijson`
- Infers field types
- Builds reusable schema
- Cached at `.loglens/schema.json`

#### `id_map.py` - Entity Relationship Mapping
- Scans for common ID patterns (request_id, trace_id, user_id)
- Builds entity-to-records index
- Caches relationships
- Cached at `.loglens/id_map.json`

#### `domain.py` - Domain Detection
- Detects log type (app, nginx, system, etc.)
- Injects domain-specific prompt context
- Cached at `.loglens/meta.json`

#### `llm.py` - LLM Integration
- CoT (Chain of Thought) for jq generation
- Two-pass retrieval with retry
- Insight synthesis from raw data

#### `jq_engine.py` - jq Query Execution
- Wrapper around `jq` binary
- Executes generated queries
- Error handling and retry logic

---

## Data Flow: Query Lifecycle

### 1. User asks a question
```
loglens query logs/app.log --query "Why did the deployment fail?"
```

### 2. Load cached schema & ID map
```
.loglens/
├── schema.json      # Field types, structure
├── id_map.json      # Entity relationships
└── meta.json        # Log domain, context
```

### 3. LLM generates jq program (CoT)
```
"Given schema {fields...} and domain 'app_log', 
 convert question to jq steps:
 1. Filter ERROR level
 2. Group by deployment_id
 3. Extract messages"
```

### 4. Execute jq query (Pass 1: Explore)
```bash
jq '.[] | select(.level == "ERROR") | {deployment_id, message}'
```

### 5. Analyze results
- If sufficient, proceed to synthesis
- If incomplete, retry with refined query (Pass 2)

### 6. Synthesize insights
```
LLM reads raw jq output + logs + question:
"Deployment failed because [reason] at [time].
 Impact: [services affected].
 Next steps: [recommendations]"
```

### 7. Return answer
```
Deployment X failed at 10:32 UTC due to JWT validation errors.
Affected services: auth-service, api-gateway.
Recommendation: Check token expiration config.
```

### 8. Save to history
```
.loglens/history.json
- conversation_id
- query
- answer
- jq_program_used
- timestamp
```

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
