<div align="center">
  <img src="https://raw.githubusercontent.com/ShivprasadRoul/LogLens/main/docs/loglens.png" width="100%" alt="LogLens — AI-Powered Log Analysis CLI" />

  <br/>

  [![PyPI version](https://img.shields.io/badge/version-0.1.0-blue?style=flat-square)](https://github.com/ShivprasadRoul/LogLens/releases)
  [![License: MIT](https://img.shields.io/badge/license-MIT-green?style=flat-square)](LICENSE)
  [![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue?style=flat-square)](https://python.org)
  [![Requires jq](https://img.shields.io/badge/requires-jq-orange?style=flat-square)](https://stedolan.github.io/jq/)

  <br/>

  <strong>Ask plain-English questions about any log file. Get precise, evidence-backed answers.</strong><br/>
  <sub>No vector DB · No embeddings · No chunking · Runs entirely on your machine</sub>

</div>

---

**LogLens** is a local-first CLI tool that turns gigabytes of messy, semi-structured logs into a conversational interface. Unlike traditional RAG systems that rely on hallucination-prone vector embeddings, LogLens uses **Vectorless RAG** — it streams your logs to discover their exact schema, then uses an LLM to write precise `jq` queries that extract only the data needed to answer your question. Every answer comes with raw evidence so you can verify it yourself.

---

## ✨ Key Features

- **Vectorless Architecture** — No embeddings, no vector DB, no chunking. Exact data extraction via LLM-generated `jq` programs.
- **Intelligent Briefing** — On `chat` start, LogLens auto-scans your logs and surfaces errors, failing endpoints, and latency outliers before you ask a single question.
- **Evidence Anchors** — Every answer includes a raw Evidence panel showing the exact log lines used to generate the response. No hallucinations, no guessing.
- **Skills System** — Pluggable `.toml` files that teach LogLens how to interpret specific log formats (Nginx, Python, systemd, and more). Community-extensible.
- **BYOK — Multi-Provider** — Bring your own API key for OpenAI, Anthropic, Gemini, or Groq. Switch providers and models anytime.
- **Persistent Sessions** — Schema and ID map are computed once per file and cached. Follow-up queries are instant.
- **Conversation Memory** — Full chat history is stored per session, enabling natural follow-up questions without re-stating context.

---


## 💬 Feedback & Feature Requests

Found a bug? Have an idea for a new skill or feature?

👉 **[Share feedback on Featurebase](https://loglens.featurebase.app)**
📋 **[View the Changelog](https://loglens.featurebase.app/changelog)**
#### Or raise an issue and tag it as a feature request or bug report.

---

## 🚀 Quick Start

### 1. Install

```bash
curl -fsSL https://raw.githubusercontent.com/ShivprasadRoul/LogLens/main/install.sh | bash
```

The installer auto-detects your OS and installs `jq`, Python dependencies, and the `loglens` CLI entry point.

> **Requires**: Python 3.9+, macOS or Linux (Ubuntu/Debian/Arch)

### 2. Configure

```bash
# Add your API key (supports openai, anthropic, groq, gemini)
loglens config set-key anthropic sk-ant-...

# Set your active provider
loglens config set-provider anthropic

# Pick a model interactively
loglens config set-model
```

### 3. Ingest Your Logs

```bash
loglens ingest /var/log/nginx/access.log --name my-app
```

This runs once per file — parses logs, discovers schema, builds ID map, and caches everything to `.loglens/sessions/my-app/`.

### 4. Start Analyzing

```bash
# Interactive multi-turn chat
loglens chat my-app

# Or a single one-shot query
loglens query my-app -q "which endpoints had the most errors?"
```

---

## 🏗 Why Vectorless RAG?

Traditional RAG chunks logs and retrieves "similar" text. This fundamentally fails for log analysis because:

| Problem | Traditional RAG | LogLens |
|---|---|---|
| **Precision** | "404" might be semantically similar to "500" | Exact field matching via `jq` |
| **Aggregation** | Can't find "the user with the most failures" across all records | Full-file computation via `jq` |
| **Logic** | Can't calculate P99 latency or failure rates | Arithmetic and grouping in `jq` |
| **Hallucination** | LLM fills gaps with plausible-sounding fiction | Evidence panel shows exact source records |

LogLens uses the LLM as a **programmer**, not just a searcher. It writes a `jq` program that executes deterministically on your logs and returns exact data — which the LLM then synthesizes into a human-readable answer.

---

## 🛠 Command Reference

### Core Analysis

| Command | Usage | Description |
|---|---|---|
| `ingest` | `loglens ingest <file> [--name <n>]` | Parse logs into a session (run once per file) |
| `query` | `loglens query <session> -q "..."` | Single one-shot question |
| `chat` | `loglens chat <session>` | Interactive multi-turn conversation |
| `sessions` | `loglens sessions` | List all cached log sessions |
| `refresh` | `loglens refresh <session>` | Re-parse logs (keeps history by default) |
| `delete` | `loglens delete <session>` | Remove a session and all its cached data |
| `update` | `loglens update` | Self-update LogLens to the latest version |

### Configuration

| Command | Usage | Description |
|---|---|---|
| `config show` | `loglens config show` | View active settings (keys masked) |
| `config set-key` | `loglens config set-key <provider> <key>` | Store an API key |
| `config set-provider` | `loglens config set-provider [provider]` | Switch active LLM provider |
| `config set-model` | `loglens config set-model [model]` | Switch model (interactive picker if no arg) |

### Skills

| Command | Usage | Description |
|---|---|---|
| `skills list` | `loglens skills list` | List all available skills (built-in + user) |
| `skills show` | `loglens skills show <name>` | View a skill's prompts and detection signals |
| `skills add` | `loglens skills add <file.toml>` | Install a custom skill |
| `skills remove` | `loglens skills remove <name>` | Remove a user-installed skill |

Pass `--skill <name>` to `ingest` or `chat` to force a specific skill instead of auto-detecting.

---

## 🧩 Skills System

Skills are pluggable `.toml` files that teach LogLens how to interpret a specific log format. Each skill contributes:

- **`[detection]`** — keywords that trigger auto-detection
- **`[prompts.domain_context]`** — injected into the synthesis prompt (what metrics mean, what to flag)
- **`[prompts.jq_hints]`** — injected into the `jq` generation prompt (field paths, gotchas)

### Built-in Skills

| Skill | Best For |
|---|---|
| `app_logs` | Generic Python / Node / Java application logs |
| `nginx_access` | Nginx access logs — 5xx rates, latency, top endpoints |
| `nginx_error` | Nginx error logs — upstream timeouts, connection failures |
| `systemd` | systemd / journald — service crashes, restart loops |
| `python_app` | Python apps with tracebacks — exception types, source tracing |
| `generic` | Fallback for any unknown log format |

### Writing a Custom Skill

```bash
# Copy the template
cp skills/_template.toml skills/my-format.toml

# Edit it
nano skills/my-format.toml

# Install it
loglens skills add skills/my-format.toml

# Test it
loglens ingest app.log --skill my-format
```

A minimal skill looks like this:

```toml
[meta]
name        = "kubernetes"
description = "Kubernetes pod and control-plane logs"
version     = "1.0.0"
author      = "your-name"

[detection]
signals = ["pod", "namespace", "container", "kubelet"]

[prompts]
domain_context = """
DOMAIN: Kubernetes Logs
- Flag CrashLoopBackOff, OOMKilled, ImagePullBackOff
- Always include namespace and pod name in findings
- Give kubectl commands as remediation steps
"""

jq_hints = """
- Pod name: .pod or .kubernetes.pod_name
- Namespace: .namespace or .kubernetes.namespace_name
- Filter by namespace: select(.namespace == "production")
"""
```

See [docs/skills.md](docs/skills.md) for the full guide and [SKILLS.md](SKILLS.md) for contributing community skills.

---

## 📁 Session Cache

Everything LogLens computes is cached under `.loglens/sessions/<name>/`:

```
.loglens/
  config.json          ← global config (API keys, provider, model)
  sessions/
    <session-name>/
      schema.json      ← discovered field structure
      id_map.json      ← entity ID → name lookup
      meta.json        ← domain, record count, last updated
      history.json     ← full conversation memory
      log_data.json    ← parsed structured JSON
```

Schema and ID map are computed **once** on `ingest` and reused for every query. Run `loglens refresh <session>` if your log file changes.

---

## 🔑 Supported LLM Providers

LogLens is **BYOK** (Bring Your Own Key) — you supply the API key, LogLens never proxies or manages keys on your behalf. Keys are stored in `~/.loglens/config.json` with `600` permissions.

| Provider | Models | Environment fallback |
|---|---|---|
| Anthropic | claude-opus-4-5, claude-sonnet-4-5, claude-haiku-4-5 | `ANTHROPIC_API_KEY` |
| OpenAI | gpt-4o, gpt-4o-mini, gpt-4-turbo | `OPENAI_API_KEY` |
| Groq | llama-3.3-70b, mixtral-8x7b | `GROQ_API_KEY` |
| Gemini | gemini-1.5-pro, gemini-1.5-flash | `GEMINI_API_KEY` |

If a key isn't in config, LogLens falls back to the corresponding environment variable automatically.

---

## 📚 Documentation

| Doc | Description |
|---|---|
| [Getting Started](docs/getting-started.md) | Installation, first ingest, first query |
| [CLI Reference](docs/cli-reference.md) | Every command, flag, and option |
| [Skills System](docs/skills.md) | Writing and contributing custom skills |
| [Architecture](architecture.md) | Deep dive into Vectorless RAG and `jq` generation |


## 🤝 Contributing

Contributions are welcome — especially new skills! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

```bash
git clone https://github.com/ShivprasadRoul/LogLens.git
cd LogLens
pip install -e ".[dev]"
```

---

## License

MIT — see [LICENSE](LICENSE) for details.