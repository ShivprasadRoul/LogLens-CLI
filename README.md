<div align="center">
  <img src="https://raw.githubusercontent.com/ShivprasadRoul/LogLens/main/docs/loglens.png" width="100%" alt="LogLens — AI-Powered Log Analysis CLI" />
</div>

---

**LogLens** is a local CLI tool that turns gigabytes of messy, semi-structured logs into a conversational interface. Unlike traditional RAG systems that use hallucination-prone vector embeddings, LogLens uses **Vectorless RAG**: it streams your logs to discover their exact schema, and then uses an LLM to write precise `jq` queries to extract the data needed for 100% accurate answers.

## 🌟 Key Features

- **Vectorless Architecture**: No embeddings, no vector DB. Exact data extraction via LLM-generated `jq`.
- **Intelligent Briefing**: Instantly scans logs upon chat start to surface errors, failing endpoints, and latency issues.
- **Raw Evidence Anchors**: Every answer includes an "Evidence" panel showing the exact log lines used to generate the response.
- **Skills System**: Pluggable domain knowledge for Nginx, Python, Systemd, and more.
- **Multi-Provider Support**: BYOK (Bring Your Own Key) for OpenAI, Anthropic, Gemini, and Groq.
- **Interactive Configuration**: Easy-to-use pickers for switching models and providers.

---

## 🚀 Quick Start

### 1. Install
```bash
curl -fsSL https://raw.githubusercontent.com/ShivprasadRoul/LogLens/main/install.sh | bash
```

### 2. Configure
```bash
loglens config set-key openai sk-...
loglens config set-provider openai
loglens config set-model          # Opens interactive picker
```

### 3. Ingest & Analyze
```bash
loglens ingest /var/log/nginx/access.log --name my-app
loglens chat my-app
```

---

## 🛠 Command Summary

### Core Analysis
| Command | Usage |
|---|---|
| `ingest` | `loglens ingest <file> [--name <name>]` - Parse logs into a session |
| `query` | `loglens query <session> -q "..."` - Single question analysis |
| `chat` | `loglens chat <session>` - Interactive multi-turn chat |
| `sessions` | `loglens sessions` - List all ingested log sessions |
| `refresh` | `loglens refresh <session>` - Re-parse logs (keeps history by default) |
| `delete` | `loglens delete <session>` - Remove a session and all cached data |
| `update` | `loglens update` - Self-update LogLens to latest version |

### Configuration (`loglens config ...`)
| Command | Usage |
|---|---|
| `show` | `loglens config show` - View active settings |
| `set-key` | `loglens config set-key <provider> <key>` - Save an API key |
| `set-provider`| `loglens config set-provider [provider]` - Switch active LLM |
| `set-model` | `loglens config set-model [model]` - Switch active model |

### Skills Management (`loglens skills ...`)
| Command | Usage |
|---|---|
| `list` | `loglens skills list` - List all available log formats |
| `show` | `loglens skills show <name>` - View skill details and hints |
| `add` | `loglens skills add <file>` - Install a custom log format |
| `remove` | `loglens skills remove <name>` - Delete a user-installed skill |

---

## 📚 Documentation

For detailed guides, check out the `docs/` folder:

- [**Getting Started**](docs/getting-started.md): Installation and first steps.
- [**CLI Reference**](docs/cli-reference.md): Full breakdown of every command and flag.
- [**Skills System**](docs/skills.md): How to write custom log formats for your domain.
- [**Architecture**](architecture.md): Deep dive into Vectorless RAG and `jq` generation.

---

## 🏗 Why Vectorless RAG?

Traditional RAG chunks logs and searches for "similar" text. This fails for logs because:
1. **Precision matters**: "404" is not "similar" to "500", but a vector search might treat them as such.
2. **Cardinality**: Finding "the user who failed the most" requires looking at *every* record, not just the "top 5 chunks."
3. **Logic**: Calculating failure rates or P99 latency requires computation, not just retrieval.

LogLens solves this by using the LLM as a **programmer**, not just a searcher. It writes a `jq` program that executes locally on your logs, providing the exact data needed for a truthful, data-backed answer.

---

## License
MIT
License
MIT
