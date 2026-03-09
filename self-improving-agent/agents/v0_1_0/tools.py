# agents/v0.1.0/tools.py
"""
Tool definitions and dispatcher for v0.1.0.

Design philosophy:
- Every tool is a plain Python function → easy to test independently.
- The dispatcher maps XML tool names → functions.
- Tools return plain strings (observations) so the agent can reason over them.
- Safety: read/write are path-restricted via config.
"""

import os
import re
import shutil
from pathlib import Path
from typing import Any

from .config import ALLOWED_READ_ROOT, ALLOWED_WRITE_ROOT


# ── Safety helpers ────────────────────────────────────────────────────────────

def _safe_read_path(raw: str) -> Path:
    p = Path(raw).resolve()
    if not str(p).startswith(str(ALLOWED_READ_ROOT.resolve())):
        raise PermissionError(
            f"Read blocked: '{p}' is outside ALLOWED_READ_ROOT '{ALLOWED_READ_ROOT}'."
        )
    return p


def _safe_write_path(raw: str) -> Path:
    p = Path(raw).resolve()
    if not str(p).startswith(str(ALLOWED_WRITE_ROOT.resolve())):
        raise PermissionError(
            f"Write blocked: '{p}' is outside ALLOWED_WRITE_ROOT '{ALLOWED_WRITE_ROOT}'."
        )
    return p


# ── Tool implementations ──────────────────────────────────────────────────────

def tool_read_file(path: str) -> str:
    """Read a text file and return its contents."""
    try:
        p = _safe_read_path(path)
        if not p.exists():
            return f"ERROR: File not found: {path}"
        if not p.is_file():
            return f"ERROR: Path is not a file: {path}"
        content = p.read_text(encoding="utf-8")
        lines = content.splitlines()
        numbered = "\n".join(f"{i+1:4d} | {line}" for i, line in enumerate(lines))
        return f"FILE: {p}\nLINES: {len(lines)}\n\n{numbered}"
    except PermissionError as e:
        return f"PERMISSION ERROR: {e}"
    except Exception as e:
        return f"ERROR reading file: {e}"


def tool_write_file(path: str, content: str) -> str:
    """Write content to a file, creating parent directories as needed."""
    try:
        p = _safe_write_path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return f"OK: Written {len(content)} chars to {p}"
    except PermissionError as e:
        return f"PERMISSION ERROR: {e}"
    except Exception as e:
        return f"ERROR writing file: {e}"


def tool_list_dir(path: str = ".") -> str:
    """List directory contents recursively (max depth 3)."""
    try:
        p = _safe_read_path(path)
        if not p.exists():
            return f"ERROR: Path not found: {path}"
        if not p.is_dir():
            return f"ERROR: Not a directory: {path}"

        lines = []
        def _walk(d: Path, depth: int = 0):
            if depth > 3:
                lines.append("  " * depth + "... (depth limit)")
                return
            try:
                entries = sorted(d.iterdir(), key=lambda x: (x.is_file(), x.name))
            except PermissionError:
                return
            for entry in entries:
                prefix = "  " * depth + ("📄 " if entry.is_file() else "📁 ")
                lines.append(f"{prefix}{entry.name}")
                if entry.is_dir() and not entry.name.startswith("."):
                    _walk(entry, depth + 1)

        lines.append(f"Directory: {p}")
        _walk(p)
        return "\n".join(lines)
    except PermissionError as e:
        return f"PERMISSION ERROR: {e}"
    except Exception as e:
        return f"ERROR listing dir: {e}"


def tool_self_critique(source_summary: str = "") -> str:
    """
    Return a structured self-critique template.
    The agent fills this in as part of its reasoning.
    This tool is a scaffold — it surfaces the right questions.
    """
    template = """
## Self-Critique Report (v0.1.0)

Fill in each section based on your reading of the source code:

### 1. Reasoning Quality
- [ ] Is the ReAct loop properly implemented?
- [ ] Are Thought/Action/Observation steps clearly separated?
- Issues found: ___

### 2. Tool Design
- [ ] Are tools minimal and composable?
- [ ] Do tools return useful error messages?
- Issues found: ___

### 3. Memory & Context
- [ ] Is context window managed efficiently?
- [ ] Is there persistent memory between runs?
- Issues found: ___

### 4. Safety
- [ ] Are path restrictions enforced?
- [ ] Are guardrails clearly marked?
- Issues found: ___

### 5. Code Quality
- [ ] Is the code readable and testable?
- [ ] Are abstractions clean?
- Issues found: ___

### 6. Missing Capabilities (propose for vNEXT)
- ___
- ___

### 7. Proposed vNEXT Architecture Changes
- ___

Source summary provided: {summary}
""".strip().format(summary=source_summary or "(none provided — read files first)")
    return template


# ── Tool registry & dispatcher ────────────────────────────────────────────────

TOOL_DEFINITIONS = {
    "read_file": {
        "description": "Read any text file within the allowed path. Returns numbered lines.",
        "params": {"path": "Absolute or relative path to the file to read."},
    },
    "write_file": {
        "description": "Write text content to a file. Creates parent dirs automatically.",
        "params": {
            "path": "Destination file path.",
            "content": "Full text content to write.",
        },
    },
    "list_dir": {
        "description": "List directory tree (max depth 3). Defaults to project root.",
        "params": {"path": "Directory path to list. Optional, defaults to '.'."},
    },
    "self_critique": {
        "description": (
            "Returns a structured self-critique template to guide the agent's "
            "architectural review. Pass a source_summary if you've already read the files."
        ),
        "params": {"source_summary": "Optional brief summary of source files read so far."},
    },
}


def dispatch(tool_name: str, params: dict[str, Any]) -> str:
    """Route a parsed tool call to the correct function."""
    if tool_name == "read_file":
        return tool_read_file(params.get("path", ""))
    elif tool_name == "write_file":
        return tool_write_file(params.get("path", ""), params.get("content", ""))
    elif tool_name == "list_dir":
        return tool_list_dir(params.get("path", "."))
    elif tool_name == "self_critique":
        return tool_self_critique(params.get("source_summary", ""))
    else:
        return f"ERROR: Unknown tool '{tool_name}'. Available: {list(TOOL_DEFINITIONS.keys())}"


def tool_definitions_as_text() -> str:
    """Render tool definitions into the system prompt."""
    lines = ["## Available Tools\n"]
    for name, meta in TOOL_DEFINITIONS.items():
        lines.append(f"### {name}")
        lines.append(f"Description: {meta['description']}")
        lines.append("Parameters:")
        for param, desc in meta["params"].items():
            lines.append(f"  - {param}: {desc}")
        lines.append("")
    return "\n".join(lines)