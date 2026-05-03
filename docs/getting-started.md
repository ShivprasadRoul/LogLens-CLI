# Getting Started with LogLens

## Prerequisites

| Requirement | Version | Check |
|---|---|---|
| Python | 3.9+ | `python3 --version` |
| jq | any | `jq --version` |
| git | any | `git --version` |

Install `jq` if missing:
```bash
# macOS
brew install jq

# Ubuntu/Debian
sudo apt install jq

# Arch
sudo pacman -S jq
```

---

## Installation

Run the one-line installer:
```bash
curl -fsSL https://raw.githubusercontent.com/ShivprasadRoul/LogLens/main/install.sh | bash
```

This will:
1. Clone the repo to `~/.loglens/install/`
2. Create a Python virtual environment with `uv`
3. Install a `loglens` shell wrapper to `~/.local/bin/`

Verify it worked:
```bash
loglens --help
```

---

## Configure an API Key

LogLens uses an LLM to generate `jq` queries. You need an API key from one of the supported providers:

```bash
# OpenAI (default)
loglens config set-key openai sk-...

# Anthropic
loglens config set-key anthropic sk-ant-...

# Groq (free tier available)
loglens config set-key groq gsk_...

# Google Gemini
loglens config set-key gemini AIza...
```

Check your current config:
```bash
loglens config show
```

---

## Ingest a Log File

Point LogLens at any log file:
```bash
loglens ingest /var/log/nginx/access.log
```

LogLens will:
- Stream the file to discover its schema
- Build an ID-to-name mapping for cross-referencing
- Cache everything under `~/.loglens/sessions/<name>/`

By default the session name is the filename without extension. Override it:
```bash
loglens ingest /path/to/prod.log --name production
```

---

## Ask Your First Question

**One-off query:**
```bash
loglens query production -q "which endpoint has the most 500 errors?"
```

**Interactive chat:**
```bash
loglens chat production
```

When you open chat, LogLens instantly scans your logs and shows a briefing:
```
Loaded: prod.log (12.4 MB) · 45,231 records · skill: nginx_access+app_logs

Detected:
  ⚠  3 server errors (5xx)
  ⚠  142 client errors (4xx)

Top failing endpoints:
  ✗  GET /v1/study  (10 errors)
  ✗  PUT /v1/study/publish  (1 error)

Try asking:
  • why did study api fail?
  • show me all server errors
  • which endpoint is most unstable?
```

---

## Keeping LogLens Updated

```bash
# Pull latest changes
loglens update

# Or manually
cd ~/.loglens/install && git pull
```
