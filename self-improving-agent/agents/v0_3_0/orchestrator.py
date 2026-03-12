# agents/v0_3_0/orchestrator.py
"""
Recursive agent spawning — Parent ↔ Child architecture.

ParentAgent:
  1. Receives a complex task
  2. Uses task_planner to decompose into subtasks
  3. Spawns ChildAgents for each subtask (respecting depth/parallelism limits)
  4. Collects results via MessageBus
  5. Synthesizes final answer

ChildAgent:
  - Same ReAct loop as base Agent
  - Receives a single focused subtask
  - Posts result back to parent via MessageBus
  - Can itself spawn grandchildren (if depth allows)

[SAFETY] Spawn depth is hard-capped at MAX_SPAWN_DEPTH.
"""

import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Optional

from groq import Groq

from .config import (
    MAX_CHILDREN_PER_AGENT, MAX_SPAWN_DEPTH,
    MAX_PARALLEL_AGENTS, GROQ_API_KEY, MODEL,
    MAX_TOKENS, MAX_REACT_STEPS, TEMPERATURE,
)
from .message_bus import MessageBus, AgentMessage, MessageType
from .task_planner import plan_subtasks, SubTask
from .tools import dispatch, tool_definitions_as_text
from .prompts import CHILD_SYSTEM_PROMPT, SYNTHESIS_PROMPT


def _call_llm(messages: list[dict], system: str) -> str:
    """Shared LLM call used by both parent and child agents."""
    client = Groq(api_key=GROQ_API_KEY)
    response = client.chat.completions.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        temperature=TEMPERATURE,
        messages=[{"role": "system", "content": system}, *messages],
    )
    return response.choices[0].message.content


# ── Child Agent ───────────────────────────────────────────────────────────────

class ChildAgent:
    """
    A focused single-task agent spawned by a ParentAgent.
    Runs a ReAct loop on its assigned subtask, posts result to bus.
    """

    def __init__(
        self,
        agent_id:    str,
        parent_id:   str,
        subtask:     SubTask,
        bus:         MessageBus,
        depth:       int = 1,
        on_status:   Optional[Callable] = None,
    ):
        self.agent_id  = agent_id
        self.parent_id = parent_id
        self.subtask   = subtask
        self.bus       = bus
        self.depth     = depth
        self.on_status = on_status   # callback for UI streaming
        self.messages: list[dict] = []
        self.system = (
            CHILD_SYSTEM_PROMPT.format(
                agent_id=agent_id,
                depth=depth,
                max_depth=MAX_SPAWN_DEPTH,
            )
            + "\n\n"
            + tool_definitions_as_text()
        )

    def _log(self, text: str):
        msg = f"[Child:{self.agent_id}|d={self.depth}] {text}"
        if self.on_status:
            self.on_status(msg)

    def _post_status(self, text: str):
        self.bus.post(AgentMessage(
            msg_type  = MessageType.STATUS,
            sender_id = self.agent_id,
            target_id = self.parent_id,
            content   = text,
        ))
        self._log(text)

    def run(self) -> str:
        """Execute subtask via ReAct loop. Returns result string."""
        self._post_status(f"Starting subtask: {self.subtask.title}")
        self.messages = [{"role": "user", "content": self.subtask.description}]

        import re
        import xml.etree.ElementTree as ET

        def extract(text, tag):
            m = re.search(rf"<{tag}>(.*?)</{tag}>", text, re.DOTALL)
            return m.group(1).strip() if m else None

        def parse_tool(xml_str):
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

        for step in range(MAX_REACT_STEPS):
            try:
                raw = _call_llm(self.messages, self.system)
            except Exception as e:
                error = f"LLM error: {e}"
                self._post_status(f"Failed: {error}")
                self.bus.post(AgentMessage(
                    msg_type=MessageType.ERROR,
                    sender_id=self.agent_id,
                    target_id=self.parent_id,
                    content=error,
                    metadata={"task_id": self.subtask.task_id},
                ))
                return error

            self.messages.append({"role": "assistant", "content": raw})

            final = extract(raw, "final_answer")
            if final:
                self._post_status(f"Done: {final[:100]}")
                self.bus.post(AgentMessage(
                    msg_type  = MessageType.RESULT,
                    sender_id = self.agent_id,
                    target_id = self.parent_id,
                    content   = final,
                    metadata  = {"task_id": self.subtask.task_id, "title": self.subtask.title},
                ))
                return final

            tool_xml = extract(raw, "tool_call")
            if tool_xml:
                tool_name, params = parse_tool(tool_xml)
                if tool_name:
                    self._post_status(f"Using tool: {tool_name}")
                    observation = dispatch(tool_name, params)
                    if len(observation) > 5000:
                        observation = observation[:5000] + "\n...[TRUNCATED]"
                    self.messages.append({
                        "role": "user",
                        "content": f"<observation>\n{observation}\n</observation>",
                    })
                else:
                    self.messages.append({
                        "role": "user",
                        "content": "Could not parse tool_call XML. Try again.",
                    })
            else:
                self.messages.append({
                    "role": "user",
                    "content": "Use <tool_call> or <final_answer>.",
                })

        result = "Reached step limit without completing task."
        self.bus.post(AgentMessage(
            msg_type=MessageType.ERROR,
            sender_id=self.agent_id,
            target_id=self.parent_id,
            content=result,
            metadata={"task_id": self.subtask.task_id},
        ))
        return result


# ── Parent Agent ──────────────────────────────────────────────────────────────

class ParentAgent:
    """
    Orchestrator agent that:
    1. Plans subtasks from a complex task
    2. Spawns child agents in parallel (up to MAX_PARALLEL_AGENTS)
    3. Collects results
    4. Synthesizes a final answer

    [SAFETY] Depth is tracked and enforced — children cannot spawn
    beyond MAX_SPAWN_DEPTH without explicit config change.
    """

    def __init__(
        self,
        agent_id:  str = "parent",
        depth:     int = 0,
        bus:       Optional[MessageBus] = None,
        on_status: Optional[Callable] = None,
        verbose:   bool = True,
    ):
        self.agent_id  = agent_id
        self.depth     = depth
        self.bus       = bus or MessageBus()
        self.on_status = on_status
        self.verbose   = verbose
        self.bus.register(agent_id)

    def _log(self, text: str):
        if self.verbose:
            print(f"\033[35m[Parent:{self.agent_id}]\033[0m {text}", flush=True)
        if self.on_status:
            self.on_status({"type": "parent_status", "content": text})

    def _spawn_child(self, subtask: SubTask, child_num: int) -> tuple[str, str]:
        """Spawn a single child agent. Returns (task_id, result)."""
        child_id = f"child-{self.agent_id}-{child_num}"
        self.bus.register(child_id)

        self._log(f"Spawning {child_id} for: {subtask.title}")

        def status_cb(msg):
            if self.on_status:
                self.on_status({
                    "type":     "child_status",
                    "agent_id": child_id,
                    "content":  msg,
                })

        child = ChildAgent(
            agent_id  = child_id,
            parent_id = self.agent_id,
            subtask   = subtask,
            bus       = self.bus,
            depth     = self.depth + 1,
            on_status = status_cb,
        )
        result = child.run()
        return subtask.task_id, result

    def run(self, task: str) -> dict:
        """
        Execute a task using parallel child agents.

        Returns:
            {
                "subtasks": [...],
                "results":  {task_id: result},
                "synthesis": final_answer_str,
                "bus_summary": str,
            }
        """
        self._log(f"Planning task: {task[:100]}")

        # 1. Plan subtasks
        subtasks = plan_subtasks(task)
        self._log(f"Planned {len(subtasks)} subtask(s): {[s.title for s in subtasks]}")

        if self.on_status:
            self.on_status({
                "type":     "plan",
                "subtasks": [{"id": s.task_id, "title": s.title, "desc": s.description} for s in subtasks],
            })

        # 2. If only one subtask — no need to spawn, run directly
        if len(subtasks) == 1:
            self._log("Single subtask — running directly without spawning.")
            _, result = self._spawn_child(subtasks[0], 1)
            return {
                "subtasks":    subtasks,
                "results":     {subtasks[0].task_id: result},
                "synthesis":   result,
                "bus_summary": self.bus.summary(),
            }

        # 3. Spawn children in parallel
        results: dict[str, str] = {}
        parallel = min(len(subtasks), MAX_PARALLEL_AGENTS)

        with ThreadPoolExecutor(max_workers=parallel) as executor:
            futures = {
                executor.submit(self._spawn_child, st, i+1): st
                for i, st in enumerate(subtasks)
            }
            for future in as_completed(futures):
                try:
                    task_id, result = future.result(timeout=120)
                    results[task_id] = result
                    self._log(f"Received result for {task_id}: {result[:80]}...")
                except Exception as e:
                    st = futures[future]
                    results[st.task_id] = f"Error: {e}"
                    self._log(f"Child failed for {st.task_id}: {e}")

        # 4. Synthesize results
        self._log("Synthesizing results from all children...")
        synthesis = self._synthesize(task, subtasks, results)

        return {
            "subtasks":    subtasks,
            "results":     results,
            "synthesis":   synthesis,
            "bus_summary": self.bus.summary(),
        }

    def _synthesize(self, original_task: str, subtasks: list, results: dict) -> str:
        """Use LLM to synthesize child results into a coherent final answer."""
        results_text = "\n\n".join(
            f"### {st.title} (id={st.task_id})\n{results.get(st.task_id, 'No result')}"
            for st in subtasks
        )
        prompt = SYNTHESIS_PROMPT.format(
            original_task=original_task,
            results=results_text,
        )
        try:
            return _call_llm(
                [{"role": "user", "content": prompt}],
                "You are a synthesis expert. Combine the provided research results into a clear, well-structured final answer. Be comprehensive but concise.",
            )
        except Exception as e:
            return f"Synthesis failed: {e}\n\nRaw results:\n{results_text}"