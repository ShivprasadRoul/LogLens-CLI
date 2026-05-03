"""Main CLI entry point using Typer."""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.table import Table

# Local imports
from loglens import config as cfg
from loglens import memory
from loglens.agent import LogAgent
from loglens.id_map import IDMapper
from loglens.parser import LogParser
from loglens.schema import SchemaDiscovery

# ── App Setup ────────────────────────────────────────────────────────────────

app = typer.Typer(
    name="loglens",
    help="AI-Powered Log Intelligence CLI — ask plain English questions about any log file.",
    no_args_is_help=True,
)
config_app = typer.Typer(help="Manage LogLens config (API keys, provider, model).")
app.add_typer(config_app, name="config")

console = Console()
SESSIONS_DIR = Path(".loglens/sessions")

# ── Helpers ──────────────────────────────────────────────────────────────────

def _get_session_dir(session: str) -> Path:
    return SESSIONS_DIR / session


def _require_session(session: str) -> Path:
    session_dir = _get_session_dir(session)
    if not session_dir.exists():
        console.print(f"[red]Error:[/red] Session '[bold]{session}[/bold]' not found.")
        console.print("Run [cyan]loglens ingest <file>[/cyan] first.")
        raise typer.Exit(1)
    return session_dir


def _build_agent() -> LogAgent:
    """Build a LogAgent using config or env var for the API key."""
    provider = cfg.get_active_provider()
    api_key = cfg.get_api_key(provider)
    model = cfg.get_model(provider)

    if not api_key:
        console.print(f"[red]Error:[/red] No API key found for provider '[bold]{provider}[/bold]'.")
        console.print(
            f"Set it with: [cyan]loglens config set-key {provider} <your-key>[/cyan]\n"
            f"Or export the env var: [cyan]export {cfg.PROVIDERS[provider]['env']}=<key>[/cyan]"
        )
        raise typer.Exit(1)

    return LogAgent(api_key=api_key, model=model)


# ── ingest ───────────────────────────────────────────────────────────────────

@app.command()
def ingest(
    log_file: Path = typer.Argument(..., help="Path to the log file"),
    session_name: Optional[str] = typer.Option(None, "--name", "-n", help="Session name (defaults to filename stem)"),
    force: bool = typer.Option(False, "--force", "-f", help="Force re-ingest even if session exists"),
) -> None:
    """Parse a log file and cache schema, ID map, and records for querying."""
    if not log_file.exists():
        console.print(f"[red]Error:[/red] File not found: {log_file}")
        raise typer.Exit(1)

    name = session_name or log_file.stem
    session_dir = _get_session_dir(name)

    if session_dir.exists() and not force:
        console.print(f"[yellow]Session '[bold]{name}[/bold]' already exists.[/yellow] Use --force to re-ingest.")
        return

    session_dir.mkdir(parents=True, exist_ok=True)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        # 1. Parse
        task = progress.add_task("Parsing log records...", total=None)
        parser = LogParser()
        records = []
        try:
            for record in parser.parse_file_stream(log_file):
                records.append(record)
        except Exception as e:
            console.print(f"[red]Parse error:[/red] {e}")
            raise typer.Exit(1)
        progress.update(task, description=f"[green]✓[/green] Parsed {len(records):,} records")

        # 2. Schema
        task = progress.add_task("Discovering schema...", total=None)
        discovery = SchemaDiscovery()
        for r in records:
            discovery.process_record(r)
        discovery.save_schema(session_dir / "schema.json")
        fields = len(discovery.field_metadata)
        progress.update(task, description=f"[green]✓[/green] Schema: {fields} fields discovered")

        # 3. ID Map
        task = progress.add_task("Building ID map...", total=None)
        mapper = IDMapper()
        mapper.process_records(records)
        mapper.save(session_dir / "id_map.json")
        unique_ids = len(mapper.id_map)
        progress.update(task, description=f"[green]✓[/green] ID map: {unique_ids:,} unique IDs")

        # 4. Save records
        task = progress.add_task("Saving session...", total=None)
        with open(session_dir / "records.json", "w") as f:
            json.dump(records, f)
        metadata = {
            "source": str(log_file.absolute()),
            "record_count": len(records),
            "ingested_at": datetime.utcnow().isoformat() + "Z",
        }
        with open(session_dir / "metadata.json", "w") as f:
            json.dump(metadata, f, indent=2)
        progress.update(task, description="[green]✓[/green] Session saved")

    console.print(f"\n[bold green]Ready.[/bold green] Session '[bold]{name}[/bold]' — {len(records):,} records.")
    console.print(f"[dim]Run: loglens chat {name}[/dim]")


# ── query ────────────────────────────────────────────────────────────────────

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

    # Load existing history for context
    hist = memory.trim(memory.load(session_dir), cfg.load().get("history_window", 20))

    console.print(f"\n[bold blue]LogLens[/bold blue] [dim]·[/dim] [dim]{session}[/dim]")
    console.print(f"[bold]Q:[/bold] {question}\n")

    with console.status("[bold green]Analyzing...[/bold green]"):
        try:
            result = agent.query(session_dir, question, history=hist)
        except Exception as e:
            console.print(f"[red]Error:[/red] {e}")
            raise typer.Exit(1)

    console.print(Panel(
        Markdown(result["answer"]),
        title="[bold green]Copilot[/bold green]",
        border_style="green",
    ))

    if show_jq:
        console.print(f"\n[dim]JQ:[/dim] [cyan]{result['jq_program']}[/cyan]")

    console.print(f"\n[dim]{result['attempts']} retrieval pass(es) · model: {cfg.get_model()}[/dim]")

    if save_history:
        memory.append_turn(session_dir, question, result["answer"])


# ── chat ─────────────────────────────────────────────────────────────────────

@app.command()
def chat(
    session: str = typer.Argument(..., help="Session name"),
    show_jq: bool = typer.Option(False, "--show-jq", help="Print the generated JQ program after each answer"),
) -> None:
    """Start an interactive chat session with memory across questions."""
    session_dir = _require_session(session)
    agent = _build_agent()
    window = cfg.load().get("history_window", 20)

    # Load persisted history
    history = memory.load(session_dir)
    hist_summary = memory.summary(session_dir)

    console.print(f"\n[bold blue]LogLens Chat[/bold blue] [dim]·[/dim] [dim]{session}[/dim]")
    if hist_summary["turns"] > 0:
        console.print(f"[dim]Resuming — {hist_summary['turns']} previous turn(s) in memory.[/dim]")
    console.print("[dim]Type 'exit' or Ctrl+C to quit.[/dim]\n")

    while True:
        try:
            question = typer.prompt("You")
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Goodbye![/dim]")
            break

        if not question.strip():
            continue
        if question.lower() in ("exit", "quit"):
            console.print("[dim]Goodbye![/dim]")
            break

        windowed_history = memory.trim(history, window)

        with console.status("[bold green]Analyzing...[/bold green]"):
            try:
                result = agent.query(session_dir, question, history=windowed_history)
            except Exception as e:
                console.print(f"[red]Error:[/red] {e}")
                continue

        console.print(f"\n[bold green]Copilot:[/bold green]")
        console.print(Markdown(result["answer"]))

        if show_jq:
            console.print(f"\n[dim]JQ:[/dim] [cyan]{result['jq_program']}[/cyan]")

        console.print(f"[dim]{result['attempts']} pass(es)[/dim]")
        console.print("─" * 60 + "\n")

        # Persist this turn
        history.append({"role": "user", "content": question})
        history.append({"role": "assistant", "content": result["answer"]})
        memory.save(session_dir, history)


# ── sessions ─────────────────────────────────────────────────────────────────

@app.command()
def sessions() -> None:
    """List all cached log sessions."""
    if not SESSIONS_DIR.exists() or not any(SESSIONS_DIR.iterdir()):
        console.print("[yellow]No sessions found.[/yellow] Run [cyan]loglens ingest <file>[/cyan] to create one.")
        return

    table = Table(title="LogLens Sessions", header_style="bold blue", border_style="dim")
    table.add_column("Session", style="bold")
    table.add_column("Records", justify="right")
    table.add_column("Ingested At")
    table.add_column("Source File", style="dim")
    table.add_column("History", justify="right")

    for session_dir in sorted(SESSIONS_DIR.iterdir()):
        if not session_dir.is_dir():
            continue
        meta_path = session_dir / "metadata.json"
        if not meta_path.exists():
            continue
        with open(meta_path) as f:
            meta = json.load(f)

        hist = memory.summary(session_dir)
        table.add_row(
            session_dir.name,
            f"{meta.get('record_count', '?'):,}",
            meta.get("ingested_at", "?")[:19].replace("T", " "),
            Path(meta.get("source", "?")).name,
            f"{hist['turns']} turns",
        )

    console.print(table)


# ── refresh ──────────────────────────────────────────────────────────────────

@app.command()
def refresh(
    session: str = typer.Argument(..., help="Session name to re-ingest"),
    keep_history: bool = typer.Option(True, "--keep-history/--clear-history", help="Keep conversation history"),
) -> None:
    """Force re-parse and re-cache a session."""
    session_dir = _require_session(session)

    # Read the original source file path
    meta_path = session_dir / "metadata.json"
    if not meta_path.exists():
        console.print("[red]Error:[/red] Session metadata missing. Cannot determine source file.")
        raise typer.Exit(1)

    with open(meta_path) as f:
        meta = json.load(f)
    source = Path(meta.get("source", ""))

    if not source.exists():
        console.print(f"[red]Error:[/red] Original log file not found: {source}")
        raise typer.Exit(1)

    # Optionally preserve history before wiping
    saved_history = memory.load(session_dir) if keep_history else []

    # Re-run ingest with force
    import shutil
    shutil.rmtree(session_dir)
    session_dir.mkdir(parents=True, exist_ok=True)

    # Restore history if needed
    if keep_history and saved_history:
        memory.save(session_dir, saved_history)

    # Delegate to ingest logic
    ctx = typer.Context(app)
    ingest.callback(log_file=source, session_name=session, force=True)  # type: ignore


# ── clear-history ─────────────────────────────────────────────────────────────

@app.command(name="clear-history")
def clear_history(
    session: str = typer.Argument(..., help="Session name"),
) -> None:
    """Wipe conversation history for a session (keeps schema and records)."""
    session_dir = _require_session(session)
    hist = memory.summary(session_dir)
    if hist["turns"] == 0:
        console.print(f"[yellow]No history to clear for session '[bold]{session}[/bold]'.[/yellow]")
        return
    memory.clear(session_dir)
    console.print(f"[green]✓[/green] Cleared {hist['turns']} turn(s) from '[bold]{session}[/bold]'.")


# ── config subcommands ────────────────────────────────────────────────────────

@config_app.command(name="show")
def config_show() -> None:
    """Print current config (API keys masked)."""
    current = cfg.masked(cfg.load())
    console.print_json(json.dumps(current, indent=2))
    console.print(f"\n[dim]Config file: {cfg.CONFIG_PATH}[/dim]")


@config_app.command(name="set-key")
def config_set_key(
    provider: str = typer.Argument(..., help=f"Provider name: {', '.join(cfg.PROVIDERS)}"),
    key: str = typer.Argument(..., help="Your API key"),
) -> None:
    """Store an API key for a provider."""
    try:
        cfg.set_key(provider, key)
        console.print(f"[green]✓[/green] API key saved for [bold]{provider}[/bold].")
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@config_app.command(name="set-provider")
def config_set_provider(
    provider: str = typer.Argument(..., help=f"Provider name: {', '.join(cfg.PROVIDERS)}"),
) -> None:
    """Switch the active LLM provider."""
    try:
        cfg.set_provider(provider)
        model = cfg.PROVIDERS[provider]["default_model"]
        console.print(f"[green]✓[/green] Active provider: [bold]{provider}[/bold] (model: {model})")
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@config_app.command(name="set-model")
def config_set_model(
    model: str = typer.Argument(..., help="Model name (e.g. gpt-4o-mini, claude-haiku-4-5)"),
) -> None:
    """Override the model for the active provider."""
    cfg.set_model(model)
    provider = cfg.get_active_provider()
    console.print(f"[green]✓[/green] Model set to [bold]{model}[/bold] for [bold]{provider}[/bold].")


if __name__ == "__main__":
    app()
