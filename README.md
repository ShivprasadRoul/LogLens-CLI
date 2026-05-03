<div align="center">
  <img src="https://raw.githubusercontent.com/ShivprasadRoul/LogLens/main/docs/logo.png" width="120" alt="LogLens Logo" />
  <h1>LogLens</h1>
  <p><strong>AI-Powered Log Intelligence CLI (Vectorless RAG)</strong></p>
  <p>Ask plain-English questions about massive log files, get accurate answers without a vector database.</p>
</div>

---

**LogLens** is a local CLI tool that turns gigabytes of messy, semi-structured logs into a conversational interface. Instead of using expensive, hallucination-prone vector embeddings, LogLens streams your logs to discover their schema, and then uses an LLM to write exact `jq` queries to extract the precise data needed to answer your questions.

## Features

- **Vectorless Architecture**: No embeddings, no vector DB, no chunking. 100% accurate data extraction via LLM-generated `jq` code.
- **BYOK (Bring Your Own Key)**: Use OpenAI, Anthropic, Gemini, or Groq.
- **Automatic Schema Discovery**: Ingests JSON, logfmt, Nginx, systemd, and Python tracebacks automatically.
- **Persistent Memory**: Multi-turn chat context is saved per session.
- **Skills System**: Pluggable `.toml` files let you teach the agent domain-specific knowledge about your logs.

---

## 🚀 Quick Start

### 1. Install
Run the one-line installer (supports macOS, Ubuntu/Debian, and Arch Linux):
```bash
curl -fsSL https://raw.githubusercontent.com/ShivprasadRoul/LogLens/main/install.sh | bash
```
*(Requires Python 3.9+ and `jq`)*

### 2. Configure your API Key
LogLens needs an LLM to generate `jq` queries and synthesize answers.
```bash
loglens config set-key openai <your-api-key>
```
*Optional: Change provider or model (e.g. `loglens config set-provider anthropic`)*

### 3. Ingest a Log File
Point LogLens at a log file to extract its schema and ID mappings:
```bash
loglens ingest /var/log/nginx/access.log --name my-app
```

### 4. Ask Questions
Ask one-off questions:
```bash
loglens query my-app -q "Which endpoint is throwing the most 500 errors?"
```

Or start an interactive chat session:
```bash
loglens chat my-app
```

---

## 🛠 Command Reference

### Core Commands
| Command | Description |
|---|---|
| `loglens ingest <file>` | Parse a log file and cache its schema for querying |
| `loglens query <session> -q "..."` | Ask a single question about an ingested session |
| `loglens chat <session>` | Open an interactive chat with persistent memory |
| `loglens sessions` | View a table of all cached log sessions |
| `loglens refresh <session>` | Re-ingest the log file to pick up new data |
| `loglens clear-history <session>` | Wipe the chat history for a session |

### Configuration
| Command | Description |
|---|---|
| `loglens config show` | View current active settings |
| `loglens config set-key <provider> <key>` | Save an API key securely (supports `openai`, `anthropic`, `gemini`, `groq`) |
| `loglens config set-provider <provider>` | Switch the active LLM provider |
| `loglens config set-model <model>` | Override the default model (e.g. `gpt-4o-mini`) |

---

## 🧠 The Skills System

LogLens uses a **Skills System** to understand the domain of your logs. A skill is simply a `.toml` file that tells the LLM what specific fields mean and how to query them.

View active skills:
```bash
loglens skills list
```

### Built-in Skills
- **`app_logs`**: Generic application logs (Python, Node, Java)
- **`nginx_access`**: HTTP traffic, latency, 5xx rate analysis
- **`nginx_error`**: Upstream timeouts, connection failures
- **`systemd`**: Service crashes, restart loops
- **`python_app`**: Python traceback parsing

LogLens auto-detects the right skill based on the fields found in your logs. If you want to override it, use the `--skill` flag:
```bash
loglens chat my-app --skill nginx_access
```

### Writing a Custom Skill
You can teach LogLens about your proprietary log formats by creating a custom skill:

**`my_custom_skill.toml`**
```toml
[meta]
name = "my_custom_skill"
description = "Analysis for my custom billing service logs"

[detection]
signals = ["billing_id", "stripe_customer", "invoice_status"]

[prompts]
domain_context = """
DOMAIN: Billing Service Logs.
Focus on 'invoice_status' == 'failed'. A failure rate > 2% is CRITICAL.
"""
jq_hints = """
- Invoice ID: .billing_id
- Customer: .stripe_customer
"""
```

Install it with:
```bash
loglens skills add my_custom_skill.toml
```

---

## 🏗 Architecture: How Vectorless RAG Works

Unlike traditional RAG (Retrieval-Augmented Generation) which chunks logs and stores them in a Vector Database (often resulting in hallucinated or missing data during exact-match queries), LogLens guarantees 100% data extraction accuracy.

1. **Schema Discovery**: `ijson` streams your log file and maps the exact schema, data types, and occurrence rates of every field.
2. **Context Injection**: The Agent loads the schema + domain context (from Skills).
3. **Pass 1 (Exploration)**: The LLM writes a `jq` query to sample 3 raw records to confirm the exact data structure.
4. **Pass 2 (Extraction)**: The LLM writes a precise `jq` query to filter, group, and aggregate the data.
5. **Synthesis**: The exact JSON output of the `jq` command is fed back to the LLM to write a natural language response.

*If the `jq` query fails, the LLM is fed the exact stderr from the bash execution and retries up to 3 times.*

---

## Contributing

1. Clone the repo
2. Install `uv` (the Python package manager)
3. Run `uv sync` to install dependencies
4. Run `uv run pytest tests/` to verify tests pass

## License
MIT
