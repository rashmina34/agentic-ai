# agents/v0_2_0/logger.py
"""
Experiment run logger.

Appends one JSON line per run to runs.jsonl.
Each line records: run_id, version, task, steps, outcome, timestamp.
Useful for tracking self-improvement progress over time.
"""

import json
import uuid
from datetime import datetime
from typing import Optional

from .config import RUNS_LOG_PATH, CURRENT_VERSION


class RunLogger:
    def __init__(self):
        self.run_id   = str(uuid.uuid4())[:8]
        self.version  = CURRENT_VERSION
        self.task     = ""
        self.steps    = 0
        self.outcome  = "unknown"
        self.notes    = ""
        self.started  = datetime.utcnow().isoformat()

    def start(self, task: str) -> str:
        self.task    = task
        self.started = datetime.utcnow().isoformat()
        return self.run_id

    def step(self) -> None:
        self.steps += 1

    def finish(self, outcome: str, notes: str = "") -> None:
        self.outcome = outcome
        self.notes   = notes
        self._write()

    def _write(self) -> None:
        record = {
            "run_id"  : self.run_id,
            "version" : self.version,
            "task"    : self.task[:200],
            "steps"   : self.steps,
            "outcome" : self.outcome,
            "notes"   : self.notes[:500],
            "started" : self.started,
            "finished": datetime.utcnow().isoformat(),
        }
        try:
            with open(RUNS_LOG_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(record) + "\n")
        except Exception as e:
            print(f"[LOGGER] Warning: could not write run log: {e}")