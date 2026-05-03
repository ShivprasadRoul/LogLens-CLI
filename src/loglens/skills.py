"""Skills system — pluggable domain knowledge for log analysis.

Skills are TOML files that contribute:
  [detection]  — keyword signals for auto-detection
  [prompts]    — domain_context + jq_hints injected into LLM calls

Loading priority (highest first):
  1. ~/.loglens/skills/   — user-installed custom skills
  2. <repo>/skills/        — built-in skills shipped with LogLens
  3. generic               — always-available fallback
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# Try tomllib (Python 3.11+) then tomli (backport)
if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomllib          # type: ignore[no-redef]
    except ImportError:
        try:
            import tomli as tomllib  # type: ignore[no-redef]
        except ImportError:
            tomllib = None      # type: ignore[assignment]

from loglens import config as cfg

# ── Paths ─────────────────────────────────────────────────────────────────────

# Built-in skills shipped in the repo
_BUILTIN_SKILLS_DIR = Path(__file__).parent.parent.parent / "skills"
# User-installed custom skills
_USER_SKILLS_DIR = Path.home() / ".loglens" / "skills"

# Skills that should never be auto-selected (only used as fallback)
_FALLBACK_SKILLS = {"generic"}

# ── Skill data class ──────────────────────────────────────────────────────────

class Skill:
    """Represents a single loaded skill."""

    def __init__(self, data: Dict[str, Any], source_path: Path):
        meta = data.get("meta", {})
        detection = data.get("detection", {})
        prompts = data.get("prompts", {})

        self.name:           str        = meta.get("name", source_path.stem)
        self.description:    str        = meta.get("description", "")
        self.version:        str        = meta.get("version", "1.0.0")
        self.author:         str        = meta.get("author", "unknown")
        self.signals:        List[str]  = detection.get("signals", [])
        self.domain_context: str        = prompts.get("domain_context", "")
        self.jq_hints:       str        = prompts.get("jq_hints", "")
        self.source_path:    Path       = source_path
        self.is_user:        bool       = _USER_SKILLS_DIR in source_path.parents

    def __repr__(self) -> str:
        tag = "user" if self.is_user else "built-in"
        return f"<Skill {self.name!r} [{tag}] signals={len(self.signals)}>"


# ── Registry ──────────────────────────────────────────────────────────────────

class SkillRegistry:
    """Loads, stores, and queries all available skills."""

    def __init__(self):
        self._skills: Dict[str, Skill] = {}
        self._load_all()

    def _load_all(self) -> None:
        """Load built-ins first, then user skills (user overrides built-ins by name)."""
        for toml_path in sorted(_BUILTIN_SKILLS_DIR.glob("*.toml")):
            skill = _load_toml(toml_path)
            if skill:
                self._skills[skill.name] = skill

        if _USER_SKILLS_DIR.exists():
            for toml_path in sorted(_USER_SKILLS_DIR.glob("*.toml")):
                skill = _load_toml(toml_path)
                if skill:
                    self._skills[skill.name] = skill  # overrides built-in with same name

    def all(self) -> List[Skill]:
        return list(self._skills.values())

    def get(self, name: str) -> Optional[Skill]:
        return self._skills.get(name)

    def detect(self, schema_text: str, sample_values: str = "") -> Skill:
        """Auto-detect the best matching skill from schema fields + sample values.

        Scoring: count how many of the skill's signals appear in the combined text.
        Generic skill is excluded from auto-detection (used only as fallback).
        Returns the generic skill if nothing scores > 0.
        """
        combined = (schema_text + " " + sample_values).lower()
        best_skill: Optional[Skill] = None
        best_score = 0

        for skill in self._skills.values():
            if skill.name in _FALLBACK_SKILLS:
                continue
            score = sum(1 for sig in skill.signals if sig.lower() in combined)
            if score > best_score:
                best_score = score
                best_skill = skill

        if best_skill is None or best_score == 0:
            return self._skills.get("generic") or _fallback_generic()

        return best_skill

    def install(self, source: Path) -> Skill:
        """Install a user skill from a TOML file into ~/.loglens/skills/."""
        skill = _load_toml(source)
        if not skill:
            raise ValueError(f"Failed to parse skill file: {source}")

        _USER_SKILLS_DIR.mkdir(parents=True, exist_ok=True)
        dest = _USER_SKILLS_DIR / source.name
        dest.write_bytes(source.read_bytes())

        skill.source_path = dest
        skill.is_user = True
        self._skills[skill.name] = skill
        return skill

    def remove(self, name: str) -> None:
        """Remove a user-installed skill."""
        skill = self._skills.get(name)
        if not skill:
            raise KeyError(f"Skill '{name}' not found.")
        if not skill.is_user:
            raise PermissionError(f"Cannot remove built-in skill '{name}'.")
        skill.source_path.unlink()
        del self._skills[name]

    def reload(self) -> None:
        self._skills.clear()
        self._load_all()


# ── TOML parsing ──────────────────────────────────────────────────────────────

def _load_toml(path: Path) -> Optional[Skill]:
    """Parse a TOML file into a Skill object."""
    if tomllib is None:
        # Python 3.9/3.10 without tomli installed — graceful degradation
        return None
    try:
        with open(path, "rb") as f:
            data = tomllib.load(f)
        return Skill(data, path)
    except Exception:
        return None


def _fallback_generic() -> Skill:
    """Return a minimal in-memory generic skill if TOML parsing fails."""
    class _FallbackSkill:
        name = "generic"
        description = "Generic fallback skill"
        version = "1.0.0"
        author = "LogLens"
        signals: List[str] = []
        domain_context = "Analyze the log data carefully and provide clear, specific insights."
        jq_hints = ""
        source_path = Path("(built-in)")
        is_user = False
    return _FallbackSkill()  # type: ignore[return-value]


# ── Module-level singleton ────────────────────────────────────────────────────

_registry: Optional[SkillRegistry] = None


def get_registry() -> SkillRegistry:
    """Return the global SkillRegistry, initializing it on first call."""
    global _registry
    if _registry is None:
        _registry = SkillRegistry()
    return _registry


def detect_skill(schema_text: str, sample_values: str = "") -> Skill:
    """Detect the best skill for the given schema. Module-level convenience."""
    return get_registry().detect(schema_text, sample_values)
