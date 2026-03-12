# agents/v0_3_0/config.py
import os
from pathlib import Path

# ── Model ─────────────────────────────────────────────────────────────────────
MODEL            = "llama-3.3-70b-versatile"
MAX_TOKENS       = 8192
MAX_REACT_STEPS  = 20
TEMPERATURE      = 0.7

# ── Spawning limits [SAFETY] ──────────────────────────────────────────────────
# Expanding these requires explicit user approval.
MAX_CHILDREN_PER_AGENT = 5    # max subtasks a single parent can spawn
MAX_SPAWN_DEPTH        = 2    # max recursion depth (parent → child → grandchild)
MAX_PARALLEL_AGENTS    = 4    # max agents running concurrently

# ── Context ───────────────────────────────────────────────────────────────────
CONTEXT_WINDOW_PAIRS = 6

# ── Paths ─────────────────────────────────────────────────────────────────────
ROOT_DIR        = Path(__file__).resolve().parents[2]
AGENTS_DIR      = ROOT_DIR / "agents"
CURRENT_VERSION = "v0.3.0"
CURRENT_DIR     = AGENTS_DIR / "v0_3_0"
DATA_DIR        = ROOT_DIR / ".agent_data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

MEMORY_DB_PATH  = DATA_DIR / "memory.db"
RUNS_LOG_PATH   = DATA_DIR / "runs.jsonl"

# ── Safety whitelist ──────────────────────────────────────────────────────────
ALLOWED_WRITE_ROOT = ROOT_DIR
ALLOWED_READ_ROOT  = ROOT_DIR

SHELL_WHITELIST = [
    "ls", "pwd", "echo", "cat", "head", "tail", "wc",
    "grep", "find", "python", "python3", "pip", "git",
]

# ── Retry ─────────────────────────────────────────────────────────────────────
RETRY_ATTEMPTS  = 3
RETRY_BASE_WAIT = 5

# ── API ───────────────────────────────────────────────────────────────────────
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")