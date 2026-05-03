# Changelog

All notable changes to LogLens are documented here.

Format: [Semantic Versioning](https://semver.org/) — `MAJOR.MINOR.PATCH`

---

## [0.1.0] — 2026-05-03 · Initial Release

### Added
- **Vectorless RAG pipeline** — exact log analysis via LLM-generated `jq` programs, no vector DB or embeddings required
- **Two-pass retrieval** — Pass 1 explores structure, Pass 2 extracts precise data, with up to 3 auto-retries on `jq` failures
- **Intelligent briefing panel** — auto-scans logs at chat start and surfaces errors, failing endpoints, and latency issues before you ask a single question
- **Raw Evidence anchors** — every answer includes an "Evidence" panel with 2–5 verbatim log lines used to generate the response, eliminating hallucination doubts
- **Skills system** — pluggable `.toml` domain knowledge plugins with auto-detection and multi-skill blending
- **6 built-in skills**: `app_logs`, `nginx_access`, `nginx_error`, `systemd`, `python_app`, `generic`
- **BYOK multi-provider support**: OpenAI, Anthropic, Google Gemini, Groq
- **Interactive model/provider pickers** — `loglens config set-model` and `loglens config set-provider` open interactive menus
- **Persistent session caching** — schema and ID map computed once per log file, reused across all queries
- **Conversation memory** — multi-turn chat with rolling history window
- **One-line installer** (`install.sh`) — auto-detects OS (macOS, Ubuntu, Debian, Arch), installs `jq`, sets up PATH
- **Self-update command** — `loglens update` pulls latest from GitHub
- **Rich terminal UI** — progress bars, color-coded log levels, spinner animations, structured answer panels
- **Structured output format** — every LLM response is parsed into `ANSWER / DETAILS / EVIDENCE` sections and rendered separately
- **Full CLI**: `ingest`, `query`, `chat`, `sessions`, `refresh`, `clear-history`, `delete`, `update`, `config`, `skills`

### Skills
- `app_logs` — generic application logs (Python, Node, Java)
- `nginx_access` — HTTP access logs, latency, error rate analysis
- `nginx_error` — upstream timeouts, connection failures
- `systemd` — service crashes, restart loops, dependency chain analysis
- `python_app` — Python traceback parsing, exception type grouping
- `generic` — fallback for unknown formats

---

<!-- Add new versions above this line -->
