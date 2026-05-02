from cProfile import label
import json
from datetime import datetime
from operator import le
from pathlib import Path
from dataclasses import dataclass, asdict
from sqlite3.dbapi2 import Timestamp
import this
import time

from pydantic import BaseModel

from ai.analyze import AnalysisResult
from data.yieldizer import GreenhouseState


LOGS_DIR = Path(__file__).parent.parent.parent / "data" / "logs"


class PlantEvent(BaseModel):
    timestamp: str
    event_type: str
    details: dict


class StateSnapshot(BaseModel):
    timestamp: int
    state: GreenhouseState


class PlantLog:
    def __init__(self):
        self.states: list[StateSnapshot] = []
        self.results: list[AnalysisResult] = []
        # self.plant_id = plant_id
        self.log_file = LOGS_DIR / "log.json"
        LOGS_DIR.mkdir(parents=True, exist_ok=True)

    def now(self):
        return int(time.time())

    # def log_ai_analysis(self, result):
    #     self._add_event("ai_analysis", asdict(result))
    #
    # def _add_event(self, event_type: str, details: dict):
    #     event = PlantEvent(
    #         timestamp=
    #         event_type=event_type,
    #         details=details,
    #     )
    #
    #     events = self._load()
    #     events.append(asdict(event))
    #
    #     with open(self.log_file, "w") as f:
    #         json.dump(events, f, indent=2)
    #
    # def _load(self) -> list:
    #     if not self.log_file.exists():
    #         return []
    #     with open(self.log_file) as f:
    #         return json.load(f)

    # def get_history(self, limit: int = 100) -> list:
    #     events = self._load()
    #     return events[-limit:]
    def last_result(self):
        if len(self.results) == 0:
            return None
        return self.results[-1]

    def analysis_snapshot(self, result: AnalysisResult):
        self.results.append(result)

    def state_snapshot(self, state: GreenhouseState):
        self.states.append(StateSnapshot(timestamp=self.now(), state=state))

    def find_state(self, ago: int):
        target = self.now() - ago
        best = self.states[-1]
        diff = abs(target - best.timestamp)
        for state in self.states:
            d = abs(target - state.timestamp)
            if d >= diff:
                continue
            diff = d
            best = state
        return best.state, int(self.now() - best.timestamp)
