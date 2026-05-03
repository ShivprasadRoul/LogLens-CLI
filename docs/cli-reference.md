# CLI Reference

LogLens uses a hierarchical command structure powered by [Typer](https://typer.tiangolo.com/).

## Core Commands

### `loglens ingest <log_file>`
Discover the schema of a log file and cache it for analysis.

**Usage:**
```bash
loglens ingest /var/log/nginx/access.log --name my-app
```

**Arguments:**
- `log_file`: Path to the log file (JSON, logfmt, or unstructured).

**Options:**
- `-n, --name TEXT`: Custom session name (defaults to filename without extension).
- `-f, --force`: Overwrite the session if it already exists.

---

### `loglens query <session>`
Ask a one-off question about an ingested session.

**Usage:**
```bash
loglens query my-app -q "which endpoint has the most 500 errors?" --show-jq
```

**Arguments:**
- `session`: The name of the session (created during ingest).

**Options:**
- `-q, --query TEXT`: Your question in plain English. **[Required]**
- `--show-jq`: Print the generated `jq` program used to find the answer.
- `--no-history`: Do not save this Q&A to the session's conversation history.
- `--skill TEXT`: Force a specific skill (e.g. `nginx_access`) instead of auto-detecting.

---

### `loglens chat <session>`
Start an interactive, multi-turn conversation with persistent memory.

**Usage:**
```bash
loglens chat my-app --skill app_logs
```

**Options:**
- `--show-jq`: Print the generated `jq` program after every response.
- `--skill TEXT`: Force a specific skill.

**Special In-Chat Commands:**
- `/help`: Show available chat commands.
- `/clear`: Wipe the conversation history for this session (starts a fresh context).
- `/jq`: Toggle displaying the generated `jq` programs.
- `/sessions`: List all available sessions without leaving the chat.
- `exit` / `quit`: Close the chat session.

---

### `loglens sessions`
List all ingested log sessions with metadata (record count, field count, ingest time, and history status).

**Usage:**
```bash
loglens sessions
```

---

### `loglens refresh <session>`
Re-parse the original log file to pick up new entries.

**Usage:**
```bash
loglens refresh my-app --clear-history
```

**Options:**
- `--keep-history` / `--clear-history`: Whether to preserve existing chat history (default: keep).

---

### `loglens clear-history <session>`
Delete all conversation history for a specific session. This helps when the AI gets "confused" by old context.

**Usage:**
```bash
loglens clear-history my-app
```

---

### `loglens delete <session>`
Permanently remove a session and all its cached data.

**Usage:**
```bash
loglens delete my-app --force
```

**Options:**
- `-f, --force`: Delete immediately without asking for confirmation.

---

### `loglens update`
Automatically update LogLens to the latest version by pulling from the main GitHub repository.

**Usage:**
```bash
loglens update
```

---

## Configuration Commands (`loglens config`)

Manage your API keys, preferred LLM providers, and models.

### `loglens config show`
Display your current active configuration. API keys are masked for security.

### `loglens config set-key <provider> <key>`
Save an API key for a provider.
- **Providers:** `openai`, `anthropic`, `gemini`, `groq`.

### `loglens config set-provider [provider]`
Switch the active provider. If `provider` is omitted, an interactive picker will open showing which providers have keys configured.

### `loglens config set-model [model]`
Switch the active model for the current provider. If `model` is omitted, an interactive picker will open showing a curated list of models (e.g. GPT-4o, Claude 3.5 Sonnet, etc.).

---

## Skills Management (`loglens skills`)

Skills are plugins that provide domain knowledge for specific log formats.

### `loglens skills list`
List all available skills (Built-in and User-installed).

### `loglens skills show <name>`
Show the full details of a skill, including its domain context and the `jq` hints it provides to the LLM.

### `loglens skills add <file_path>`
Install a custom skill from a `.toml` file. This is how you teach LogLens about your proprietary log formats.

### `loglens skills remove <name>`
Remove a user-installed skill.
