# agents/v0_3_0/message_bus.py
"""
Lightweight in-process message bus for agent communication.

Design:
- Every agent has a unique agent_id
- Messages are dataclasses (typed, inspectable)
- Parent posts tasks → children post results back
- No shared mutable state between agents (pure message passing)
- Thread-safe via threading.Lock
"""

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional


class MessageType(str, Enum):
    TASK        = "task"        # parent → child: here's your subtask
    RESULT      = "result"      # child → parent: here's my result
    ERROR       = "error"       # child → parent: I failed, here's why
    STATUS      = "status"      # any → any: progress update
    SPAWN       = "spawn"       # agent → bus: I want to spawn a child


@dataclass
class AgentMessage:
    msg_id:    str         = field(default_factory=lambda: str(uuid.uuid4())[:8])
    msg_type:  MessageType = MessageType.STATUS
    sender_id: str         = ""
    target_id: str         = ""        # "" = broadcast
    content:   Any         = None
    metadata:  dict        = field(default_factory=dict)
    timestamp: str         = field(default_factory=lambda: datetime.utcnow().isoformat())

    def __str__(self):
        preview = str(self.content)[:80] + ("..." if len(str(self.content)) > 80 else "")
        return f"[{self.msg_type}] {self.sender_id}→{self.target_id or 'all'}: {preview}"


class MessageBus:
    """
    Central message bus. All agents share one bus instance per run.

    Usage:
        bus = MessageBus()
        bus.post(AgentMessage(msg_type=MessageType.TASK, ...))
        msgs = bus.poll(agent_id="child-1")
    """

    def __init__(self):
        self._lock    = threading.Lock()
        self._history: list[AgentMessage] = []
        self._queues:  dict[str, list[AgentMessage]] = {}

    def register(self, agent_id: str) -> None:
        with self._lock:
            if agent_id not in self._queues:
                self._queues[agent_id] = []

    def post(self, msg: AgentMessage) -> None:
        """Post a message. Delivers to target or all registered agents."""
        with self._lock:
            self._history.append(msg)
            if msg.target_id and msg.target_id in self._queues:
                self._queues[msg.target_id].append(msg)
            elif not msg.target_id:
                for q in self._queues.values():
                    q.append(msg)

    def poll(self, agent_id: str) -> list[AgentMessage]:
        """Drain all pending messages for an agent."""
        with self._lock:
            msgs = list(self._queues.get(agent_id, []))
            self._queues[agent_id] = []
            return msgs

    def history(self) -> list[AgentMessage]:
        with self._lock:
            return list(self._history)

    def summary(self) -> str:
        """Human-readable bus activity summary."""
        with self._lock:
            lines = [f"MessageBus: {len(self._history)} total messages"]
            for msg in self._history[-10:]:
                lines.append(f"  {msg}")
            return "\n".join(lines)