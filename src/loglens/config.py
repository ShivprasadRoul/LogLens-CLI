"""Config management for LogLens — stored at ~/.loglens/config.json."""

import json
import os
import stat
from pathlib import Path
from typing import Any, Dict, Optional

CONFIG_DIR = Path.home() / ".loglens"
CONFIG_PATH = CONFIG_DIR / "config.json"

PROVIDERS = {
    "openai":    {"env": "OPENAI_API_KEY",    "default_model": "gpt-4o"},
    "anthropic": {"env": "ANTHROPIC_API_KEY", "default_model": "claude-opus-4-5"},
    "groq":      {"env": "GROQ_API_KEY",      "default_model": "llama-3.3-70b-versatile"},
    "gemini":    {"env": "GEMINI_API_KEY",    "default_model": "gemini-1.5-pro"},
}

# Model catalog — used by the interactive picker
MODELS = {
    "openai": {
        "Core LLMs": ["gpt-5.3", "gpt-5", "gpt-4o", "gpt-4o-mini"],
        "Reasoning": ["o3", "o1"],
        "Fast & Cheap": ["gpt-4o-mini"],
    },
    "anthropic": {
        "Core LLMs": ["claude-opus-4-5", "claude-sonnet-4-5", "claude-haiku-3-5"],
        "Fast & Cheap": ["claude-haiku-3-5"],
    },
    "groq": {
        "Core LLMs": ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "mixtral-8x7b-32768"],
        "Fast & Cheap": ["llama-3.1-8b-instant"],
    },
    "gemini": {
        "Core LLMs": ["gemini-2.5-pro", "gemini-2.5-flash", "gemini-1.5-pro", "gemini-1.5-flash"],
        "Fast & Cheap": ["gemini-2.5-flash", "gemini-1.5-flash"],
    },
}

_DEFAULTS: Dict[str, Any] = {
    "llm_provider": "openai",
    "model": "gpt-4o",
    "api_keys": {},
    "max_retries": 3,
    "max_jq_bytes": 200_000,
    "history_window": 20,
}


def _ensure_config_dir() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def load() -> Dict[str, Any]:
    """Load config from disk, returning defaults for missing keys."""
    _ensure_config_dir()
    if not CONFIG_PATH.exists():
        return dict(_DEFAULTS)
    try:
        with open(CONFIG_PATH, "r") as f:
            data = json.load(f)
        # Fill in any missing keys with defaults
        for k, v in _DEFAULTS.items():
            data.setdefault(k, v)
        return data
    except (json.JSONDecodeError, IOError):
        return dict(_DEFAULTS)


def save(cfg: Dict[str, Any]) -> None:
    """Write config to disk with restricted permissions (600)."""
    _ensure_config_dir()
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)
    # Restrict to owner read/write only (protects API keys)
    CONFIG_PATH.chmod(stat.S_IRUSR | stat.S_IWUSR)


def get_api_key(provider: Optional[str] = None) -> Optional[str]:
    """Return the API key for the given provider.
    
    Priority order:
      1. Config file (~/.loglens/config.json)
      2. Environment variable
    """
    cfg = load()
    provider = provider or cfg.get("llm_provider", "openai")
    
    # 1. Config file
    key = cfg.get("api_keys", {}).get(provider)
    if key:
        return key
    
    # 2. Environment variable fallback
    env_var = PROVIDERS.get(provider, {}).get("env", "")
    return os.getenv(env_var) or None


def get_model(provider: Optional[str] = None) -> str:
    """Return the configured model for the active (or given) provider."""
    cfg = load()
    return cfg.get("model", _DEFAULTS["model"])


def get_active_provider() -> str:
    return load().get("llm_provider", "openai")


def set_key(provider: str, key: str) -> None:
    """Store an API key for a provider."""
    if provider not in PROVIDERS:
        raise ValueError(f"Unknown provider '{provider}'. Choose from: {', '.join(PROVIDERS)}")
    cfg = load()
    cfg.setdefault("api_keys", {})[provider] = key
    save(cfg)


def set_provider(provider: str) -> None:
    """Switch the active LLM provider and reset model to provider default."""
    if provider not in PROVIDERS:
        raise ValueError(f"Unknown provider '{provider}'. Choose from: {', '.join(PROVIDERS)}")
    cfg = load()
    cfg["llm_provider"] = provider
    cfg["model"] = PROVIDERS[provider]["default_model"]
    save(cfg)


def set_model(model: str) -> None:
    """Set the model for the currently active provider."""
    cfg = load()
    cfg["model"] = model
    save(cfg)


def masked(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Return a copy of config with API keys masked for display."""
    import copy
    display = copy.deepcopy(cfg)
    for provider, key in display.get("api_keys", {}).items():
        if key:
            display["api_keys"][provider] = key[:8] + "..." + key[-4:]
    return display
