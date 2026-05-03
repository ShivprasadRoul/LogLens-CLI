"""Tests for the log parser module."""

import pytest
from loglens.parser import LogParser


def test_parser_initialization():
    """Test that the parser initializes correctly."""
    parser = LogParser()
    assert parser is not None


def test_supported_formats():
    """Test that supported formats are defined."""
    parser = LogParser()
    assert "json" in parser.supported_formats
    assert "plaintext" in parser.supported_formats
