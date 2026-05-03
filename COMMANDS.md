# LogLens — Complete Command Reference

> All commands follow the pattern: `loglens <command> [arguments] [options]`
> Run `loglens --help` or `loglens <command> --help` for live help in the terminal.

---

## Table of Contents

1. [Core Commands](#core-commands)
   - [ingest](#ingest)
   - [query](#query)
   - [chat](#chat)
   - [sessions](#sessions)
   - [refresh](#refresh)
   - [clear-history](#clear-history)
   - [delete](#delete)
   - [update](#update)
2. [Config Commands](#config-commands)
   - [config show](#config-show)
   - [config set-key](#config-set-key)
   - [config set-provider](#config-set-provider)
   - [config set-model](#config-set-model)
3. [Skills Commands](#skills-commands)
   - [skills list](#skills-list)
   - [skills show](#skills-show)
   - [skills add](#skills-add)
   - [skills remove](#skills-remove)
4. [In-Chat Commands](#in-chat-commands)
5. [Global Flags](#global-flags)
6. [Environment Variables](#environment-variables)

---

## Core Commands

### `ingest`

Parse a log file and cache its schema, ID map, and records for querying.
This must be run once before you can `query` or `chat` a session.

```bash
loglens ingest <log_file> [OPTIONS]
```

| Argument / Option | Type | Default | Description |
|---|---|---|---|
| `log_file` | `PATH` | **required** | Path to the log file to ingest |
| `-n, --name TEXT` | string | filename stem | Custom session name |
| `-f, --force` | flag | `false` | Re-ingest even if the session already exists |

**Examples:**
```bash
# Basic ingest — session name defaults to "access"
loglens ingest /var/log/nginx/access.log

# Custom session name
loglens ingest /var/log/nginx/access.log --name prod-nginx

# Force re-ingest (overwrite existing session)
loglens ingest /var/log/app.log --name myapp --force
loglens ingest /var/log/app.log --name myapp -f
```

**Output:** Progress bar with 4 stages (Parse → Schema → ID Map → Save), then a summary panel showing record count, field count, and unique IDs found.

---

### `query`

Ask a single one-off question about an ingested session. Does not open an interactive session.

```bash
loglens query <session> [OPTIONS]
```

| Argument / Option | Type | Default | Description |
|---|---|---|---|
| `session` | string | **required** | Name of the ingested session |
| `-q, --query TEXT` | string | **required** | Your question in plain English |
| `--show-jq` | flag | `false` | Print the generated `jq` program after the answer |
| `--save-history / --no-history` | flag | `--save-history` | Save this Q&A turn to session history |
| `--skill TEXT` | string | auto-detect | Force a specific skill (e.g. `nginx_access`) |

**Examples:**
```bash
# Basic query
loglens query prod-nginx -q "which endpoint has the most 500 errors?"

# Show the jq program that was generated
loglens query myapp -q "what errors happened after 6pm?" --show-jq

# Query without saving to history
loglens query myapp -q "how many records are there?" --no-history

# Force a specific skill
loglens query myapp -q "why did the publish api fail?" --skill app_logs
```

**Output:** A green **Copilot** panel (answer + details) followed by a red-bordered **Evidence** panel (raw log lines), then a footer showing retrieval passes, model, and skill.

---

### `chat`

Open an interactive multi-turn conversation with persistent memory. Starts with an auto-briefing scan.

```bash
loglens chat <session> [OPTIONS]
```

| Argument / Option | Type | Default | Description |
|---|---|---|---|
| `session` | string | **required** | Name of the ingested session |
| `--show-jq` | flag | `false` | Print the generated `jq` program after every answer |
| `--skill TEXT` | string | auto-detect | Force a specific skill |

**Examples:**
```bash
# Standard chat
loglens chat prod-nginx

# Chat with jq programs shown
loglens chat myapp --show-jq

# Force nginx skill on a mixed log file
loglens chat myapp --skill nginx_access
```

**Exit chat:** Type `exit`, `quit`, `bye`, or press `Ctrl+C`.

**Resuming:** If a session has existing history, chat resumes from where you left off (shows "Resuming — N turns in memory"). Use `/clear` to start fresh.

---

### `sessions`

List all ingested log sessions with metadata.

```bash
loglens sessions
```

**No options.** Displays a table with:

| Column | Description |
|---|---|
| Session | Session name |
| Records | Number of parsed log records |
| Fields | Number of discovered schema fields |
| Ingested At | Timestamp of last ingest |
| Source File | Original log file name |
| History | Number of chat turns in memory |

---

### `refresh`

Re-parse the original log file for a session. Use this when the log file has new entries. Keeps chat history by default.

```bash
loglens refresh <session> [OPTIONS]
```

| Argument / Option | Type | Default | Description |
|---|---|---|---|
| `session` | string | **required** | Session name to re-ingest |
| `--keep-history / --clear-history` | flag | `--keep-history` | Whether to preserve conversation history |

**Examples:**
```bash
# Refresh and keep existing chat history
loglens refresh prod-nginx

# Refresh and also wipe chat history
loglens refresh prod-nginx --clear-history
```

**Note:** Requires the original log file to still exist at the path recorded during ingest. If the file was moved, ingest again with the new path.

---

### `clear-history`

Delete all conversation history for a session. Keeps the schema, ID map, and records intact — only wipes the chat turns.

```bash
loglens clear-history <session>
```

| Argument | Type | Description |
|---|---|---|
| `session` | string | Session name to clear history for |

**Example:**
```bash
loglens clear-history myapp
```

**Use case:** When the LLM is confused by old context, or you want to start a fresh conversation about the same log file without re-ingesting.

---

### `delete`

Permanently delete a session and all its cached data (schema, ID map, records, history).

```bash
loglens delete <session> [OPTIONS]
```

| Argument / Option | Type | Default | Description |
|---|---|---|---|
| `session` | string | **required** | Session name to delete |
| `-f, --force` | flag | `false` | Skip the confirmation prompt |

**Examples:**
```bash
# With confirmation prompt
loglens delete old-logs

# Skip confirmation
loglens delete old-logs --force
loglens delete old-logs -f
```

---

### `update`

Pull the latest LogLens code from GitHub. Self-update.

```bash
loglens update
```

**No options.** Runs `git pull --ff-only` in `~/.loglens/install/`.

**Requirements:** Must have been installed via `install.sh`. If installed from source, run `git pull` manually.

---

## Config Commands

### `config show`

Print the current active configuration. API keys are masked (shows first 8 and last 4 characters).

```bash
loglens config show
```

**Output example:**
```json
{
  "llm_provider": "openai",
  "model": "gpt-4o",
  "api_keys": {
    "openai": "sk-proj-AB...wxyz",
    "anthropic": "sk-ant-CD...abcd"
  },
  "max_retries": 3,
  "max_jq_bytes": 200000,
  "history_window": 20
}
Config file: /Users/you/.loglens/config.json
```

---

### `config set-key`

Save an API key for a provider. Keys are stored in `~/.loglens/config.json` with `600` permissions (owner read/write only).

```bash
loglens config set-key <provider> <key>
```

| Argument | Values | Environment fallback |
|---|---|---|
| `openai` | `sk-...` | `OPENAI_API_KEY` |
| `anthropic` | `sk-ant-...` | `ANTHROPIC_API_KEY` |
| `groq` | `gsk_...` | `GROQ_API_KEY` |
| `gemini` | `AIza...` | `GEMINI_API_KEY` |

**Examples:**
```bash
loglens config set-key openai sk-proj-...
loglens config set-key anthropic sk-ant-...
loglens config set-key groq gsk_...
loglens config set-key gemini AIza...
```

**Note:** If no key is set in config, LogLens automatically falls back to the corresponding environment variable.

---

### `config set-provider`

Switch the active LLM provider. Also resets the model to that provider's default.

```bash
loglens config set-provider [provider]
```

| Argument | Description |
|---|---|
| `provider` (optional) | One of `openai`, `anthropic`, `groq`, `gemini`. If omitted, opens an interactive picker. |

**Interactive picker** (no argument): Shows all providers, marks which ones have API keys configured, and which is currently active. Enter a number or provider name.

**Examples:**
```bash
# Direct set
loglens config set-provider anthropic
loglens config set-provider groq

# Interactive picker
loglens config set-provider
```

**Default models per provider:**

| Provider | Default Model |
|---|---|
| `openai` | `gpt-4o` |
| `anthropic` | `claude-opus-4-5` |
| `groq` | `llama-3.3-70b-versatile` |
| `gemini` | `gemini-1.5-pro` |

---

### `config set-model`

Set the model for the currently active provider.

```bash
loglens config set-model [model]
```

| Argument | Description |
|---|---|
| `model` (optional) | Model name (e.g. `gpt-4o-mini`). If omitted, opens an interactive picker. |

**Interactive picker** (no argument): Shows a categorized list of models for the active provider. You can also type any custom model name not in the list.

**Examples:**
```bash
# Direct set
loglens config set-model gpt-4o-mini
loglens config set-model claude-haiku-3-5
loglens config set-model llama-3.1-8b-instant

# Interactive picker
loglens config set-model
```

**Available models by provider:**

| Provider | Category | Models |
|---|---|---|
| `openai` | Frontier | `gpt-5.5`, `gpt-5.4`, `gpt-5.4-mini`, `gpt-5.4-nano` |
| `openai` | GPT-5 | `gpt-5`, `gpt-5.2`, `gpt-5.1`, `gpt-5-mini`, `gpt-5-nano` |
| `openai` | Production | `gpt-4.1`, `gpt-4o`, `gpt-4o-mini` |
| `anthropic` | Core LLMs | `claude-opus-4-5`, `claude-sonnet-4-5`, `claude-haiku-3-5` |
| `groq` | Core LLMs | `llama-3.3-70b-versatile`, `llama-3.1-8b-instant`, `mixtral-8x7b-32768` |
| `gemini` | Core LLMs | `gemini-2.5-pro`, `gemini-2.5-flash`, `gemini-1.5-pro`, `gemini-1.5-flash` |

---

## Skills Commands

### `skills list`

List all available skills — both built-in and user-installed.

```bash
loglens skills list
```

**No options.** Displays a table with: Name, Type (Built-in / User), Description, Detection Signals.

---

### `skills show`

Print the full configuration of a skill — its domain context and JQ hints.

```bash
loglens skills show <name>
```

| Argument | Description |
|---|---|
| `name` | Skill name (from `skills list`) |

**Examples:**
```bash
loglens skills show nginx_access
loglens skills show app_logs
loglens skills show my_custom_skill
```

**Output:** Shows skill description, author, version, source path, detection signals, full domain context, and full JQ hints.

---

### `skills add`

Install a custom skill from a `.toml` file. Copies it to `~/.loglens/skills/`.

```bash
loglens skills add <file_path>
```

| Argument | Description |
|---|---|
| `file_path` | Path to the `.toml` skill file |

**Examples:**
```bash
loglens skills add ./my_billing_skill.toml
loglens skills add /path/to/kubernetes.toml
```

**Skill file structure:**
```toml
[meta]
name        = "my_skill"
description = "What this skill handles"
version     = "1.0"
author      = "your-name"

[detection]
signals = ["field_one", "field_two"]

[prompts]
domain_context = """..."""
jq_hints = """..."""
```

---

### `skills remove`

Remove a user-installed skill. Cannot remove built-in skills.

```bash
loglens skills remove <name>
```

| Argument | Description |
|---|---|
| `name` | Name of the user-installed skill to remove |

**Example:**
```bash
loglens skills remove my_billing_skill
```

---

## In-Chat Commands

These commands are typed inside an active `loglens chat` session.

| Command | Aliases | Description |
|---|---|---|
| `/help` | `/h`, `/?` | Show available in-chat commands |
| `/clear` | `/reset` | Wipe conversation history for this session and start fresh |
| `/jq` | — | Toggle displaying the generated `jq` program after each answer |
| `/sessions` | — | List all available sessions without leaving chat |
| `exit` | `quit`, `bye` | End the chat session |
| `Ctrl+C` | `Ctrl+D` | Force-quit the chat session |

---

## Global Flags

These apply to the `loglens` root command:

| Flag | Description |
|---|---|
| `--help` | Show help for any command |
| `--version` | Show the installed LogLens version |
| `--install-completion` | Install shell tab completion |
| `--show-completion` | Show the completion script for your shell |

**Examples:**
```bash
loglens --help
loglens ingest --help
loglens config --help
loglens skills --help
```

---

## Environment Variables

These environment variables can be used instead of (or as fallback for) API keys stored in config.

| Variable | Provider | Example |
|---|---|---|
| `OPENAI_API_KEY` | OpenAI | `export OPENAI_API_KEY=sk-proj-...` |
| `ANTHROPIC_API_KEY` | Anthropic | `export ANTHROPIC_API_KEY=sk-ant-...` |
| `GROQ_API_KEY` | Groq | `export GROQ_API_KEY=gsk_...` |
| `GEMINI_API_KEY` | Google Gemini | `export GEMINI_API_KEY=AIza...` |

**Priority order:** Config file (`~/.loglens/config.json`) takes precedence over environment variables.

---

## Quick Reference Card

```
loglens ingest <file>                          Parse a log file into a session
loglens ingest <file> --name myapp            Custom session name
loglens ingest <file> --force                 Force re-ingest

loglens query <session> -q "..."              Ask a single question
loglens query <session> -q "..." --show-jq    Show generated jq too
loglens query <session> -q "..." --skill X    Force a specific skill

loglens chat <session>                         Interactive multi-turn chat
loglens chat <session> --show-jq              Always show jq in chat
loglens chat <session> --skill X              Force a specific skill

loglens sessions                               List all sessions
loglens refresh <session>                      Re-parse (keep history)
loglens refresh <session> --clear-history      Re-parse and wipe history
loglens clear-history <session>                Wipe history only
loglens delete <session>                       Delete session (with prompt)
loglens delete <session> --force               Delete without prompt
loglens update                                 Self-update from GitHub

loglens config show                            Show current config
loglens config set-key openai sk-...          Save OpenAI API key
loglens config set-provider                   Interactive provider picker
loglens config set-provider anthropic         Set provider directly
loglens config set-model                      Interactive model picker
loglens config set-model gpt-4o-mini          Set model directly

loglens skills list                            List all skills
loglens skills show <name>                     View skill details
loglens skills add <file.toml>                Install custom skill
loglens skills remove <name>                   Remove custom skill
```
