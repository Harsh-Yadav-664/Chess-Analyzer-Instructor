"""
config.py - Central configuration for AI Chess Instructor
Handles Stockfish path resolution, profile storage, and environment settings.
"""

import os
import shutil
from pathlib import Path
from typing import Optional


# Profile storage - user's home directory
PROFILE_DIR = Path.home() / ".chess_instructor"
PROFILE_FILE = PROFILE_DIR / "profile.json"
WEB_PROFILE_FILE = PROFILE_DIR / "web_profile.json"
SESSION_DIR = PROFILE_DIR / "sessions"

# Ensure directories exist when needed
def ensure_profile_dir():
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    SESSION_DIR.mkdir(parents=True, exist_ok=True)

# Stockfish path resolution
COMMON_STOCKFISH_PATHS = [
    # Environment variable
    os.environ.get("STOCKFISH_PATH"),
    # Which in PATH
    shutil.which("stockfish"),
    # Common Linux locations
    "/usr/bin/stockfish",
    "/usr/local/bin/stockfish",
    "/opt/homebrew/bin/stockfish",
    "/usr/games/stockfish",
    # macOS Homebrew
    "/opt/homebrew/opt/stockfish/bin/stockfish",
    "/usr/local/opt/stockfish/bin/stockfish",
    # Windows common
    r"C:\stockfish\stockfish.exe",
    r"C:\Program Files\stockfish\stockfish.exe",
    # Local project stockfish (if bundled)
    str(Path(__file__).parent / "stockfish"),
    str(Path(__file__).parent / "stockfish.exe"),
    str(Path(__file__).parent / "bin" / "stockfish"),
    # Legacy hardcoded path (for backward compat, last resort)
    r"D:\CODE\PROJECTS\Chess Stockfish\stockfish\stockfish-windows-x86-64-avx2.exe",
]

def get_stockfish_path() -> Optional[str]:
    """Find stockfish binary, checking env var, PATH, and common locations."""
    for path in COMMON_STOCKFISH_PATHS:
        if not path:
            continue
        p = Path(path)
        if p.exists() and p.is_file():
            return str(p)
        # Also try if it's executable in PATH (shutil.which already handles)
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    return None

def get_stockfish_path_or_raise() -> str:
    path = get_stockfish_path()
    if not path:
        raise FileNotFoundError(
            "Stockfish engine not found. Please:\n"
            "1. Install Stockfish: https://stockfishchess.org/download/\n"
            "2. Set STOCKFISH_PATH environment variable, or\n"
            "3. Place stockfish binary in PATH or project root\n"
            f"Checked: {[p for p in COMMON_STOCKFISH_PATHS if p]}"
        )
    return path

# Engine defaults
ENGINE_DEPTH = int(os.environ.get("ENGINE_DEPTH", "12"))
ENGINE_MOVE_TIME = float(os.environ.get("ENGINE_MOVE_TIME", "1.0"))
ENGINE_THREADS = int(os.environ.get("ENGINE_THREADS", "1"))

# Web defaults
WEB_HOST = os.environ.get("WEB_HOST", "0.0.0.0")
WEB_PORT = int(os.environ.get("WEB_PORT", "5000"))
FLASK_SECRET = os.environ.get("FLASK_SECRET", os.urandom(16).hex())

# Difficulty presets are in engine.py, but we expose defaults here
DEFAULT_DIFFICULTY = os.environ.get("DEFAULT_DIFFICULTY", "intermediate")
DEFAULT_COACH_MODE = os.environ.get("DEFAULT_COACH_MODE", "adaptive")

# Feature flags
USE_FAKE_ENGINE_IF_MISSING = os.environ.get("USE_FAKE_ENGINE", "1") == "1"  # for dev/preview without stockfish
