# agents/v0_3_0/tools.py
"""
Tools for v0.3.0 — adds spawn_agent tool on top of v0.2.0 tools.
"""

import subprocess
import shlex
from pathlib import Path
from typing import Any

from .config import (
    ALLOWED_READ_ROOT, ALLOWED_WRITE_ROOT,
    SHELL_WHITELIST, MAX_SPAWN_DEPTH,
)
from .memory import memory_store as _mem_store, memory_search as _mem_search


def _safe_read(raw: str) -> Path:
    p = Path(raw).resolve()
    if not str(p).startswith(str(ALLOWED_READ_ROOT.resolve())):
        raise PermissionError(f"Read blocked: {p}")
    return p

def _safe_write(raw: str) -> Path:
    p = Path(raw).resolve()
    if not str(p).startswith(str(ALLOWED_WRITE_ROOT.resolve())):
        raise PermissionError(f"Write blocked: {p}")
    return p


def tool_read_file(path: str) -> str:
    try:
        p = _safe_read(path)
        if not p.exists():  return f"ERROR: Not found: {path}"
        if not p.is_file(): return f"ERROR: Not a file: {path}"
        lines = p.read_text(encoding="utf-8").splitlines()
        return f"FILE: {p}\nLINES: {len(lines)}\n\n" + "\n".join(
            f"{i+1:4d} | {l}" for i, l in enumerate(lines)
        )
    except PermissionError as e: return f"PERMISSION ERROR: {e}"
    except Exception as e:       return f"ERROR: {e}"


def tool_write_file(path: str, content: str) -> str:
    try:
        p = _safe_write(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return f"OK: Written {len(content)} chars to {p}"
    except PermissionError as e: return f"PERMISSION ERROR: {e}"
    except Exception as e:       return f"ERROR: {e}"


def tool_list_dir(path: str = ".") -> str:
    try:
        p = _safe_read(path)
        if not p.exists():  return f"ERROR: Not found: {path}"
        if not p.is_dir():  return f"ERROR: Not a directory: {path}"
        lines = [f"Directory: {p}"]
        def _walk(d, depth=0):
            if depth > 3: return
            try:
                for entry in sorted(d.iterdir(), key=lambda x: (x.is_file(), x.name)):
                    if entry.name.startswith("."): continue
                    lines.append("  " * depth + ("📄 " if entry.is_file() else "📁 ") + entry.name)
                    if entry.is_dir(): _walk(entry, depth+1)
            except PermissionError: pass
        _walk(p)
        return "\n".join(lines)
    except Exception as e: return f"ERROR: {e}"


def tool_self_critique(source_summary: str = "") -> str:
    return f"""## Self-Critique (v0.3.0)

### 1. Orchestration Quality
- Does parent→child communication work cleanly?
- Is task decomposition accurate?
- Issues: ___

### 2. Tool Design
- Are tools minimal and composable?
- Issues: ___

### 3. Memory & Context
- Is sliding window working?
- Issues: ___

### 4. Safety
- Are spawn depth limits enforced? (MAX={MAX_SPAWN_DEPTH})
- Issues: ___

### 5. Code Quality
- Issues: ___

### 6. Proposed v0.4.0 improvements
- ___

Source summary: {source_summary or '(read files first)'}""".strip()


def tool_memory_store(key: str, value: str, tags: str = "") -> str:
    if not key:   return "ERROR: key required"
    if not value: return "ERROR: value required"
    return _mem_store(key, value, tags)


def tool_memory_search(query: str) -> str:
    if not query: return "ERROR: query required"
    return _mem_search(query)


def tool_shell_run(command: str) -> str:
    """[SAFETY] Whitelisted shell commands only."""
    if not command: return "ERROR: command required"
    try:
        tokens = shlex.split(command)
    except ValueError as e:
        return f"ERROR parsing command: {e}"
    if not tokens or tokens[0] not in SHELL_WHITELIST:
        return (
            f"PERMISSION ERROR: '{tokens[0] if tokens else ''}' not whitelisted.\n"
            f"Allowed: {', '.join(sorted(SHELL_WHITELIST))}"
        )
    try:
        r = subprocess.run(tokens, capture_output=True, text=True, timeout=30,
                          cwd=str(ALLOWED_READ_ROOT))
        out = (r.stdout + r.stderr)[:4000]
        return out or "(no output)"
    except subprocess.TimeoutExpired: return "ERROR: Timed out"
    except Exception as e: return f"ERROR: {e}"


def tool_spawn_agent(task: str, context: str = "") -> str:
    """
    [ORCHESTRATION] Spawn a ParentAgent to solve a complex subtask.
    Use this when a task has clearly separable parallel components.
    [SAFETY] Depth is enforced by config.MAX_SPAWN_DEPTH.
    """
    if not task:
        return "ERROR: task required"
    try:
        # Import here to avoid circular imports
        from .orchestrator import ParentAgent
        status_lines = []
        def collect_status(msg):
            if isinstance(msg, dict):
                status_lines.append(str(msg.get("content", msg)))
            else:
                status_lines.append(str(msg))

        agent = ParentAgent(
            agent_id  = "spawned",
            depth     = 1,           # spawned agents start at depth 1
            on_status = collect_status,
            verbose   = False,
        )
        result = agent.run(task)
        return f"SPAWN COMPLETE\n\nSynthesis:\n{result['synthesis']}\n\nStatus log:\n" + "\n".join(status_lines[-10:])
    except Exception as e:
        return f"ERROR spawning agent: {e}"


# ── Registry ──────────────────────────────────────────────────────────────────

TOOL_DEFINITIONS = {
    "read_file":     {"description": "Read a text file.", "params": {"path": "File path"}},
    "write_file":    {"description": "Write content to a file.", "params": {"path": "Destination", "content": "Text to write"}},
    "list_dir":      {"description": "List directory tree.", "params": {"path": "Directory (optional)"}},
    "self_critique": {"description": "Generate a self-critique scaffold.", "params": {"source_summary": "Optional summary"}},
    "memory_store":  {"description": "Store a fact in persistent SQLite memory.", "params": {"key": "Unique key", "value": "Content", "tags": "Optional tags"}},
    "memory_search": {"description": "Search persistent memory.", "params": {"query": "Search term"}},
    "shell_run":     {"description": f"[WHITELISTED] Run shell command. Allowed: {', '.join(sorted(SHELL_WHITELIST))}", "params": {"command": "Shell command"}},
    "spawn_agent":   {"description": "[ORCHESTRATION] Spawn a child agent team to solve a complex multi-part task in parallel.", "params": {"task": "The complex task to delegate", "context": "Optional context"}},
}


def dispatch(name: str, params: dict[str, Any]) -> str:
    if name == "read_file":     return tool_read_file(params.get("path", ""))
    if name == "write_file":    return tool_write_file(params.get("path", ""), params.get("content", ""))
    if name == "list_dir":      return tool_list_dir(params.get("path", "."))
    if name == "self_critique": return tool_self_critique(params.get("source_summary", ""))
    if name == "memory_store":  return tool_memory_store(params.get("key",""), params.get("value",""), params.get("tags",""))
    if name == "memory_search": return tool_memory_search(params.get("query", ""))
    if name == "shell_run":     return tool_shell_run(params.get("command", ""))
    if name == "spawn_agent":   return tool_spawn_agent(params.get("task",""), params.get("context",""))
    return f"ERROR: Unknown tool '{name}'"


def tool_definitions_as_text() -> str:
    lines = ["## Available Tools\n"]
    for name, meta in TOOL_DEFINITIONS.items():
        lines.append(f"### {name}")
        lines.append(f"Description: {meta['description']}")
        lines.append("Parameters:")
        for p, d in meta["params"].items():
            lines.append(f"  - {p}: {d}")
        lines.append("")
    return "\n".join(lines)