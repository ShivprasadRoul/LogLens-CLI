import json
from pathlib import Path
import pytest
from loglens import memory

def test_append_and_load(tmp_path):
    session_dir = tmp_path / "session"
    session_dir.mkdir()
    
    memory.append_turn(session_dir, "Hello", "Hi there")
    hist = memory.load(session_dir)
    
    assert len(hist) == 2
    assert hist[0] == {"role": "user", "content": "Hello"}
    assert hist[1] == {"role": "assistant", "content": "Hi there"}

def test_trim_rolling_window():
    history = []
    for i in range(10):
        history.append({"role": "user", "content": f"Q{i}"})
        history.append({"role": "assistant", "content": f"A{i}"})
        
    assert len(history) == 20
    
    # Trim to 4 turns (8 messages)
    trimmed = memory.trim(history, window=4)
    assert len(trimmed) == 8
    assert trimmed[0]["content"] == "Q6"
    assert trimmed[-1]["content"] == "A9"

def test_clear_memory(tmp_path):
    session_dir = tmp_path / "session"
    session_dir.mkdir()
    
    memory.append_turn(session_dir, "Hello", "Hi there")
    assert memory.summary(session_dir)["turns"] == 1
    
    memory.clear(session_dir)
    assert memory.summary(session_dir)["turns"] == 0
    assert len(memory.load(session_dir)) == 0

def test_summary(tmp_path):
    session_dir = tmp_path / "session"
    session_dir.mkdir()
    
    memory.append_turn(session_dir, "Q1", "A1")
    memory.append_turn(session_dir, "Q2", "A2")
    
    summ = memory.summary(session_dir)
    assert summ["turns"] == 2
