"""Conversation memory — persists chat history per session."""

import json
from pathlib import Path
from typing import Dict, List, Optional


_HISTORY_FILE = "history.json"


def load(session_dir: Path) -> List[Dict[str, str]]:
    """Load conversation history for a session. Returns [] if none exists."""
    path = session_dir / _HISTORY_FILE
    if not path.exists():
        return []
    try:
        with open(path, "r") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
    except (json.JSONDecodeError, IOError):
        pass
    return []


def save(session_dir: Path, history: List[Dict[str, str]]) -> None:
    """Persist conversation history to disk."""
    path = session_dir / _HISTORY_FILE
    with open(path, "w") as f:
        json.dump(history, f, indent=2)


def append(session_dir: Path, role: str, content: str) -> None:
    """Append a single turn to history and persist immediately."""
    history = load(session_dir)
    history.append({"role": role, "content": content})
    save(session_dir, history)


def append_turn(session_dir: Path, question: str, answer: str) -> None:
    """Append a user+assistant turn and persist."""
    history = load(session_dir)
    history.append({"role": "user", "content": question})
    history.append({"role": "assistant", "content": answer})
    save(session_dir, history)


def trim(history: List[Dict[str, str]], window: int = 20) -> List[Dict[str, str]]:
    """Return the last `window` turns (each turn = 1 user + 1 assistant message).
    
    Keeps the most recent `window * 2` messages to stay within token limits.
    """
    max_msgs = window * 2
    if len(history) > max_msgs:
        return history[-max_msgs:]
    return history


def clear(session_dir: Path) -> None:
    """Wipe the conversation history for a session."""
    path = session_dir / _HISTORY_FILE
    if path.exists():
        path.unlink()


def summary(session_dir: Path) -> Dict[str, int]:
    """Return stats about the stored history."""
    history = load(session_dir)
    turns = len(history) // 2
    return {
        "turns": turns,
        "messages": len(history),
    }
