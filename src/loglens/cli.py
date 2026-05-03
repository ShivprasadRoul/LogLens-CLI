"""Main CLI entry point using Typer."""

import typer
import json
import os
import shutil
from pathlib import Path
from typing import Optional
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.panel import Panel
from rich.markdown import Markdown

# Local imports
from loglens.parser import LogParser
from loglens.schema import SchemaDiscovery
from loglens.id_map import IDMapper
from loglens.agent import LogAgent

app = typer.Typer(
    name="loglens",
    help="AI-Powered Log Intelligence CLI - Ask questions about your logs in plain English",
)
console = Console()

@app.command()
def ingest(
    log_file: Path = typer.Argument(..., help="Path to the log file"),
    session_name: Optional[str] = typer.Option(None, "--name", "-n", help="Optional name for this session"),
    force: bool = typer.Option(False, "--force", "-f", help="Force re-ingestion if session exists"),
) -> None:
    """Ingest, parse, and index a log file."""
    if not log_file.exists():
        console.print(f"[red]Error:[/red] Log file not found: {log_file}")
        raise typer.Exit(1)

    # Prepare session directory
    name = session_name or log_file.stem
    session_dir = Path(".loglens/sessions") / name
    
    if session_dir.exists() and not force:
        console.print(f"[yellow]Session '{name}' already exists.[/yellow] Use --force to re-ingest.")
        return

    session_dir.mkdir(parents=True, exist_ok=True)
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console
    ) as progress:
        # 1. Parsing
        task1 = progress.add_task(description="Parsing log records...", total=None)
        parser = LogParser()
        records = []
        try:
            for record in parser.parse_file_stream(log_file):
                records.append(record)
            progress.update(task1, description=f"Parsed {len(records)} records.")
        except Exception as e:
            console.print(f"[red]Parsing failed:[/red] {e}")
            raise typer.Exit(1)

        # 2. Schema Discovery
        task2 = progress.add_task(description="Discovering schema...", total=None)
        discovery = SchemaDiscovery()
        for r in records:
            discovery.process_record(r)
        discovery.save_schema(session_dir / "schema.json")
        progress.update(task2, description="Schema discovery complete.")

        # 3. ID Mapping
        task3 = progress.add_task(description="Building ID map...", total=None)
        mapper = IDMapper()
        mapper.process_records(records)
        mapper.save(session_dir / "id_map.json")
        progress.update(task3, description="ID mapping complete.")

        # 4. Save records
        task4 = progress.add_task(description="Saving session data...", total=None)
        with open(session_dir / "records.json", "w") as f:
            json.dump(records, f)
        
        # Save metadata
        metadata = {
            "source": str(log_file.absolute()),
            "record_count": len(records),
            "ingested_at": str(Path(".")), # Placeholder for timestamp or something
        }
        with open(session_dir / "metadata.json", "w") as f:
            json.dump(metadata, f)
            
        progress.update(task4, description="Session saved successfully.")

    console.print(f"\n[green]Success![/green] Session [bold]{name}[/bold] is ready.")
    console.print(f"Location: {session_dir}")

@app.command()
def query(
    session: str = typer.Argument(..., help="Session name"),
    question: str = typer.Option(..., "--query", "-q", help="Question to ask about the logs"),
    show_jq: bool = typer.Option(False, "--show-jq", help="Show the generated JQ program"),
) -> None:
    """Query an ingested log session using natural language."""
    session_dir = Path(".loglens/sessions") / session
    if not session_dir.exists():
        console.print(f"[red]Error:[/red] Session '{session}' not found. Run 'ingest' first.")
        raise typer.Exit(1)

    try:
        agent = LogAgent()
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    console.print(f"\n[bold blue]LogLens Analysis[/bold blue]")
    console.print(f"[dim]Session: {session}[/dim]")
    console.print(f"[bold]Q:[/bold] {question}\n")

    with console.status("[bold green]Thinking...[/bold green]"):
        try:
            result = agent.query(session_dir, question)
        except Exception as e:
            console.print(f"[red]Agent Error:[/red] {e}")
            raise typer.Exit(1)

    # Display Answer
    console.print(Panel(Markdown(result["answer"]), title="[bold green]Copilot Answer[/bold green]", border_style="green"))
    
    if show_jq:
        console.print(f"\n[dim]Generated JQ:[/dim] [cyan]{result['jq_program']}[/cyan]")
    
    console.print(f"\n[dim]({result['attempts']} retrieval pass(es))[/dim]")

@app.command()
def chat(
    session: str = typer.Argument(..., help="Session name"),
) -> None:
    """Start an interactive chat session about the logs."""
    session_dir = Path(".loglens/sessions") / session
    if not session_dir.exists():
        console.print(f"[red]Error:[/red] Session '{session}' not found. Run 'ingest' first.")
        raise typer.Exit(1)

    try:
        agent = LogAgent()
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    console.print(f"\n[bold blue]LogLens Chat Session[/bold blue]")
    console.print(f"[dim]Type 'exit' or 'quit' to end.[/dim]\n")

    history = []
    while True:
        question = typer.prompt("You")
        if question.lower() in ("exit", "quit"):
            break
        
        with console.status("[bold green]Analyzing...[/bold green]"):
            try:
                result = agent.query(session_dir, question, history=history)
                console.print(f"\n[bold green]Copilot:[/bold green]")
                console.print(Markdown(result["answer"]))
                console.print(f"\n[dim]─[/dim]" * 20)
                
                history.append({"role": "user", "content": question})
                history.append({"role": "assistant", "content": result["answer"]})
            except Exception as e:
                console.print(f"[red]Error:[/red] {e}")

if __name__ == "__main__":
    app()
