# agents/v0_2_0/config.py
import os
from pathlib import Path

# ── Model ─────────────────────────────────────────────────────────────────────
MODEL            = "llama-3.3-70b-versatile"
MAX_TOKENS       = 8192
MAX_REACT_STEPS  = 20

# ── Context window management ─────────────────────────────────────────────────
# Keep this many most-recent message PAIRS (user+assistant) in the live window.
# Older pairs get summarized and stored as a single summary message.
CONTEXT_WINDOW_PAIRS = 6

# ── Paths ─────────────────────────────────────────────────────────────────────
ROOT_DIR        = Path(__file__).resolve().parents[2]
AGENTS_DIR      = ROOT_DIR / "agents"
CURRENT_VERSION = "v0.2.0"
CURRENT_DIR     = AGENTS_DIR / "v0_2_0"
DATA_DIR        = ROOT_DIR / ".agent_data"      # persistent storage root
DATA_DIR.mkdir(parents=True, exist_ok=True)

MEMORY_DB_PATH  = DATA_DIR / "memory.db"        # SQLite memory
RUNS_LOG_PATH   = DATA_DIR / "runs.jsonl"        # experiment log

# ── Safety whitelist ──────────────────────────────────────────────────────────
ALLOWED_WRITE_ROOT = ROOT_DIR
ALLOWED_READ_ROOT  = ROOT_DIR

# ── Shell tool safety: only these commands are whitelisted ────────────────────
# [SAFETY] Expanding this list requires explicit user approval in conversation.
SHELL_WHITELIST = [
    "ls", "pwd", "echo", "cat", "head", "tail", "wc",
    "grep", "find", "python", "python3", "pip", "git",
]

# ── Retry config ──────────────────────────────────────────────────────────────
RETRY_ATTEMPTS  = 3
RETRY_BASE_WAIT = 5     # seconds, doubles each retry

# ── API Key ───────────────────────────────────────────────────────────────────
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")