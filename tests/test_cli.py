"""Tests for the CLI module."""

import pytest
from loglens.cli import app

from typer.testing import CliRunner

runner = CliRunner()

def test_cli_help():
    """Test that the CLI help command works."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "LogLens" in result.stdout
    assert "AI-Powered Log Intelligence CLI" in result.stdout
    assert "ingest" in result.stdout
    assert "query" in result.stdout
    assert "chat" in result.stdout
