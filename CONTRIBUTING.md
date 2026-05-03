# Contributing to LogLens

First off — thank you for taking the time to contribute! LogLens is a community-driven tool and the **Skills System** is specifically designed to make it easy for anyone to extend it without touching core code.

---

## Ways to Contribute

| Type | Description |
|---|---|
| 🆕 New Skill | Write a `.toml` skill for a new log format (Kubernetes, Postgres, Redis, etc.) |
| 🐛 Bug Fix | Fix issues with parsing, JQ generation, or the CLI |
| ✨ Feature | Add new commands, improve the briefing panel, etc. |
| 📚 Docs | Improve getting-started guides, add examples |

---

## The Easiest Way to Contribute: Write a Skill

Skills are the community-extensible part of LogLens. A skill teaches the AI how to interpret a specific log format — no Python required.

### Skill File Structure

Create a `.toml` file with this format:

```toml
[meta]
name        = "my_skill"
description = "Short description of what logs this handles"
version     = "1.0"
author      = "your-github-username"

[detection]
# Field names in the logs that identify this skill
# More specific = better auto-detection
signals = ["field_one", "field_two", "field_three"]

[prompts]
domain_context = """
DOMAIN: <Name of the technology>

Key fields:
- field_one: description of what it means
- field_two: description of what it means

IMPORTANT THRESHOLDS:
- <metric> > <value>: CRITICAL
- <metric> > <value>: WARNING

Common failure patterns:
- "<log_pattern>": what it means
"""

jq_hints = """
- Primary key field: .field_one
- Status field: .status (values: "ok", "error", "timeout")
- Filter errors: select(.status == "error")
- Latency field: .duration_ms
"""
```

### Testing Your Skill

```bash
# Install it locally
loglens skills add my_skill.toml

# Verify it shows up
loglens skills list

# Test it on a real log file
loglens chat my_logs --skill my_skill
loglens skills show my_skill
```

### Opening a PR

1. Fork the repo
2. Place your skill in `skills/my_skill.toml`
3. Test it against a real log file (attach the test session output as a screenshot in the PR)
4. Open a PR with the title: `feat(skill): add <name> skill`
5. In the PR description, include:
   - What log format it handles
   - Example questions it can answer
   - A screenshot of it in action

---

## Development Setup

```bash
# Clone the repo
git clone https://github.com/ShivprasadRoul/LogLens.git
cd LogLens

# Install dependencies (requires uv)
uv sync

# Run the tests
uv run pytest tests/ -v

# Run the CLI locally
uv run python -m loglens.cli --help
```

---

## Code Style

- Python formatting: `black` / `ruff`
- Keep functions small and focused
- All CLI changes must have a corresponding test in `tests/`

---

## Reporting Bugs

Open an issue with:
1. The command you ran
2. The full error output (including traceback)
3. Your OS and Python version (`python3 --version`)
4. Your LogLens version (`loglens --version`)

---

## Questions?

Open a [GitHub Discussion](https://github.com/ShivprasadRoul/LogLens/discussions) for anything that isn't a bug or feature request.
