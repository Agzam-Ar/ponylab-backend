from __future__ import annotations
from pathlib import Path
import time

from pydantic import BaseModel

import data.yieldizer

from ai.analyze import AnalysisResult

LOGS_DIR = Path(__file__).parent.parent.parent / "data" / "logs"


class StateSnapshot(BaseModel):
    timestamp: int
    state: data.yieldizer.GreenhouseState


class ResultSnapshot(BaseModel):
    timestamp: int
    result: AnalysisResult


class PlantLog:
    def __init__(self):
        self.states: list[StateSnapshot] = []
        self.results: list[ResultSnapshot] = []
        LOGS_DIR.mkdir(parents=True, exist_ok=True)

    def now(self):
        return int(time.time())

    def results_str(self):
        return [
            f"[{r.timestamp % 86400 // 3600:02d}:{r.timestamp % 3600 // 60:02d}] {r.result.action_summary}"
            for r in self.results[-7:]
        ]

    def last_result(self):
        if len(self.results) == 0:
            return None
        return self.results[-1]

    def analysis_snapshot(self, result: AnalysisResult):
        self.results.append(ResultSnapshot(timestamp=self.now(), result=result))

    def state_snapshot(self, state: data.yieldizer.GreenhouseState):
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
