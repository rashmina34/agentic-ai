# agents/v0_3_0/logger.py
import json
import uuid
from datetime import datetime
from .config import RUNS_LOG_PATH, CURRENT_VERSION

class RunLogger:
    def __init__(self):
        self.run_id  = str(uuid.uuid4())[:8]
        self.version = CURRENT_VERSION
        self.task    = ""
        self.steps   = 0
        self.children_spawned = 0
        self.outcome = "unknown"
        self.started = datetime.utcnow().isoformat()

    def start(self, task: str) -> str:
        self.task    = task
        self.started = datetime.utcnow().isoformat()
        return self.run_id

    def step(self):       self.steps += 1
    def spawned(self):    self.children_spawned += 1

    def finish(self, outcome: str, notes: str = ""):
        self.outcome = outcome
        record = {
            "run_id":           self.run_id,
            "version":          self.version,
            "task":             self.task[:200],
            "steps":            self.steps,
            "children_spawned": self.children_spawned,
            "outcome":          outcome,
            "notes":            notes[:300],
            "started":          self.started,
            "finished":         datetime.utcnow().isoformat(),
        }
        try:
            with open(RUNS_LOG_PATH, "a") as f:
                f.write(json.dumps(record) + "\n")
        except Exception as e:
            print(f"[LOGGER] Warning: {e}")