"""Main CLI entry point using Typer."""

import typer
from pathlib import Path

app = typer.Typer(
    name="loglens",
    help="AI-Powered Log Intelligence CLI - Ask questions about your logs in plain English",
)


@app.command()
def query(
    log_file: Path = typer.Argument(..., help="Path to the log file"),
    question: str = typer.Option(..., "--query", "-q", help="Question to ask about the logs"),
) -> None:
    """Query a log file using natural language."""
    typer.echo(f"Analyzing: {log_file}")
    typer.echo(f"Question: {question}")
    typer.echo("Coming soon...")


@app.command()
def ingest(
    log_file: Path = typer.Argument(..., help="Path to the log file"),
    output_dir: Path = typer.Option(Path(".loglens"), "--output", "-o", help="Output directory for parsed data"),
) -> None:
    """Ingest and parse a log file."""
    typer.echo(f"Ingesting: {log_file}")
    typer.echo(f"Output: {output_dir}")
    typer.echo("Coming soon...")


@app.command()
def chat(
    log_file: Path = typer.Argument(..., help="Path to the log file"),
) -> None:
    """Start an interactive chat session about the logs."""
    typer.echo(f"Starting chat session for: {log_file}")
    typer.echo("Coming soon...")


if __name__ == "__main__":
    app()
