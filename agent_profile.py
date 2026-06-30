"""Agent profile loader — overlays per-agent settings from profiles/*.env onto os.environ."""

import os
from pathlib import Path

from dotenv import dotenv_values

PROFILES_DIR = Path(__file__).parent / "profiles"


def load_profile(name: str) -> dict:
    """Load profiles/<name>.env and overlay its values onto os.environ."""
    path = PROFILES_DIR / f"{name}.env"
    if not path.exists():
        raise FileNotFoundError(f"No profile '{name}' — expected {path}")
    values = dotenv_values(path)
    for key, val in values.items():
        if val is not None:
            os.environ[key] = val
    os.environ["AGENT_PROFILE"] = name
    return dict(values)


def list_profiles() -> list[str]:
    """Return names of all available profiles."""
    return sorted(p.stem for p in PROFILES_DIR.glob("*.env"))


def active_profile() -> str:
    return os.getenv("AGENT_PROFILE", "trina")
