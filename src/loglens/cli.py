"""Main CLI entry point using Typer."""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

import typer
from rich import box
from rich.columns import Columns
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.rule import Rule
from rich.table import Table
from rich.text import Text
from rich.theme import Theme

# Local imports
from loglens import config as cfg
from loglens import memory
from loglens.agent import LogAgent
from loglens.id_map import IDMapper
from loglens.parser import LogParser
from loglens.schema import SchemaDiscovery

# ── Theme & Console ───────────────────────────────────────────────────────────

_THEME = Theme({
    "info":     "bold blue",
    "success":  "bold green",
    "warning":  "bold yellow",
    "error":    "bold red",
    "muted":    "dim white",
    "level.debug":    "dim cyan",
    "level.info":     "green",
    "level.warning":  "yellow",
    "level.error":    "bold red",
    "level.critical": "bold red on white",
    "copilot":  "bold green",
    "session":  "bold cyan",
})

console = Console(theme=_THEME)

# ── Log level color map ───────────────────────────────────────────────────────

LEVEL_COLORS = {
    "debug":    "[level.debug]",
    "info":     "[level.info]",
    "warning":  "[level.warning]",
    "warn":     "[level.warning]",
    "error":    "[level.error]",
    "critical": "[level.critical]",
}

def _level_badge(level: str) -> str:
    lvl = level.lower()
    color = LEVEL_COLORS.get(lvl, "[dim]")
    end = color.replace("[", "[/").replace("level.", "level.")
    # Build proper closing tag
    tag = color.strip("[]")
    return f"[{tag}]{level.upper():>8}[/{tag}]"

# ── App Setup ─────────────────────────────────────────────────────────────────

app = typer.Typer(
    name="loglens",
    help="AI-Powered Log Intelligence CLI — ask plain English questions about any log file.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)
config_app = typer.Typer(help="Manage LogLens config (API keys, provider, model).")
app.add_typer(config_app, name="config")

SESSIONS_DIR = Path(".loglens/sessions")

# ── UI Helpers ────────────────────────────────────────────────────────────────

def _header(title: str, subtitle: str = "") -> None:
    """Print a styled section header."""
    console.print()
    console.print(Rule(f"[bold blue]{title}[/bold blue]", style="blue"))
    if subtitle:
        console.print(f"[muted]{subtitle}[/muted]")
    console.print()


def _print_answer(result: dict, show_jq: bool = False) -> None:
    """Render the Copilot answer in a rich panel with footer."""
    answer_md = Markdown(result["answer"])
    passes = result["attempts"]
    model  = cfg.get_model()
    jq     = result.get("jq_program", "")

    # Main answer panel
    console.print(Panel(
        answer_md,
        title="[copilot] Copilot[/copilot]",
        border_style="green",
        padding=(1, 2),
    ))

    # Footer row — passes + model
    footer = Text()
    footer.append(f" {passes} retrieval pass{'es' if passes != 1 else ''}", style="muted")
    footer.append("  ·  ", style="muted")
    footer.append(f"model: {model}", style="muted")
    console.print(footer)

    # Optional JQ block
    if show_jq and jq:
        console.print(Panel(
            f"[cyan]{jq}[/cyan]",
            title="[dim]Generated JQ[/dim]",
            border_style="dim",
            padding=(0, 1),
        ))


def _get_session_dir(session: str) -> Path:
    return SESSIONS_DIR / session


def _require_session(session: str) -> Path:
    session_dir = _get_session_dir(session)
    if not session_dir.exists():
        console.print(f"[error]Error:[/error] Session '[session]{session}[/session]' not found.")
        console.print("Run [cyan]loglens ingest <file>[/cyan] first.")
        raise typer.Exit(1)
    return session_dir


def _build_agent() -> LogAgent:
    provider = cfg.get_active_provider()
    api_key  = cfg.get_api_key(provider)
    model    = cfg.get_model(provider)

    if not api_key:
        console.print(f"[error]Error:[/error] No API key for provider '[bold]{provider}[/bold]'.")
        console.print(
            f"Set it with: [cyan]loglens config set-key {provider} <your-key>[/cyan]\n"
            f"Or: [cyan]export {cfg.PROVIDERS[provider]['env']}=<key>[/cyan]"
        )
        raise typer.Exit(1)

    return LogAgent(api_key=api_key, model=model)


# ── ingest ────────────────────────────────────────────────────────────────────

@app.command()
def ingest(
    log_file: Path = typer.Argument(..., help="Path to the log file"),
    session_name: Optional[str] = typer.Option(None, "--name", "-n", help="Session name (defaults to filename stem)"),
    force: bool = typer.Option(False, "--force", "-f", help="Force re-ingest even if session exists"),
) -> None:
    """Parse a log file and cache schema, ID map, and records for querying."""
    if not log_file.exists():
        console.print(f"[error]Error:[/error] File not found: {log_file}")
        raise typer.Exit(1)

    name = session_name or log_file.stem
    session_dir = _get_session_dir(name)

    if session_dir.exists() and not force:
        console.print(f"[warning]Session '[bold]{name}[/bold]' already exists.[/warning] Use --force to re-ingest.")
        return

    session_dir.mkdir(parents=True, exist_ok=True)

    file_size_mb = log_file.stat().st_size / (1024 * 1024)
    _header(
        "LogLens — Ingest",
        f"File: {log_file.name}  ({file_size_mb:.1f} MB)  →  Session: {name}"
    )

    with Progress(
        SpinnerColumn(spinner_name="dots"),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(bar_width=30),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        console=console,
        transient=False,
    ) as progress:

        # 1. Parse — stream with live count
        task_parse = progress.add_task("[cyan]Parsing records...", total=None)
        parser = LogParser()
        records = []
        try:
            for i, record in enumerate(parser.parse_file_stream(log_file)):
                records.append(record)
                if i % 500 == 0:
                    progress.update(task_parse, description=f"[cyan]Parsing... {i:,} records")
        except Exception as e:
            console.print(f"[error]Parse error:[/error] {e}")
            raise typer.Exit(1)

        progress.update(
            task_parse,
            total=len(records), completed=len(records),
            description=f"[success]✓ Parsed {len(records):,} records[/success]"
        )

        # 2. Schema
        task_schema = progress.add_task("[cyan]Discovering schema...", total=len(records))
        discovery = SchemaDiscovery()
        for i, r in enumerate(records):
            discovery.process_record(r)
            progress.update(task_schema, completed=i + 1)
        discovery.save_schema(session_dir / "schema.json")
        fields = len(discovery.field_metadata)
        progress.update(task_schema, description=f"[success]✓ Schema — {fields} fields[/success]")

        # 3. ID Map
        task_idmap = progress.add_task("[cyan]Building ID map...", total=len(records))
        mapper = IDMapper()
        for i, r in enumerate(records):
            mapper._scan_record(r, i)
            progress.update(task_idmap, completed=i + 1)
        mapper.save(session_dir / "id_map.json")
        progress.update(task_idmap, description=f"[success]✓ ID map — {len(mapper.id_map):,} unique IDs[/success]")

        # 4. Save
        task_save = progress.add_task("[cyan]Saving session...", total=None)
        with open(session_dir / "records.json", "w") as f:
            json.dump(records, f)
        metadata = {
            "source": str(log_file.absolute()),
            "record_count": len(records),
            "ingested_at": datetime.utcnow().isoformat() + "Z",
            "fields": fields,
        }
        with open(session_dir / "metadata.json", "w") as f:
            json.dump(metadata, f, indent=2)
        progress.update(task_save, total=1, completed=1, description="[success]✓ Session saved[/success]")

    # Summary panel
    summary = Table.grid(padding=(0, 2))
    summary.add_column(style="muted")
    summary.add_column(style="bold")
    summary.add_row("Session",  name)
    summary.add_row("Records",  f"{len(records):,}")
    summary.add_row("Fields",   str(fields))
    summary.add_row("Unique IDs", f"{len(mapper.id_map):,}")
    summary.add_row("Cached at", str(session_dir))

    console.print(Panel(summary, title="[success]Ready[/success]", border_style="green", padding=(1, 2)))
    console.print(f"[muted]Next: [cyan]loglens chat {name}[/cyan][/muted]\n")


# ── query ─────────────────────────────────────────────────────────────────────

@app.command()
def query(
    session: str = typer.Argument(..., help="Session name"),
    question: str = typer.Option(..., "--query", "-q", help="Question in plain English"),
    show_jq: bool = typer.Option(False, "--show-jq", help="Print the generated JQ program"),
    save_history: bool = typer.Option(True, "--save-history/--no-history", help="Save this Q&A to session history"),
) -> None:
    """Ask a one-off question about an ingested log session."""
    session_dir = _require_session(session)
    agent = _build_agent()

    hist = memory.trim(memory.load(session_dir), cfg.load().get("history_window", 20))

    _header("LogLens — Query", f"Session: {session}")
    console.print(Panel(f"[bold]{question}[/bold]", title="[dim]Question[/dim]", border_style="dim", padding=(0, 2)))
    console.print()

    with console.status("[bold green]Analyzing logs...[/bold green]", spinner="dots"):
        try:
            result = agent.query(session_dir, question, history=hist)
        except Exception as e:
            console.print(f"[error]Error:[/error] {e}")
            raise typer.Exit(1)

    _print_answer(result, show_jq=show_jq)

    if save_history:
        memory.append_turn(session_dir, question, result["answer"])


# ── chat ──────────────────────────────────────────────────────────────────────

@app.command()
def chat(
    session: str = typer.Argument(..., help="Session name"),
    show_jq: bool = typer.Option(False, "--show-jq", help="Print the generated JQ program after each answer"),
) -> None:
    """Start an interactive chat session with persistent memory."""
    session_dir = _require_session(session)
    agent = _build_agent()
    window = cfg.load().get("history_window", 20)

    history = memory.load(session_dir)
    hist_summary = memory.summary(session_dir)

    _header(
        "LogLens Chat",
        f"Session: {session}  ·  Model: {cfg.get_model()}  ·  Type 'exit' to quit"
    )

    if hist_summary["turns"] > 0:
        console.print(f"[muted]↩  Resuming — {hist_summary['turns']} previous turn(s) in memory.[/muted]\n")

    turn = 0
    while True:
        try:
            turn += 1
            question = console.input(f"[bold cyan]You[/bold cyan] [dim]#{turn}[/dim]  ")
        except (EOFError, KeyboardInterrupt):
            console.print("\n[muted]Goodbye![/muted]")
            break

        q = question.strip()
        if not q:
            turn -= 1
            continue
        if q.lower() in ("exit", "quit", "bye"):
            console.print("[muted]Goodbye![/muted]")
            break

        windowed_history = memory.trim(history, window)

        with console.status("[bold green]Thinking...[/bold green]", spinner="dots"):
            try:
                result = agent.query(session_dir, q, history=windowed_history)
            except Exception as e:
                console.print(f"[error]Error:[/error] {e}")
                continue

        console.print()
        _print_answer(result, show_jq=show_jq)
        console.print()
        console.print(Rule(style="dim"))
        console.print()

        history.append({"role": "user",      "content": q})
        history.append({"role": "assistant",  "content": result["answer"]})
        memory.save(session_dir, history)


# ── sessions ──────────────────────────────────────────────────────────────────

@app.command()
def sessions() -> None:
    """List all cached log sessions."""
    if not SESSIONS_DIR.exists() or not any(SESSIONS_DIR.iterdir()):
        console.print("[warning]No sessions found.[/warning] Run [cyan]loglens ingest <file>[/cyan] to create one.")
        return

    table = Table(
        title="LogLens Sessions",
        header_style="bold blue",
        border_style="dim",
        box=box.ROUNDED,
        show_lines=True,
    )
    table.add_column("Session",    style="bold cyan")
    table.add_column("Records",    justify="right")
    table.add_column("Fields",     justify="right")
    table.add_column("Ingested At")
    table.add_column("Source File", style="dim")
    table.add_column("History",    justify="right")

    for session_dir in sorted(SESSIONS_DIR.iterdir()):
        if not session_dir.is_dir():
            continue
        meta_path = session_dir / "metadata.json"
        if not meta_path.exists():
            continue
        with open(meta_path) as f:
            meta = json.load(f)

        hist = memory.summary(session_dir)
        turns_str = f"[green]{hist['turns']} turns[/green]" if hist["turns"] > 0 else "[muted]0 turns[/muted]"
        table.add_row(
            session_dir.name,
            f"{meta.get('record_count', '?'):,}",
            str(meta.get("fields", "?")),
            meta.get("ingested_at", "?")[:19].replace("T", " "),
            Path(meta.get("source", "?")).name,
            turns_str,
        )

    console.print(table)


# ── refresh ───────────────────────────────────────────────────────────────────

@app.command()
def refresh(
    session: str = typer.Argument(..., help="Session name to re-ingest"),
    keep_history: bool = typer.Option(True, "--keep-history/--clear-history", help="Keep conversation history"),
) -> None:
    """Force re-parse and re-cache a session."""
    session_dir = _require_session(session)

    meta_path = session_dir / "metadata.json"
    if not meta_path.exists():
        console.print("[error]Error:[/error] Session metadata missing.")
        raise typer.Exit(1)

    with open(meta_path) as f:
        meta = json.load(f)
    source = Path(meta.get("source", ""))

    if not source.exists():
        console.print(f"[error]Error:[/error] Original log file not found: {source}")
        raise typer.Exit(1)

    saved_history = memory.load(session_dir) if keep_history else []

    import shutil
    shutil.rmtree(session_dir)
    session_dir.mkdir(parents=True, exist_ok=True)

    if keep_history and saved_history:
        memory.save(session_dir, saved_history)
        console.print(f"[muted]History preserved ({len(saved_history) // 2} turns).[/muted]")

    # Delegate to ingest
    ingest(log_file=source, session_name=session, force=True)


# ── clear-history ─────────────────────────────────────────────────────────────

@app.command(name="clear-history")
def clear_history(session: str = typer.Argument(..., help="Session name")) -> None:
    """Wipe conversation history for a session (keeps schema and records)."""
    session_dir = _require_session(session)
    hist = memory.summary(session_dir)
    if hist["turns"] == 0:
        console.print(f"[warning]No history to clear for '[bold]{session}[/bold]'.[/warning]")
        return
    memory.clear(session_dir)
    console.print(f"[success]✓[/success] Cleared {hist['turns']} turn(s) from '[bold]{session}[/bold]'.")


# ── config subcommands ────────────────────────────────────────────────────────

@config_app.command(name="show")
def config_show() -> None:
    """Print current config (API keys masked)."""
    current = cfg.masked(cfg.load())
    console.print_json(json.dumps(current, indent=2))
    console.print(f"\n[muted]Config file: {cfg.CONFIG_PATH}[/muted]")


@config_app.command(name="set-key")
def config_set_key(
    provider: str = typer.Argument(..., help=f"Provider: {', '.join(cfg.PROVIDERS)}"),
    key: str = typer.Argument(..., help="Your API key"),
) -> None:
    """Store an API key for a provider."""
    try:
        cfg.set_key(provider, key)
        console.print(f"[success]✓[/success] API key saved for [bold]{provider}[/bold].")
    except ValueError as e:
        console.print(f"[error]Error:[/error] {e}")
        raise typer.Exit(1)


@config_app.command(name="set-provider")
def config_set_provider(
    provider: str = typer.Argument(..., help=f"Provider: {', '.join(cfg.PROVIDERS)}"),
) -> None:
    """Switch the active LLM provider."""
    try:
        cfg.set_provider(provider)
        model = cfg.PROVIDERS[provider]["default_model"]
        console.print(f"[success]✓[/success] Provider: [bold]{provider}[/bold] (model: {model})")
    except ValueError as e:
        console.print(f"[error]Error:[/error] {e}")
        raise typer.Exit(1)


@config_app.command(name="set-model")
def config_set_model(
    model: str = typer.Argument(..., help="Model name (e.g. gpt-4o-mini, claude-haiku-4-5)"),
) -> None:
    """Override the model for the active provider."""
    cfg.set_model(model)
    provider = cfg.get_active_provider()
    console.print(f"[success]✓[/success] Model → [bold]{model}[/bold] for [bold]{provider}[/bold].")


if __name__ == "__main__":
    app()
