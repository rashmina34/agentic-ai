# agents/v0_3_0/task_planner.py
"""
LLM-powered task decomposition.

Given a complex task, produces a list of subtasks suitable for
parallel execution by child agents.

Design:
- Single focused LLM call (not a full ReAct loop)
- Returns structured SubTask list
- Respects MAX_CHILDREN_PER_AGENT limit
"""

import json
import re
from dataclasses import dataclass, field
from typing import Optional

from groq import Groq

from .config import GROQ_API_KEY, MODEL, MAX_CHILDREN_PER_AGENT


@dataclass
class SubTask:
    task_id:     str
    title:       str
    description: str
    depends_on:  list[str] = field(default_factory=list)   # task_ids this depends on
    result:      Optional[str] = None
    status:      str = "pending"   # pending | running | done | failed


PLANNER_SYSTEM = """You are a task decomposition expert.
Given a complex task, break it into clear, parallel subtasks.
Each subtask should be independently executable by a separate AI agent.

Respond ONLY with valid JSON — no markdown, no explanation:
{
  "subtasks": [
    {
      "task_id": "t1",
      "title": "Short title",
      "description": "Detailed description of exactly what this agent should do",
      "depends_on": []
    }
  ],
  "reasoning": "Why you split it this way"
}

Rules:
- Maximum """ + str(MAX_CHILDREN_PER_AGENT) + """ subtasks
- Make subtasks as independent as possible
- Each subtask must be concrete and actionable
- If task is simple enough for one agent, return just 1 subtask
"""


def plan_subtasks(task: str, context: str = "") -> list[SubTask]:
    """
    Decompose a task into subtasks using LLM.
    Returns list of SubTask objects.
    Falls back to single subtask on any error.
    """
    client = Groq(api_key=GROQ_API_KEY)

    prompt = f"Task: {task}"
    if context:
        prompt += f"\n\nContext: {context}"

    try:
        response = client.chat.completions.create(
            model=MODEL,
            max_tokens=2048,
            temperature=0.3,   # low temp for structured output
            messages=[
                {"role": "system", "content": PLANNER_SYSTEM},
                {"role": "user",   "content": prompt},
            ],
        )
        raw = response.choices[0].message.content.strip()

        # Strip markdown fences if present
        raw = re.sub(r"```json\s*|\s*```", "", raw).strip()
        data = json.loads(raw)

        subtasks = []
        for st in data.get("subtasks", [])[:MAX_CHILDREN_PER_AGENT]:
            subtasks.append(SubTask(
                task_id     = st.get("task_id", f"t{len(subtasks)+1}"),
                title       = st.get("title", "Subtask"),
                description = st.get("description", task),
                depends_on  = st.get("depends_on", []),
            ))
        return subtasks if subtasks else [_single_subtask(task)]

    except Exception as e:
        # Graceful fallback: treat as single task
        return [_single_subtask(task)]


def _single_subtask(task: str) -> SubTask:
    return SubTask(task_id="t1", title="Main task", description=task)