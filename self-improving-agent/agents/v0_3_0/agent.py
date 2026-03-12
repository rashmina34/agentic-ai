# agents/v0_3_0/agent.py
"""
Main agent for v0.3.0.
For simple tasks: runs solo ReAct loop (same as v0.2.0).
For complex tasks: delegates to ParentAgent orchestrator.
"""

import re
import time
import xml.etree.ElementTree as ET
from typing import Optional

from groq import Groq, APIStatusError, APIConnectionError

from .config import (
    MAX_REACT_STEPS, MAX_TOKENS, MODEL, TEMPERATURE,
    GROQ_API_KEY, CURRENT_VERSION,
    RETRY_ATTEMPTS, RETRY_BASE_WAIT,
)
from .prompts import SYSTEM_PROMPT, make_user_message, make_self_improve_message
from .tools import dispatch, tool_definitions_as_text
from .context import ContextManager
from .logger import RunLogger
from .orchestrator import ParentAgent
from .message_bus import MessageBus


def _extract(text: str, tag: str) -> Optional[str]:
    m = re.search(rf"<{tag}>(.*?)</{tag}>", text, re.DOTALL)
    return m.group(1).strip() if m else None

def _parse_tool(xml_str: str) -> tuple[str, dict]:
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


class Agent:
    def __init__(self, verbose: bool = True):
        self.verbose = verbose
        self.client  = Groq(api_key=GROQ_API_KEY)
        self.logger  = RunLogger()
        self.system  = SYSTEM_PROMPT + "\n\n" + tool_definitions_as_text()
        self.ctx     = ContextManager()

    def _log(self, label: str, text: str, c: str = "0"):
        if self.verbose:
            print(f"\033[{c}m[{label}]\033[0m {text}", flush=True)

    def _log_step(self, t):   self._log("STEP",        t, "90")
    def _log_action(self, t): self._log("ACTION",      t, "36")
    def _log_obs(self, t):    self._log("OBS",         t, "32")
    def _log_answer(self, t): self._log("ANSWER",      t, "35")
    def _log_error(self, t):  self._log("ERROR",       t, "31")
    def _log_info(self, t):   self._log("INFO",        t, "34")
    def _log_spawn(self, t):  self._log("SPAWN",       t, "33")

    def _call_model(self, messages: list[dict]) -> str:
        wait = RETRY_BASE_WAIT
        for attempt in range(1, RETRY_ATTEMPTS + 1):
            try:
                r = self.client.chat.completions.create(
                    model=MODEL, max_tokens=MAX_TOKENS, temperature=TEMPERATURE,
                    messages=[{"role": "system", "content": self.system}, *messages],
                )
                return r.choices[0].message.content
            except APIStatusError as e:
                if e.status_code in (429, 503) and attempt < RETRY_ATTEMPTS:
                    self._log_error(f"Rate limit. Retry {attempt} in {wait}s")
                    time.sleep(wait); wait *= 2
                else: raise
            except APIConnectionError:
                if attempt < RETRY_ATTEMPTS:
                    time.sleep(wait); wait *= 2
                else: raise

    def _summarize_overflow(self):
        to_summarize = self.ctx.get_messages_to_summarize()
        if not to_summarize: return
        self._log_info(f"Summarizing {len(to_summarize)} overflow messages")
        conv = "\n".join(f"{m['role'].upper()}: {m['content']}" for m in to_summarize)
        try:
            summary = self._call_model([{
                "role": "user",
                "content": f"Summarize this conversation segment concisely, preserving all key facts:\n\n{conv}"
            }])
            self.ctx.set_summary(summary)
        except Exception as e:
            self._log_error(f"Summarization failed: {e}")

    def react_loop(self) -> str:
        for step in range(MAX_REACT_STEPS):
            self._log_step(f"{step+1}/{MAX_REACT_STEPS} | msgs={len(self.ctx)}")
            self.logger.step()

            if self.ctx.needs_summarization():
                self._summarize_overflow()

            raw = self._call_model(self.ctx.get_windowed())
            self.ctx.add("assistant", raw)

            final = _extract(raw, "final_answer")
            if final:
                self._log_answer(final[:200])
                self.logger.finish("success")
                return final

            tool_xml = _extract(raw, "tool_call")
            if tool_xml:
                tool_name, params = _parse_tool(tool_xml)
                if not tool_name:
                    obs = "ERROR: bad tool_call XML"
                    self._log_error(obs)
                else:
                    if tool_name == "spawn_agent":
                        self._log_spawn(f"Spawning agents for: {params.get('task','')[:80]}")
                        self.logger.spawned()
                    else:
                        self._log_action(f"{tool_name}({params})")
                    obs = dispatch(tool_name, params)
                    if len(obs) > 6000: obs = obs[:6000] + "\n...[TRUNCATED]"
                    self._log_obs(obs[:300] + ("..." if len(obs) > 300 else ""))
                self.ctx.add("user", f"<observation>\n{obs}\n</observation>")
            else:
                self._log_error("No tool_call or final_answer — nudging")
                self.ctx.add("user", "Use <tool_call> or <final_answer>.")

        self.logger.finish("max_steps")
        return "ERROR: max steps reached"

    def run(self, task: str) -> str:
        self.logger.start(task)
        self.ctx = ContextManager()
        self.ctx.add("user", make_user_message(task))
        return self.react_loop()

    def run_orchestrated(self, task: str) -> str:
        """Run task using parallel child agent orchestration."""
        self.logger.start(f"orchestrated:{task}")
        status_lines = []

        def on_status(msg):
            content = msg.get("content", str(msg)) if isinstance(msg, dict) else str(msg)
            status_lines.append(content)
            if self.verbose:
                print(f"\033[33m[ORCH]\033[0m {content}", flush=True)

        parent = ParentAgent(
            agent_id="parent-0", depth=0,
            on_status=on_status, verbose=self.verbose,
        )
        result = parent.run(task)
        self.logger.finish("success", notes=result["synthesis"][:200])
        return result["synthesis"]

    def self_improve(self, next_version: str = "v0.4.0") -> str:
        self.logger.start(f"self_improve→{next_version}")
        self.ctx = ContextManager()
        self.ctx.add("user", make_self_improve_message(CURRENT_VERSION, next_version))
        return self.react_loop()