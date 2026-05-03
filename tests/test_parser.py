import json
from pathlib import Path
import pytest
from loglens.parser import LogParser

# ── Sample Logs ───────────────────────────────────────────────────────────────

JSON_LOG = '{"level": "info", "message": "Server started", "port": 8080}'
STANDARD_LOG = 'ERROR:src.main:Connection failed'
PLAINTEXT_LOG = '2026-10-10 13:55:36 [INFO] Database connection established'
MULTILINE_TRACEBACK = """ERROR:src.app:Task failed
Traceback (most recent call last):
  File "main.py", line 10, in <module>
    1 / 0
ZeroDivisionError: division by zero"""

@pytest.fixture
def parser():
    return LogParser()

def _write_temp_log(tmp_path: Path, content: str) -> Path:
    log_file = tmp_path / "test.log"
    log_file.write_text(content)
    return log_file

# ── Tests ─────────────────────────────────────────────────────────────────────

def test_parse_json(parser, tmp_path):
    log_file = _write_temp_log(tmp_path, JSON_LOG)
    records = list(parser.parse_file_stream(log_file))
    
    assert len(records) == 1
    assert records[0]["level"] == "INFO"
    assert records[0]["message"] == "Server started"
    assert records[0]["port"] == 8080

def test_parse_standard_log(parser, tmp_path):
    log_file = _write_temp_log(tmp_path, STANDARD_LOG)
    records = list(parser.parse_file_stream(log_file))
    
    assert len(records) == 1
    assert records[0]["level"] == "ERROR"
    assert records[0]["logger"] == "src.main"
    assert records[0]["message"] == "Connection failed"

def test_parse_plaintext(parser, tmp_path):
    log_file = _write_temp_log(tmp_path, PLAINTEXT_LOG)
    records = list(parser.parse_file_stream(log_file))
    
    assert len(records) == 1
    assert "Database connection established" in records[0]["raw"]
    assert records[0]["level"] == "UNKNOWN"

def test_parse_multiline_traceback(parser, tmp_path):
    log_file = _write_temp_log(tmp_path, MULTILINE_TRACEBACK)
    records = list(parser.parse_file_stream(log_file))
    
    assert len(records) == 1
    assert records[0]["level"] == "ERROR"
    assert records[0]["logger"] == "src.app"
    assert "Task failed" in records[0]["message"]
    assert "ZeroDivisionError" in records[0]["message"]
