# server.py — FastAPI backend for the Agent Chat UI
"""
Run with:
    pip install fastapi uvicorn groq
    python server.py
"""

import os
import sys
import json
import asyncio
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

app = FastAPI(title="Self-Improving Agent API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

try:
    from groq import Groq
    GROQ_AVAILABLE = True
except ImportError:
    GROQ_AVAILABLE = False

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
MODEL = "llama-3.3-70b-versatile"

SYSTEM_PROMPT = """You are a helpful AI assistant embedded in a chat UI. You have tools available.

Be conversational, warm, and helpful. You CAN ask the user follow-up questions naturally.
For tasks like writing letters, CVs, applications — ask clarifying questions first, then produce excellent output.

## Tool Calling (only when needed)
<tool_call>
  <name>TOOL_NAME</name>
  <input>
    <param_name>value</param_name>
  </input>
</tool_call>

## Available Tools
- read_file(path): Read a file from the project
- write_file(path, content): Save content to a file
- list_dir(path): List directory contents
- memory_store(key, value): Remember something persistently
- memory_search(query): Search past memories

For document writing (letters, CVs, reports): ask 3-5 focused questions, then write a polished result and save it to a file."""

def _safe_path(raw: str) -> Path:
    p = Path(raw).resolve()
    if not str(p).startswith(str(ROOT)):
        raise PermissionError(f"Path outside project: {p}")
    return p

def run_tool(name: str, params: dict) -> str:
    try:
        if name == "read_file":
            p = _safe_path(params.get("path", ""))
            return p.read_text(encoding="utf-8")[:4000] if p.exists() else f"Not found: {p}"
        elif name == "write_file":
            p = _safe_path(params.get("path", "output.txt"))
            p.parent.mkdir(parents=True, exist_ok=True)
            content = params.get("content", "")
            p.write_text(content, encoding="utf-8")
            return f"Saved to {p.name} ({len(content)} chars)"
        elif name == "list_dir":
            p = _safe_path(params.get("path", "."))
            items = sorted(p.iterdir(), key=lambda x: (x.is_file(), x.name))
            return "\n".join(("📄 " if i.is_file() else "📁 ") + i.name for i in items if not i.name.startswith("."))
        elif name == "memory_store":
            mem_file = ROOT / ".agent_data" / "chat_memory.json"
            mem_file.parent.mkdir(exist_ok=True)
            mem = json.loads(mem_file.read_text()) if mem_file.exists() else {}
            mem[params.get("key", "note")] = params.get("value", "")
            mem_file.write_text(json.dumps(mem, indent=2))
            return f"Remembered: {params.get('key')}"
        elif name == "memory_search":
            mem_file = ROOT / ".agent_data" / "chat_memory.json"
            if not mem_file.exists(): return "No memories yet."
            mem = json.loads(mem_file.read_text())
            q = params.get("query", "").lower()
            results = {k: v for k, v in mem.items() if q in k.lower() or q in v.lower()}
            return json.dumps(results, indent=2) if results else f"No memories matching '{q}'"
        return f"Unknown tool: {name}"
    except PermissionError as e:
        return f"Blocked: {e}"
    except Exception as e:
        return f"Error: {e}"

def parse_tool_call(xml_str: str) -> tuple[str, dict]:
    try:
        root = ET.fromstring(f"<root>{xml_str}</root>")
        name = (root.findtext("name") or "").strip()
        params = {}
        inp = root.find("input")
        if inp is not None:
            for child in inp:
                params[child.tag] = (child.text or "").strip()
        return name, params
    except:
        return "", {}

class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    messages: list[ChatMessage]

@app.post("/chat")
async def chat(request: ChatRequest):
    if not GROQ_AVAILABLE:
        raise HTTPException(500, "groq not installed")
    if not GROQ_API_KEY:
        raise HTTPException(500, "GROQ_API_KEY not set")

    client = Groq(api_key=GROQ_API_KEY)
    messages = [{"role": m.role, "content": m.content} for m in request.messages]

    async def generate():
        current_messages = list(messages)
        for step in range(6):
            full_response = ""
            try:
                stream = client.chat.completions.create(
                    model=MODEL, max_tokens=4096, temperature=0.7, stream=True,
                    messages=[{"role": "system", "content": SYSTEM_PROMPT}, *current_messages],
                )
                for chunk in stream:
                    full_response += chunk.choices[0].delta.content or ""
            except Exception as e:
                yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"
                return

            tool_match = re.search(r"<tool_call>(.*?)</tool_call>", full_response, re.DOTALL)
            if tool_match:
                tool_name, params = parse_tool_call(tool_match.group(1))
                if tool_name:
                    yield f"data: {json.dumps({'type': 'tool', 'tool': tool_name, 'params': params})}\n\n"
                    observation = run_tool(tool_name, params)
                    current_messages.append({"role": "assistant", "content": full_response})
                    current_messages.append({"role": "user", "content": f"<observation>{observation}</observation>"})
                    continue

            clean = re.sub(r"<tool_call>.*?</tool_call>", "", full_response, flags=re.DOTALL).strip()
            words = clean.split(" ")
            for i, word in enumerate(words):
                yield f"data: {json.dumps({'type': 'text', 'content': word + (' ' if i < len(words)-1 else '')})}\n\n"
                await asyncio.sleep(0.018)

            yield f"data: {json.dumps({'type': 'done'})}\n\n"
            return

        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")

@app.get("/health")
async def health():
    return {"status": "ok", "groq": GROQ_AVAILABLE, "key": bool(GROQ_API_KEY), "model": MODEL}

if __name__ == "__main__":
    import uvicorn
    print(f"🚀 Agent Chat Server → http://localhost:8000")
    print(f"   GROQ_API_KEY: {'✅ set' if GROQ_API_KEY else '❌ not set — export GROQ_API_KEY=...'}")
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="warning")