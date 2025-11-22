"""
Configuration settings for Vision LLM Web Agent
"""

import os
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Project paths
PROJECT_ROOT = Path(__file__).parent.parent.parent
ARTIFACTS_DIR = PROJECT_ROOT / "artifacts"
LOGS_DIR = PROJECT_ROOT / "logs"

# Ensure directories exist
ARTIFACTS_DIR.mkdir(exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)

# Current session artifacts directory (set by Agent during initialization)
# This allows tools to access the session-specific directory
_current_session_artifacts_dir: Optional[Path] = None

def set_session_artifacts_dir(session_dir: Path) -> None:
    """Set the current session artifacts directory"""
    global _current_session_artifacts_dir
    _current_session_artifacts_dir = session_dir

def get_session_artifacts_dir() -> Path:
    """Get the current session artifacts directory, fallback to ARTIFACTS_DIR if not set"""
    global _current_session_artifacts_dir
    return _current_session_artifacts_dir if _current_session_artifacts_dir else ARTIFACTS_DIR

# API Configuration
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")

# Agent Configuration
MAX_ROUNDS = int(os.getenv("MAX_ROUNDS", "50"))  # Increased default from 20 to 50
TIMEOUT_PER_ROUND = int(os.getenv("TIMEOUT_PER_ROUND", "30"))

# Browser Configuration
BROWSER_HEADLESS = os.getenv("BROWSER_HEADLESS", "false").lower() == "true"
BROWSER_VIEWPORT_WIDTH = int(os.getenv("BROWSER_VIEWPORT_WIDTH", "1280"))
BROWSER_VIEWPORT_HEIGHT = int(os.getenv("BROWSER_VIEWPORT_HEIGHT", "720"))
BROWSER_LOCALE = os.getenv("BROWSER_LOCALE", "en-US")
