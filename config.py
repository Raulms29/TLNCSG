# =============================================================================
# Project-wide configuration
# Settings shared across all modules. Machine-specific values are read from
# a local.env file at the project root
# =============================================================================

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_OLLAMA_HOST = "http://localhost:11434"


def _load_dotenv(path: Path) -> dict[str, str]:
    """Parse simple KEY=VALUE lines from a .env file, ignoring blanks and comments."""
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("'\"")
    return values


def get_ollama_host() -> str:
    """Ollama server URL: OLLAMA_HOST env var > .env file > localhost default."""
    return (
        os.environ.get("OLLAMA_HOST")
        or _load_dotenv(PROJECT_ROOT / ".env").get("OLLAMA_HOST")
        or DEFAULT_OLLAMA_HOST
    )


# Ollama server endpoint
OLLAMA_HOST = get_ollama_host()
