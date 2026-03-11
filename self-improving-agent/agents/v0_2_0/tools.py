# agents/v0_2_0/tools.py
"""
Tool definitions and dispatcher for v0.2.0.

New tools vs v0.1.0:
  + memory_store  — persist a key/value fact to SQLite
  + memory_search — search persistent memory
  + shell_run     — run whitelisted shell commands safely

Retained tools:
  read_file, write_file, list_dir, self_critique
"""

import subprocess
import shlex
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from .config import ALLOWED_READ_ROOT, ALLOWED_WRITE_ROOT, SHELL_WHITELIST
from .memory import memory_store as _memory_store, memory_search as _memory_search


# ── Safety helpers ────────────────────────────────────────────────────────────

def _safe_read_path(raw: str) -> Path:
    p = Path(raw).resolve()
    if not str(p).startswith(str(ALLOWED_READ_ROOT.resolve())):
        raise PermissionError(f"Read blocked: '{p}' outside ALLOWED_READ_ROOT.")
    return p


def _safe_write_path(raw: str) -> Path:
    p = Path(raw).resolve()
    if not str(p).startswith(str(ALLOWED_WRITE_ROOT.resolve())):
        raise PermissionError(f"Write blocked: '{p}' outside ALLOWED_WRITE_ROOT.")
    return p


# ── Tool implementations ──────────────────────────────────────────────────────

def tool_read_file(path: str) -> str:
    try:
        p = _safe_read_path(path)
        if not p.exists():  return f"ERROR: File not found: {path}"
        if not p.is_file(): return f"ERROR: Not a file: {path}"
        content = p.read_text(encoding="utf-8")
        lines   = content.splitlines()
        numbered = "\n".join(f"{i+1:4d} | {line}" for i, line in enumerate(lines))
        return f"FILE: {p}\nLINES: {len(lines)}\n\n{numbered}"
    except PermissionError as e: return f"PERMISSION ERROR: {e}"
    except Exception as e:       return f"ERROR: {e}"


def tool_write_file(path: str, content: str) -> str:
    try:
        p = _safe_write_path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return f"OK: Written {len(content)} chars to {p}"
    except PermissionError as e: return f"PERMISSION ERROR: {e}"
    except Exception as e:       return f"ERROR: {e}"


def tool_list_dir(path: str = ".") -> str:
    try:
        p = _safe_read_path(path)
        if not p.exists():  return f"ERROR: Not found: {path}"
        if not p.is_dir():  return f"ERROR: Not a directory: {path}"
        lines = [f"Directory: {p}"]
        def _walk(d: Path, depth: int = 0):
            if depth > 3:
                lines.append("  " * depth + "... (depth limit)")
                return
            try:
                entries = sorted(d.iterdir(), key=lambda x: (x.is_file(), x.name))
            except PermissionError:
                return
            for entry in entries:
                if entry.name.startswith("."): continue
                prefix = "  " * depth + ("📄 " if entry.is_file() else "📁 ")
                lines.append(f"{prefix}{entry.name}")
                if entry.is_dir():
                    _walk(entry, depth + 1)
        _walk(p)
        return "\n".join(lines)
    except PermissionError as e: return f"PERMISSION ERROR: {e}"
    except Exception as e:       return f"ERROR: {e}"


def tool_self_critique(source_summary: str = "") -> str:
    """Structured self-critique scaffold."""
    return f"""
## Self-Critique Report (v0.2.0)

### 1. Reasoning Quality
- Is the ReAct loop tight and well-separated?
- Are Thought/Action/Observation steps clear?
- Issues found: ___

### 2. Tool Design
- Are tools minimal, composable, and safe?
- Do tools return useful error messages?
- Issues found: ___

### 3. Memory & Context
- Is the sliding window working correctly?
- Is SQLite memory being used effectively?
- Issues found: ___

### 4. Safety
- Are path restrictions enforced?
- Is shell whitelist sufficient?
- Issues found: ___

### 5. Code Quality
- Readability, testability, abstractions?
- Issues found: ___

### 6. Missing Capabilities (propose for v0.3.0)
- ___

### 7. Proposed v0.3.0 Architecture Changes
- ___

Source summary: {source_summary or '(none — read files first)'}
""".strip()


def tool_memory_store(key: str, value: str, tags: str = "") -> str:
    """Store a persistent fact in SQLite memory."""
    if not key:  return "ERROR: 'key' param is required."
    if not value: return "ERROR: 'value' param is required."
    return _memory_store(key, value, tags)


def tool_memory_search(query: str) -> str:
    """Search persistent memory by keyword."""
    if not query: return "ERROR: 'query' param is required."
    return _memory_search(query)


def tool_shell_run(command: str) -> str:
    """
    [SAFETY] Run a whitelisted shell command.
    Only commands whose first token appears in SHELL_WHITELIST are permitted.
    """
    if not command:
        return "ERROR: 'command' param is required."
    try:
        tokens = shlex.split(command)
    except ValueError as e:
        return f"ERROR: Could not parse command: {e}"

    base_cmd = tokens[0] if tokens else ""
    if base_cmd not in SHELL_WHITELIST:
        return (
            f"PERMISSION ERROR: '{base_cmd}' is not in the shell whitelist.\n"
            f"Allowed: {', '.join(sorted(SHELL_WHITELIST))}"
        )
    try:
        result = subprocess.run(
            tokens,
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(ALLOWED_READ_ROOT),
        )
        output = result.stdout + result.stderr
        if len(output) > 4000:
            output = output[:4000] + "\n... [TRUNCATED]"
        return output or "(no output)"
    except subprocess.TimeoutExpired:
        return "ERROR: Command timed out after 30s."
    except Exception as e:
        return f"ERROR running command: {e}"


# ── Tool registry ─────────────────────────────────────────────────────────────

TOOL_DEFINITIONS = {
    "read_file": {
        "description": "Read any text file within the allowed path. Returns numbered lines.",
        "params": {"path": "Absolute or relative path to the file."},
    },
    "write_file": {
        "description": "Write text content to a file. Creates parent dirs automatically.",
        "params": {"path": "Destination path.", "content": "Full text to write."},
    },
    "list_dir": {
        "description": "List directory tree (max depth 3).",
        "params": {"path": "Directory path. Optional, defaults to project root."},
    },
    "self_critique": {
        "description": "Returns a structured self-critique template for architectural review.",
        "params": {"source_summary": "Optional brief summary of source files read."},
    },
    "memory_store": {
        "description": "Persist a key/value fact to SQLite memory across runs.",
        "params": {
            "key":   "Unique identifier for this memory.",
            "value": "Content to remember.",
            "tags":  "Optional comma-separated tags for easier retrieval.",
        },
    },
    "memory_search": {
        "description": "Search persistent memory by keyword (matches key, value, or tags).",
        "params": {"query": "Search keyword or phrase."},
    },
    "shell_run": {
        "description": (
            "[SAFETY-WHITELISTED] Run a shell command. "
            f"Only these base commands are allowed: {', '.join(sorted(SHELL_WHITELIST))}."
        ),
        "params": {"command": "Full shell command string to execute."},
    },
}


def dispatch(tool_name: str, params: dict[str, Any]) -> str:
    if tool_name == "read_file":     return tool_read_file(params.get("path", ""))
    if tool_name == "write_file":    return tool_write_file(params.get("path", ""), params.get("content", ""))
    if tool_name == "list_dir":      return tool_list_dir(params.get("path", "."))
    if tool_name == "self_critique": return tool_self_critique(params.get("source_summary", ""))
    if tool_name == "memory_store":  return tool_memory_store(params.get("key", ""), params.get("value", ""), params.get("tags", ""))
    if tool_name == "memory_search": return tool_memory_search(params.get("query", ""))
    if tool_name == "shell_run":     return tool_shell_run(params.get("command", ""))
    return f"ERROR: Unknown tool '{tool_name}'. Available: {list(TOOL_DEFINITIONS.keys())}"


def tool_definitions_as_text() -> str:
    lines = ["## Available Tools\n"]
    for name, meta in TOOL_DEFINITIONS.items():
        lines.append(f"### {name}")
        lines.append(f"Description: {meta['description']}")
        lines.append("Parameters:")
        for param, desc in meta["params"].items():
            lines.append(f"  - {param}: {desc}")
        lines.append("")
    return "\n".join(lines)