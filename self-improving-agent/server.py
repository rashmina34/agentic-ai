# server.py — Agent Chat API with fixed memory
import os, sys, json, asyncio, re, xml.etree.ElementTree as ET
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel

# ── Paths — resolved at startup, printed for debugging ───────────────────────
ROOT        = Path(__file__).resolve().parent
DATA_DIR    = ROOT / ".agent_data"
MEMORY_FILE = DATA_DIR / "chat_memory.json"

DATA_DIR.mkdir(parents=True, exist_ok=True)
if not MEMORY_FILE.exists():
    MEMORY_FILE.write_text("{}", encoding="utf-8")

sys.path.insert(0, str(ROOT))

print(f"📁 ROOT      : {ROOT}")
print(f"📁 DATA_DIR  : {DATA_DIR}")
print(f"🧠 MEMORY    : {MEMORY_FILE}")

app = FastAPI(title="Self-Improving Agent API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

try:
    from groq import Groq
    GROQ_AVAILABLE = True
except ImportError:
    GROQ_AVAILABLE = False

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")

# ── Version registry ──────────────────────────────────────────────────────────
VERSIONS = {
    "v0.1.0": {
        "model":       "llama-3.3-70b-versatile",
        "label":       "v0.1.0 · Solo · Naive",
        "color":       "#6b7280",
        "emoji":       "🔵",
        "description": "Single agent, basic ReAct loop, no memory, no retries",
        "features":    ["ReAct loop", "4 tools", "XML tool calling"],
        "limitations": ["No memory", "No retry", "No context management"],
        "has_memory":  False,
        "has_spawn":   False,
    },
    "v0.2.0": {
        "model":       "llama-3.3-70b-versatile",
        "label":       "v0.2.0 · Solo · Smart",
        "color":       "#3b82f6",
        "emoji":       "🟢",
        "description": "Single agent with persistent memory, sliding context, auto-retry",
        "features":    ["Persistent memory", "Sliding window", "Auto-retry", "7 tools"],
        "limitations": ["Single agent", "Sequential only"],
        "has_memory":  True,
        "has_spawn":   False,
    },
    "v0.3.0": {
        "model":       "llama-3.3-70b-versatile",
        "label":       "v0.3.0 · Multi-Agent · Parallel",
        "color":       "#8b5cf6",
        "emoji":       "🟣",
        "description": "Parent spawns parallel child agents, task decomposition, synthesis",
        "features":    ["Parallel agents", "Task planning", "MessageBus", "8 tools"],
        "limitations": ["More API calls", "Higher latency on simple tasks"],
        "has_memory":  True,
        "has_spawn":   True,
    },
}

# ── System prompts ────────────────────────────────────────────────────────────
# CRITICAL: tool XML format must exactly match what parse_tool_call() expects.
# Parameters must be direct children of <input> with exact names: key, value, query

def get_system_prompt(version: str) -> str:
    memory_note = {
        "v0.1.0": "You are v0.1.0 BASIC. You have NO memory tool. Tell users to switch to v0.2.0 for memory.",
        "v0.2.0": "You are v0.2.0 SMART. You MUST use memory_store and memory_search tools to remember information. Always store important facts immediately.",
        "v0.3.0": "You are v0.3.0 MULTI-AGENT. Use memory tools to persist info. Handle complex multi-part tasks thoroughly.",
    }

    return f"""You are a helpful AI assistant. {memory_note.get(version, '')}

Be conversational and warm. For complex tasks like writing documents, ask clarifying questions first.

## HOW TO CALL TOOLS — follow this format EXACTLY:

To store a memory:
<tool_call>
<name>memory_store</name>
<input>
<key>fact_name</key>
<value>the information to remember</value>
</input>
</tool_call>

To search memory:
<tool_call>
<name>memory_search</name>
<input>
<query>what to search for</query>
</input>
</tool_call>

To read a file:
<tool_call>
<name>read_file</name>
<input>
<path>filename.txt</path>
</input>
</tool_call>

To write a file:
<tool_call>
<name>write_file</name>
<input>
<path>output.txt</path>
<content>file content here</content>
</input>
</tool_call>

To list directory:
<tool_call>
<name>list_dir</name>
<input>
<path>.</path>
</input>
</tool_call>

## RULES
- Call ONE tool at a time, wait for the observation, then continue
- For v0.2.0: ALWAYS use memory_store when user shares personal info, project details, preferences
- Never say memory isn't working — just call the tool and it will work
- After storing, confirm to the user what you remembered
"""

# ── Memory helpers ────────────────────────────────────────────────────────────
def read_memory() -> dict:
    try:
        return json.loads(MEMORY_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[MEMORY READ ERROR] {e}")
        return {}

def write_memory(mem: dict) -> None:
    try:
        MEMORY_FILE.write_text(json.dumps(mem, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"[MEMORY WRITE ERROR] {e}")
        raise

# ── Tool dispatcher ───────────────────────────────────────────────────────────
def run_tool(name: str, params: dict, version: str) -> str:
    print(f"[TOOL] {name}({params}) version={version}")  # server-side debug log

    try:
        # ── read_file ─────────────────────────────────────────────────────────
        if name == "read_file":
            path = params.get("path", "").strip()
            if not path:
                return "ERROR: path parameter is required"
            p = (ROOT / path).resolve() if not Path(path).is_absolute() else Path(path).resolve()
            if not str(p).startswith(str(ROOT)):
                return f"ERROR: path outside project root"
            return p.read_text(encoding="utf-8")[:4000] if p.exists() else f"File not found: {p}"

        # ── write_file ────────────────────────────────────────────────────────
        elif name == "write_file":
            path    = params.get("path", "output.txt").strip()
            content = params.get("content", "")
            p = (ROOT / path).resolve() if not Path(path).is_absolute() else Path(path).resolve()
            if not str(p).startswith(str(ROOT)):
                return "ERROR: path outside project root"
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
            return f"✅ Saved to {p.name} ({len(content)} chars)"

        # ── list_dir ──────────────────────────────────────────────────────────
        elif name == "list_dir":
            path = params.get("path", ".").strip() or "."
            p = (ROOT / path).resolve() if not Path(path).is_absolute() else Path(path).resolve()
            if not p.exists():
                return f"Directory not found: {p}"
            items = sorted(p.iterdir(), key=lambda x: (x.is_file(), x.name))
            return "\n".join(
                ("📄 " if i.is_file() else "📁 ") + i.name
                for i in items if not i.name.startswith(".")
            )

        # ── memory_store ──────────────────────────────────────────────────────
        elif name == "memory_store":
            if version == "v0.1.0":
                return "⚠️ Memory not available in v0.1.0 — switch to v0.2.0 in the sidebar"
            key   = params.get("key", "").strip()
            value = params.get("value", "").strip()
            if not key:
                return "ERROR: 'key' parameter is required for memory_store"
            if not value:
                return "ERROR: 'value' parameter is required for memory_store"
            mem = read_memory()
            mem[key] = value
            write_memory(mem)
            print(f"[MEMORY STORED] key={key!r} value={value[:50]!r}")
            return f"✅ Remembered: {key} = {value[:80]}"

        # ── memory_search ─────────────────────────────────────────────────────
        elif name == "memory_search":
            if version == "v0.1.0":
                return "⚠️ Memory not available in v0.1.0 — switch to v0.2.0 in the sidebar"
            query = params.get("query", "").strip()
            if not query:
                return "ERROR: 'query' parameter is required for memory_search"
            mem = read_memory()
            if not mem:
                return "No memories stored yet."
            q = query.lower()
            results = {k: v for k, v in mem.items() if q in k.lower() or q in str(v).lower()}
            if not results:
                # Return all memories if no match, so agent knows what's stored
                all_keys = list(mem.keys())
                return f"No exact match for '{query}'. Stored keys: {all_keys}\n\nAll memories:\n" + \
                       "\n".join(f"  {k}: {v}" for k, v in mem.items())
            return f"Found {len(results)} result(s):\n" + \
                   "\n".join(f"  {k}: {v}" for k, v in results.items())

        return f"Unknown tool: '{name}'. Available: read_file, write_file, list_dir, memory_store, memory_search"

    except Exception as e:
        print(f"[TOOL ERROR] {name}: {e}")
        return f"ERROR in {name}: {str(e)}"

# ── XML tool call parser ──────────────────────────────────────────────────────
def parse_tool_call(xml_str: str) -> tuple[str, dict]:
    """Parse <tool_call> XML. Returns (tool_name, params_dict)."""
    try:
        # Clean up common model formatting issues
        xml_str = xml_str.strip()
        root = ET.fromstring(f"<root>{xml_str}</root>")
        name = (root.findtext("name") or "").strip()
        params = {}
        inp = root.find("input")
        if inp is not None:
            for child in inp:
                params[child.tag] = (child.text or "").strip()
        print(f"[PARSE] tool={name!r} params={params}")
        return name, params
    except ET.ParseError as e:
        print(f"[PARSE ERROR] {e} | xml={xml_str[:200]}")
        return "", {}

# ── Pydantic models ───────────────────────────────────────────────────────────
class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    version: str = "v0.2.0"

# ── Chat endpoint ─────────────────────────────────────────────────────────────
@app.post("/chat")
async def chat(request: ChatRequest):
    if not GROQ_AVAILABLE:
        raise HTTPException(500, "groq not installed — run: pip install groq")
    if not GROQ_API_KEY:
        raise HTTPException(500, "GROQ_API_KEY environment variable not set")

    version = request.version if request.version in VERSIONS else "v0.2.0"
    vinfo   = VERSIONS[version]
    client  = Groq(api_key=GROQ_API_KEY)
    msgs    = [{"role": m.role, "content": m.content} for m in request.messages]

    async def generate():
        yield f"data: {json.dumps({'type': 'version_info', 'version': version, 'vinfo': vinfo})}\n\n"

        current_messages = list(msgs)
        step_count = 0

        for step in range(20):
            step_count += 1
            yield f"data: {json.dumps({'type': 'thinking', 'step': step_count, 'version': version, 'color': vinfo['color']})}\n\n"

            full_response = ""
            try:
                stream = client.chat.completions.create(
                    model=vinfo["model"],
                    max_tokens=4096,
                    temperature=0.7,
                    stream=True,
                    messages=[
                        {"role": "system", "content": get_system_prompt(version)},
                        *current_messages,
                    ],
                )
                for chunk in stream:
                    full_response += chunk.choices[0].delta.content or ""
            except Exception as e:
                yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"
                return

            # Check for tool call
            tool_match = re.search(r"<tool_call>(.*?)</tool_call>", full_response, re.DOTALL)
            if tool_match:
                tool_name, params = parse_tool_call(tool_match.group(1))
                if tool_name:
                    yield f"data: {json.dumps({'type': 'tool', 'tool': tool_name, 'params': params, 'version': version, 'color': vinfo['color']})}\n\n"
                    observation = run_tool(tool_name, params, version)
                    print(f"[OBS] {observation[:100]}")
                    current_messages.append({"role": "assistant", "content": full_response})
                    current_messages.append({
                        "role": "user",
                        "content": f"<observation>{observation}</observation>\nContinue based on this result."
                    })
                    continue
                else:
                    # Could not parse — tell model to fix its XML
                    current_messages.append({"role": "assistant", "content": full_response})
                    current_messages.append({
                        "role": "user",
                        "content": "ERROR: Could not parse your tool_call XML. Make sure <name> and <input> tags are correct."
                    })
                    continue

            # No tool call — stream text to client
            clean = re.sub(r"<tool_call>.*?</tool_call>", "", full_response, flags=re.DOTALL).strip()
            words = clean.split(" ")
            for i, word in enumerate(words):
                yield f"data: {json.dumps({'type': 'text', 'content': word + (' ' if i < len(words)-1 else '')})}\n\n"
                await asyncio.sleep(0.018)

            yield f"data: {json.dumps({'type': 'done', 'steps': step_count, 'version': version})}\n\n"
            return

        yield f"data: {json.dumps({'type': 'done', 'steps': step_count, 'version': version})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")

# ── Debug endpoints ───────────────────────────────────────────────────────────
@app.get("/memory")
async def get_memory():
    """View all stored memories — useful for debugging."""
    return JSONResponse({
        "file":    str(MEMORY_FILE),
        "exists":  MEMORY_FILE.exists(),
        "entries": read_memory(),
    })

@app.delete("/memory")
async def clear_memory():
    """Clear all memories."""
    write_memory({})
    return {"status": "cleared"}

@app.get("/versions")
async def get_versions():
    return VERSIONS

@app.get("/health")
async def health():
    return {
        "status":      "ok",
        "groq":        GROQ_AVAILABLE,
        "key_set":     bool(GROQ_API_KEY),
        "memory_file": str(MEMORY_FILE),
        "memory_ok":   MEMORY_FILE.exists(),
        "root":        str(ROOT),
    }

# ── Startup ───────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    print(f"\n🚀 Agent Chat → http://localhost:8000")
    print(f"   GROQ_API_KEY : {'✅ set' if GROQ_API_KEY else '❌ run: export GROQ_API_KEY=your-key'}")
    print(f"   Memory debug : http://localhost:8000/memory\n")
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="warning")