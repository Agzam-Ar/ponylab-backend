import json
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, asdict


LOGS_DIR = Path(__file__).parent.parent.parent / "data" / "logs"


@dataclass
class PlantEvent:
    timestamp: str
    event_type: str
    details: dict


class PlantLog:
    def __init__(self, plant_id: str):
        self.plant_id = plant_id
        self.log_file = LOGS_DIR / f"{plant_id}.json"
        self._ensure_dir()

    def _ensure_dir(self):
        LOGS_DIR.mkdir(parents=True, exist_ok=True)

    def log_planted(self, plant_type: str, variety: str = ""):
        self._add_event(
            "planted",
            {
                "plant_type": plant_type,
                "variety": variety,
            },
        )

    def log_sensor_change(self, sensor: str, old_val, new_val):
        self._add_event(
            "sensor_change",
            {
                "sensor": sensor,
                "old": old_val,
                "new": new_val,
            },
        )

    def log_ai_analysis(self, result):
        self._add_event("ai_analysis", asdict(result))

    def _add_event(self, event_type: str, details: dict):
        event = PlantEvent(
            timestamp=datetime.now().isoformat(),
            event_type=event_type,
            details=details,
        )

        events = self._load()
        events.append(asdict(event))

        with open(self.log_file, "w") as f:
            json.dump(events, f, indent=2)

    def _load(self) -> list:
        if not self.log_file.exists():
            return []
        with open(self.log_file) as f:
            return json.load(f)

    def get_history(self, limit: int = 100) -> list:
        events = self._load()
        return events[-limit:]
