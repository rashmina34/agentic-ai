# agents/v0_2_0/context.py
"""
Sliding-window context manager.

Strategy:
  - Always keep: system prompt (handled by caller) + first user message
  - Keep last CONTEXT_WINDOW_PAIRS user/assistant pairs verbatim
  - Summarize any pairs that fall outside the window into a single
    compressed message injected just after the first user message

This prevents unbounded context growth while preserving recent reasoning.
"""

from .config import CONTEXT_WINDOW_PAIRS


class ContextManager:
    """
    Wraps a raw message list and returns a windowed view safe to send to the API.

    Usage:
        ctx = ContextManager()
        ctx.add("user", "hello")
        ctx.add("assistant", "hi!")
        windowed = ctx.get_windowed()   # pass to API
    """

    def __init__(self):
        self.messages: list[dict] = []      # full history
        self._summary: str = ""             # compressed older context

    def add(self, role: str, content: str) -> None:
        self.messages.append({"role": role, "content": content})

    def set_summary(self, summary: str) -> None:
        """Inject a summary of dropped messages."""
        self._summary = summary

    def get_windowed(self) -> list[dict]:
        """
        Return the windowed message list to send to the API.

        Structure:
          [first_user_msg]
          [summary_msg if exists]
          [...last CONTEXT_WINDOW_PAIRS*2 messages]
        """
        if not self.messages:
            return []

        # Always include first message
        first = self.messages[:1]

        # Sliding window of recent messages
        window_size = CONTEXT_WINDOW_PAIRS * 2   # pairs → individual messages
        recent = self.messages[-window_size:] if len(self.messages) > window_size else self.messages[1:]

        # Check if we dropped anything
        dropped_count = max(0, len(self.messages) - 1 - len(recent))

        result = list(first)

        if dropped_count > 0 and self._summary:
            result.append({
                "role": "user",
                "content": (
                    f"[CONTEXT SUMMARY — {dropped_count} earlier messages compressed]\n"
                    f"{self._summary}"
                )
            })
            result.append({
                "role": "assistant",
                "content": "Understood, I have the context summary. Continuing."
            })

        result.extend(recent)
        return result

    def needs_summarization(self) -> bool:
        """True when we have more messages than the window can hold."""
        return len(self.messages) > (CONTEXT_WINDOW_PAIRS * 2 + 1)

    def get_messages_to_summarize(self) -> list[dict]:
        """Return the overflow messages that should be summarized."""
        window_size = CONTEXT_WINDOW_PAIRS * 2
        cutoff = max(1, len(self.messages) - window_size)
        return self.messages[1:cutoff]   # exclude first message

    def __len__(self) -> int:
        return len(self.messages)