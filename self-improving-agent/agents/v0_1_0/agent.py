# # agents/v0.1.0/agent.py
# """
# Core ReAct agent loop for v0.1.0.

# Architecture:
#   Agent
#   ├── system_prompt  (identity + tool schema)
#   ├── messages[]     (full conversation history — simple context strategy)
#   ├── react_loop()   (Thought → Action → Observation × N → Answer)
#   └── run()          (public entry point)

# Context strategy (v0.1.0 — naive):
#   Keep ALL messages in context. This is simple and debuggable.
#   v0.2.0 will introduce summarization / sliding window.
# """

# import re
# import sys
# import xml.etree.ElementTree as ET
# from typing import Optional

# import anthropic

# from .config import MAX_REACT_STEPS, MAX_TOKENS, MODEL, ANTHROPIC_API_KEY
# from .prompts import SYSTEM_PROMPT, make_user_message, make_self_improve_message
# from .tools import dispatch, tool_definitions_as_text
# from .config import CURRENT_VERSION


# # ── XML parsing helpers ───────────────────────────────────────────────────────

# def _extract_xml_block(text: str, tag: str) -> Optional[str]:
#     """Extract the content of the first matching XML tag from text."""
#     pattern = rf"<{tag}>(.*?)</{tag}>"
#     m = re.search(pattern, text, re.DOTALL)
#     return m.group(1).strip() if m else None


# def _parse_tool_call(xml_str: str) -> tuple[str, dict]:
#     """
#     Parse a <tool_call> XML block into (tool_name, params_dict).
#     Returns ('', {}) on parse failure.
#     """
#     try:
#         root = ET.fromstring(f"<root>{xml_str}</root>")
#         name_el = root.find("name")
#         input_el = root.find("input")
#         if name_el is None:
#             return "", {}
#         name = name_el.text.strip() if name_el.text else ""
#         params = {}
#         if input_el is not None:
#             for child in input_el:
#                 params[child.tag] = (child.text or "").strip()
#         return name, params
#     except ET.ParseError as e:
#         return "", {}


# # ── Agent ─────────────────────────────────────────────────────────────────────

# class Agent:
#     """
#     Minimal ReAct agent.

#     Public methods:
#         run(task)          — execute a task, return final answer string
#         self_improve()     — run the self-improvement loop
#     """

#     def __init__(self, verbose: bool = True):
#         self.verbose = verbose
#         self.client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

#         # Build system prompt once (identity + tools)
#         self.system_prompt = (
#             SYSTEM_PROMPT
#             + "\n\n"
#             + tool_definitions_as_text()
#         )

#         # Message history (naive: keep everything)
#         self.messages: list[dict] = []

#     # ── Logging ───────────────────────────────────────────────────────────────

#     def _log(self, label: str, text: str, color_code: str = "0"):
#         if self.verbose:
#             print(f"\033[{color_code}m[{label}]\033[0m {text}", flush=True)

#     def _log_thought(self, t: str):   self._log("THOUGHT",      t, "33")   # yellow
#     def _log_action(self, t: str):    self._log("ACTION",       t, "36")   # cyan
#     def _log_obs(self, t: str):       self._log("OBSERVATION",  t, "32")   # green
#     def _log_answer(self, t: str):    self._log("ANSWER",       t, "35")   # magenta
#     def _log_error(self, t: str):     self._log("ERROR",        t, "31")   # red

#     # ── Core API call ─────────────────────────────────────────────────────────

#     def _call_model(self) -> str:
#         """Send current message history to the model and return raw text."""
#         response = self.client.messages.create(
#             model=MODEL,
#             max_tokens=MAX_TOKENS,
#             system=self.system_prompt,
#             messages=self.messages,
#         )
#         return response.content[0].text

#     # ── ReAct loop ────────────────────────────────────────────────────────────

#     def react_loop(self) -> str:
#         """
#         Run the ReAct loop until a <final_answer> is produced or MAX_REACT_STEPS reached.
#         Returns the final answer string.
#         """
#         for step in range(MAX_REACT_STEPS):
#             self._log("STEP", f"{step + 1}/{MAX_REACT_STEPS}", "90")

#             # 1. Call model
#             raw = self._call_model()

#             # 2. Add assistant turn to history
#             self.messages.append({"role": "assistant", "content": raw})

#             # 3. Check for final answer
#             final = _extract_xml_block(raw, "final_answer")
#             if final:
#                 self._log_answer(final[:300] + ("..." if len(final) > 300 else ""))
#                 return final

#             # 4. Check for tool call
#             tool_xml = _extract_xml_block(raw, "tool_call")
#             if tool_xml:
#                 tool_name, params = _parse_tool_call(tool_xml)
#                 if not tool_name:
#                     observation = "ERROR: Could not parse tool_call XML. Check your syntax."
#                     self._log_error(observation)
#                 else:
#                     self._log_action(f"{tool_name}({params})")
#                     observation = dispatch(tool_name, params)
#                     # Truncate very long observations to preserve context budget
#                     if len(observation) > 6000:
#                         observation = observation[:6000] + "\n... [TRUNCATED — use read_file with specific path for more]"
#                     self._log_obs(observation[:400] + ("..." if len(observation) > 400 else ""))

#                 # 5. Add observation as next user turn
#                 self.messages.append({
#                     "role": "user",
#                     "content": f"<observation>\n{observation}\n</observation>"
#                 })
#             else:
#                 # Model produced neither tool call nor final answer — nudge it
#                 self._log_error("No tool_call or final_answer found. Nudging model.")
#                 self.messages.append({
#                     "role": "user",
#                     "content": (
#                         "Please either call a tool using <tool_call>...</tool_call> "
#                         "or provide your final answer using <final_answer>...</final_answer>."
#                     )
#                 })

#         return "ERROR: Reached MAX_REACT_STEPS without a final answer."

#     # ── Public entry points ───────────────────────────────────────────────────

#     def run(self, task: str) -> str:
#         """Execute a task from scratch."""
#         self.messages = [{"role": "user", "content": make_user_message(task)}]
#         return self.react_loop()

#     def self_improve(self, next_version: str = "v0.2.0") -> str:
#         """
#         Run the self-improvement loop:
#         1. Read own source
#         2. Critique architecture
#         3. Write improved version to ./agents/<next_version>/
#         """
#         self._log("SELF-IMPROVE", f"Starting: {CURRENT_VERSION} → {next_version}", "35")
#         self.messages = [{
#             "role": "user",
#             "content": make_self_improve_message(CURRENT_VERSION, next_version),
#         }]
#         return self.react_loop()


# agents/v0_1_0/agent.py
# """
# Core ReAct agent loop for v0.1.0 — Gemini backend.
# """

# import re
# import sys
# import xml.etree.ElementTree as ET
# from typing import Optional

# from google import genai
# from google.genai import types

# from .config import MAX_REACT_STEPS, MAX_TOKENS, MODEL, GEMINI_API_KEY, CURRENT_VERSION
# from .prompts import SYSTEM_PROMPT, make_user_message, make_self_improve_message
# from .tools import dispatch, tool_definitions_as_text


# # ── XML parsing helpers ───────────────────────────────────────────────────────

# def _extract_xml_block(text: str, tag: str) -> Optional[str]:
#     pattern = rf"<{tag}>(.*?)</{tag}>"
#     m = re.search(pattern, text, re.DOTALL)
#     return m.group(1).strip() if m else None


# def _parse_tool_call(xml_str: str) -> tuple[str, dict]:
#     try:
#         root = ET.fromstring(f"<root>{xml_str}</root>")
#         name_el = root.find("name")
#         input_el = root.find("input")
#         if name_el is None:
#             return "", {}
#         name = name_el.text.strip() if name_el.text else ""
#         params = {}
#         if input_el is not None:
#             for child in input_el:
#                 params[child.tag] = (child.text or "").strip()
#         return name, params
#     except ET.ParseError:
#         return "", {}


# # ── Agent ─────────────────────────────────────────────────────────────────────

# class Agent:
#     def __init__(self, verbose: bool = True):
#         self.verbose = verbose
#         self.client = genai.Client(api_key=GEMINI_API_KEY)

#         self.system_prompt = (
#             SYSTEM_PROMPT
#             + "\n\n"
#             + tool_definitions_as_text()
#         )

#         self.messages: list[dict] = []

#     # ── Logging ───────────────────────────────────────────────────────────────

#     def _log(self, label: str, text: str, color_code: str = "0"):
#         if self.verbose:
#             print(f"\033[{color_code}m[{label}]\033[0m {text}", flush=True)

#     def _log_thought(self, t: str):  self._log("THOUGHT",     t, "33")
#     def _log_action(self, t: str):   self._log("ACTION",      t, "36")
#     def _log_obs(self, t: str):      self._log("OBSERVATION", t, "32")
#     def _log_answer(self, t: str):   self._log("ANSWER",      t, "35")
#     def _log_error(self, t: str):    self._log("ERROR",       t, "31")

#     # ── Core API call ─────────────────────────────────────────────────────────

#     def _call_model(self) -> str:
#         """Send current message history to Gemini and return raw text."""
#         # Convert our simple {role, content} history to Gemini Content objects
#         gemini_history = []
#         for msg in self.messages[:-1]:  # all but last
#             role = "user" if msg["role"] == "user" else "model"
#             gemini_history.append(
#                 types.Content(role=role, parts=[types.Part(text=msg["content"])])
#             )

#         # Last message is the current user turn
#         last = self.messages[-1]
#         current_content = last["content"]

#         response = self.client.models.generate_content(
#             model=MODEL,
#             contents=gemini_history + [
#                 types.Content(role="user", parts=[types.Part(text=current_content)])
#             ],
#             config=types.GenerateContentConfig(
#                 system_instruction=self.system_prompt,
#                 max_output_tokens=MAX_TOKENS,
#                 temperature=0.7,
#             ),
#         )
#         return response.text

#     # ── ReAct loop ────────────────────────────────────────────────────────────

#     def react_loop(self) -> str:
#         for step in range(MAX_REACT_STEPS):
#             self._log("STEP", f"{step + 1}/{MAX_REACT_STEPS}", "90")

#             raw = self._call_model()

#             self.messages.append({"role": "assistant", "content": raw})

#             # Check for final answer
#             final = _extract_xml_block(raw, "final_answer")
#             if final:
#                 self._log_answer(final[:300] + ("..." if len(final) > 300 else ""))
#                 return final

#             # Check for tool call
#             tool_xml = _extract_xml_block(raw, "tool_call")
#             if tool_xml:
#                 tool_name, params = _parse_tool_call(tool_xml)
#                 if not tool_name:
#                     observation = "ERROR: Could not parse tool_call XML. Check your syntax."
#                     self._log_error(observation)
#                 else:
#                     self._log_action(f"{tool_name}({params})")
#                     observation = dispatch(tool_name, params)
#                     if len(observation) > 6000:
#                         observation = observation[:6000] + "\n... [TRUNCATED]"
#                     self._log_obs(observation[:400] + ("..." if len(observation) > 400 else ""))

#                 self.messages.append({
#                     "role": "user",
#                     "content": f"<observation>\n{observation}\n</observation>"
#                 })
#             else:
#                 self._log_error("No tool_call or final_answer found. Nudging model.")
#                 self.messages.append({
#                     "role": "user",
#                     "content": (
#                         "Please either call a tool using <tool_call>...</tool_call> "
#                         "or provide your final answer using <final_answer>...</final_answer>."
#                     )
#                 })

#         return "ERROR: Reached MAX_REACT_STEPS without a final answer."

#     # ── Public entry points ───────────────────────────────────────────────────

#     def run(self, task: str) -> str:
#         self.messages = [{"role": "user", "content": make_user_message(task)}]
#         return self.react_loop()

#     def self_improve(self, next_version: str = "v0.2.0") -> str:
#         self._log("SELF-IMPROVE", f"Starting: {CURRENT_VERSION} → {next_version}", "35")
#         self.messages = [{
#             "role": "user",
#             "content": make_self_improve_message(CURRENT_VERSION, next_version),
#         }]
#         return self.react_loop()



# agents/v0_1_0/agent.py
"""
Core ReAct agent loop for v0.1.0 — Groq backend (Llama 3.3 70B).
"""

import re
import xml.etree.ElementTree as ET
from typing import Optional

from groq import Groq

from .config import (
    MAX_REACT_STEPS, MAX_TOKENS, MODEL,
    GROQ_API_KEY, CURRENT_VERSION
)
from .prompts import SYSTEM_PROMPT, make_user_message, make_self_improve_message
from .tools import dispatch, tool_definitions_as_text


# ── XML parsing helpers ───────────────────────────────────────────────────────

def _extract_xml_block(text: str, tag: str) -> Optional[str]:
    pattern = rf"<{tag}>(.*?)</{tag}>"
    m = re.search(pattern, text, re.DOTALL)
    return m.group(1).strip() if m else None


def _parse_tool_call(xml_str: str) -> tuple[str, dict]:
    try:
        root = ET.fromstring(f"<root>{xml_str}</root>")
        name_el = root.find("name")
        input_el = root.find("input")
        if name_el is None:
            return "", {}
        name = name_el.text.strip() if name_el.text else ""
        params = {}
        if input_el is not None:
            for child in input_el:
                params[child.tag] = (child.text or "").strip()
        return name, params
    except ET.ParseError:
        return "", {}


# ── Agent ─────────────────────────────────────────────────────────────────────

class Agent:
    def __init__(self, verbose: bool = True):
        self.verbose = verbose
        self.client = Groq(api_key=GROQ_API_KEY)

        self.system_prompt = (
            SYSTEM_PROMPT
            + "\n\n"
            + tool_definitions_as_text()
        )

        self.messages: list[dict] = []

    # ── Logging ───────────────────────────────────────────────────────────────

    def _log(self, label: str, text: str, color_code: str = "0"):
        if self.verbose:
            print(f"\033[{color_code}m[{label}]\033[0m {text}", flush=True)

    def _log_action(self, t: str):  self._log("ACTION",      t, "36")
    def _log_obs(self, t: str):     self._log("OBSERVATION", t, "32")
    def _log_answer(self, t: str):  self._log("ANSWER",      t, "35")
    def _log_error(self, t: str):   self._log("ERROR",       t, "31")

    # ── Core API call ─────────────────────────────────────────────────────────

    def _call_model(self) -> str:
        """Send current message history to Groq and return raw text."""
        response = self.client.chat.completions.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            temperature=0.7,
            messages=[
                {"role": "system", "content": self.system_prompt},
                *self.messages,
            ],
        )
        return response.choices[0].message.content

    # ── ReAct loop ────────────────────────────────────────────────────────────

    def react_loop(self) -> str:
        for step in range(MAX_REACT_STEPS):
            self._log("STEP", f"{step + 1}/{MAX_REACT_STEPS}", "90")

            raw = self._call_model()

            self.messages.append({"role": "assistant", "content": raw})

            # Check for final answer
            final = _extract_xml_block(raw, "final_answer")
            if final:
                self._log_answer(final[:300] + ("..." if len(final) > 300 else ""))
                return final

            # Check for tool call
            tool_xml = _extract_xml_block(raw, "tool_call")
            if tool_xml:
                tool_name, params = _parse_tool_call(tool_xml)
                if not tool_name:
                    observation = "ERROR: Could not parse tool_call XML. Check syntax."
                    self._log_error(observation)
                else:
                    self._log_action(f"{tool_name}({params})")
                    observation = dispatch(tool_name, params)
                    if len(observation) > 6000:
                        observation = observation[:6000] + "\n... [TRUNCATED]"
                    self._log_obs(
                        observation[:400] + ("..." if len(observation) > 400 else "")
                    )

                self.messages.append({
                    "role": "user",
                    "content": f"<observation>\n{observation}\n</observation>"
                })
            else:
                self._log_error("No tool_call or final_answer found. Nudging model.")
                self.messages.append({
                    "role": "user",
                    "content": (
                        "Please either call a tool using <tool_call>...</tool_call> "
                        "or provide your final answer using <final_answer>...</final_answer>."
                    )
                })

        return "ERROR: Reached MAX_REACT_STEPS without a final answer."

    # ── Public entry points ───────────────────────────────────────────────────

    def run(self, task: str) -> str:
        self.messages = [{"role": "user", "content": make_user_message(task)}]
        return self.react_loop()

    def self_improve(self, next_version: str = "v0.2.0") -> str:
        self._log("SELF-IMPROVE", f"Starting: {CURRENT_VERSION} → {next_version}", "35")
        self.messages = [{
            "role": "user",
            "content": make_self_improve_message(CURRENT_VERSION, next_version),
        }]
        return self.react_loop()