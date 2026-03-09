# # agents/v0.1.0/config.py
# """
# Central configuration for v0.1.0.
# All magic numbers and model choices live here.
# """

# import os
# from pathlib import Path

# # ── Model ────────────────────────────────────────────────────────────────────
# MODEL = "claude-sonnet-4-20250514"
# MAX_TOKENS = 8192
# MAX_REACT_STEPS = 20          # hard cap on ReAct iterations per run

# # ── Paths ─────────────────────────────────────────────────────────────────────
# ROOT_DIR        = Path(__file__).resolve().parents[2]   # repo root
# AGENTS_DIR      = ROOT_DIR / "agents"
# CURRENT_VERSION = "v0.1.0"
# CURRENT_DIR     = AGENTS_DIR / CURRENT_VERSION

# # ── Safety whitelist ──────────────────────────────────────────────────────────
# # The agent may only read/write inside this directory tree.
# # Expanding this requires explicit user approval in the conversation thread.
# ALLOWED_WRITE_ROOT = ROOT_DIR          # tightened to AGENTS_DIR in v0.2+
# ALLOWED_READ_ROOT  = ROOT_DIR

# # ── Misc ──────────────────────────────────────────────────────────────────────
# ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")


# agents/v0_1_0/config.py
# import os
# from pathlib import Path

# # ── Model ─────────────────────────────────────────────────────────────────────
# MODEL = "gemini-2.0-flash"
# MAX_TOKENS = 8192
# MAX_REACT_STEPS = 20

# # ── Paths ─────────────────────────────────────────────────────────────────────
# ROOT_DIR        = Path(__file__).resolve().parents[2]
# AGENTS_DIR      = ROOT_DIR / "agents"
# CURRENT_VERSION = "v0.1.0"
# CURRENT_DIR     = AGENTS_DIR / CURRENT_VERSION

# # ── Safety whitelist ──────────────────────────────────────────────────────────
# ALLOWED_WRITE_ROOT = ROOT_DIR
# ALLOWED_READ_ROOT  = ROOT_DIR

# # ── API Key ───────────────────────────────────────────────────────────────────
# GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")


# agents/v0_1_0/config.py
import os
from pathlib import Path

# ── Model ─────────────────────────────────────────────────────────────────────
MODEL = "llama-3.3-70b-versatile"   # best free model on Groq
MAX_TOKENS = 8192
MAX_REACT_STEPS = 20

# ── Paths ─────────────────────────────────────────────────────────────────────
ROOT_DIR        = Path(__file__).resolve().parents[2]
AGENTS_DIR      = ROOT_DIR / "agents"
CURRENT_VERSION = "v0.1.0"
CURRENT_DIR     = AGENTS_DIR / CURRENT_VERSION

# ── Safety whitelist ──────────────────────────────────────────────────────────
ALLOWED_WRITE_ROOT = ROOT_DIR
ALLOWED_READ_ROOT  = ROOT_DIR

# ── API Key ───────────────────────────────────────────────────────────────────
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")