# agents/v0_2_0/agent.py
"""
Core ReAct agent loop for v0.2.0.

Improvements over v0.1.0:
  - Sliding-window context (ContextManager)
  - Persistent SQLite memory (via memory tools)
  - Automatic summarization of dropped context
  - Retry/backoff on API errors
  - Experiment run logging (RunLogger)
"""

import re
import time
import xml.etree.ElementTree as ET
from typing import Optional

from groq import Groq
from groq import APIStatusError, APIConnectionError

from .config import (
    MAX_REACT_STEPS, MAX_TOKENS, MODEL,
    GROQ_API_KEY, CURRENT_VERSION,
    RETRY_ATTEMPTS, RETRY_BASE_WAIT,
)
from .prompts import (
    SYSTEM_PROMPT, make_user_message,
    make_self_improve_message, make_summarize_message,
)
from .tools import dispatch, tool_definitions_as_text
from .context import ContextManager
from .logger import RunLogger


# ── XML helpers ───────────────────────────────────────────────────────────────

def _extract_xml_block(text: str, tag: str) -> Optional[str]:
    pattern = rf"<{tag}>(.*?)</{tag}>"
    m = re.search(pattern, text, re.DOTALL)
    return m.group(1).strip() if m else None


def _parse_tool_call(xml_str: str) -> tuple[str, dict]:
    try:
        root = ET.fromstring(f"<root>{xml_str}</root>")
        name_el  = root.find("name")
        input_el = root.find("input")
        if name_el is None:
            return "", {}
        name   = (name_el.text or "").strip()
        params = {}
        if input_el is not None:
            for child in input_el:
                params[child.tag] = (child.text or "").strip()
        return name, params
    except ET.ParseError:
        return "", {}


# ── Agent ─────────────────────────────────────────────────────────────────────

class Agent:
    """
    ReAct agent v0.2.0 with sliding-window context, persistent memory,
    retry/backoff, and experiment logging.
    """

    def __init__(self, verbose: bool = True):
        self.verbose = verbose
        self.client  = Groq(api_key=GROQ_API_KEY)
        self.logger  = RunLogger()

        self.system_prompt = (
            SYSTEM_PROMPT + "\n\n" + tool_definitions_as_text()
        )
        self.ctx = ContextManager()

    # ── Logging ───────────────────────────────────────────────────────────────

    def _log(self, label: str, text: str, color: str = "0"):
        if self.verbose:
            print(f"\033[{color}m[{label}]\033[0m {text}", flush=True)

    def _log_step(self, t: str):    self._log("STEP",        t, "90")
    def _log_action(self, t: str):  self._log("ACTION",      t, "36")
    def _log_obs(self, t: str):     self._log("OBSERVATION", t, "32")
    def _log_answer(self, t: str):  self._log("ANSWER",      t, "35")
    def _log_error(self, t: str):   self._log("ERROR",       t, "31")
    def _log_info(self, t: str):    self._log("INFO",        t, "34")

    # ── API call with retry ───────────────────────────────────────────────────

    def _call_model(self, messages: list[dict]) -> str:
        """Call Groq with retry/backoff on transient errors."""
        wait = RETRY_BASE_WAIT
        for attempt in range(1, RETRY_ATTEMPTS + 1):
            try:
                response = self.client.chat.completions.create(
                    model=MODEL,
                    max_tokens=MAX_TOKENS,
                    temperature=0.7,
                    messages=[
                        {"role": "system", "content": self.system_prompt},
                        *messages,
                    ],
                )
                return response.choices[0].message.content
            except APIStatusError as e:
                if e.status_code in (429, 503) and attempt < RETRY_ATTEMPTS:
                    self._log_error(f"API error {e.status_code}. Retrying in {wait}s (attempt {attempt}/{RETRY_ATTEMPTS})")
                    time.sleep(wait)
                    wait *= 2
                else:
                    raise
            except APIConnectionError:
                if attempt < RETRY_ATTEMPTS:
                    self._log_error(f"Connection error. Retrying in {wait}s")
                    time.sleep(wait)
                    wait *= 2
                else:
                    raise

    # ── Summarization ─────────────────────────────────────────────────────────

    def _summarize_overflow(self) -> None:
        """Summarize messages that have fallen out of the context window."""
        to_summarize = self.ctx.get_messages_to_summarize()
        if not to_summarize:
            return

        self._log_info(f"Summarizing {len(to_summarize)} overflow messages...")
        conversation_text = "\n".join(
            f"{m['role'].upper()}: {m['content']}" for m in to_summarize
        )
        summary_prompt = make_summarize_message(conversation_text)

        try:
            summary = self._call_model([
                {"role": "user", "content": summary_prompt}
            ])
            self.ctx.set_summary(summary)
            self._log_info(f"Summary: {summary[:150]}...")
        except Exception as e:
            self._log_error(f"Summarization failed: {e}. Proceeding without summary.")

    # ── ReAct loop ────────────────────────────────────────────────────────────

    def react_loop(self) -> str:
        for step in range(MAX_REACT_STEPS):
            self._log_step(f"{step + 1}/{MAX_REACT_STEPS}  |  ctx_msgs={len(self.ctx)}")
            self.logger.step()

            # Summarize if context is overflowing
            if self.ctx.needs_summarization():
                self._summarize_overflow()

            # Get windowed messages and call model
            windowed = self.ctx.get_windowed()
            raw = self._call_model(windowed)

            # Add assistant response to full history
            self.ctx.add("assistant", raw)

            # ── Final answer? ─────────────────────────────────────────────────
            final = _extract_xml_block(raw, "final_answer")
            if final:
                self._log_answer(final[:300] + ("..." if len(final) > 300 else ""))
                self.logger.finish("success", notes=final[:200])
                return final

            # ── Tool call? ────────────────────────────────────────────────────
            tool_xml = _extract_xml_block(raw, "tool_call")
            if tool_xml:
                tool_name, params = _parse_tool_call(tool_xml)
                if not tool_name:
                    observation = "ERROR: Could not parse <tool_call> XML. Check your syntax."
                    self._log_error(observation)
                else:
                    self._log_action(f"{tool_name}({params})")
                    observation = dispatch(tool_name, params)
                    if len(observation) > 6000:
                        observation = observation[:6000] + "\n... [TRUNCATED]"
                    self._log_obs(
                        observation[:400] + ("..." if len(observation) > 400 else "")
                    )

                self.ctx.add("user", f"<observation>\n{observation}\n</observation>")

            else:
                # Neither tool call nor final answer — nudge
                self._log_error("No tool_call or final_answer. Nudging model.")
                self.ctx.add("user", (
                    "Please either call a tool using <tool_call>...</tool_call> "
                    "or give your final answer using <final_answer>...</final_answer>."
                ))

        self.logger.finish("max_steps_reached")
        return "ERROR: Reached MAX_REACT_STEPS without a final answer."

    # ── Public entry points ───────────────────────────────────────────────────

    def run(self, task: str) -> str:
        """Execute a task."""
        run_id = self.logger.start(task)
        self._log_info(f"Run ID: {run_id} | Version: {CURRENT_VERSION}")
        self.ctx = ContextManager()
        self.ctx.add("user", make_user_message(task))
        return self.react_loop()

    def self_improve(self, next_version: str = "v0.3.0") -> str:
        """Run the self-improvement cycle."""
        run_id = self.logger.start(f"self_improve:{CURRENT_VERSION}→{next_version}")
        self._log_info(f"Self-improve run: {run_id} | {CURRENT_VERSION} → {next_version}")
        self.ctx = ContextManager()
        self.ctx.add("user", make_self_improve_message(CURRENT_VERSION, next_version))
        return self.react_loop()