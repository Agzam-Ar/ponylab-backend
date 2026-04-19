import csv
import os
import json
from pathlib import Path
from typing import Optional


PLANT_DATA_DIR = Path(__file__).parent.parent.parent / "data" / "plants"


class PlantRules:
    def __init__(self, plant_type: str = "tomato"):
        self.plant_type = plant_type
        self._table: dict = self._load_table(plant_type)

    def _load_table(self, plant_type: str) -> dict:
        path = PLANT_DATA_DIR / f"{plant_type}.csv"
        if not path.exists():
            return self._defaults()

        rules = {}
        with open(path) as f:
            reader = csv.DictReader(f)
            for row in reader:
                stage = row.get("stage", "default")
                rules[stage] = {
                    "temp_min": float(row.get("temp_min", 20)),
                    "temp_max": float(row.get("temp_max", 28)),
                    "humidity_min": float(row.get("humidity_min", 50)),
                    "humidity_max": float(row.get("humidity_max", 70)),
                    "ec_min": float(row.get("ec_min", 1.2)),
                    "ec_max": float(row.get("ec_max", 2.5)),
                    "ph_min": float(row.get("ph_min", 5.8)),
                    "ph_max": float(row.get("ph_max", 6.5)),
                }
        return rules

    def _defaults(self) -> dict:
        return {
            "default": {
                "temp_min": 20,
                "temp_max": 28,
                "humidity_min": 50,
                "humidity_max": 70,
                "ec_min": 1.2,
                "ec_max": 2.5,
                "ph_min": 5.8,
                "ph_max": 6.5,
            }
        }

    def get_bounds(self, stage: str = "default") -> dict:
        return self._table.get(
            stage, self._table.get("default", self._defaults()["default"])
        )

    def adjust_ai_params(self, ai_params: dict, stage: str = "default") -> dict:
        bounds = self.get_bounds(stage)

        adjusted = ai_params.copy()
        adjusted["temp"] = self._clamp(
            ai_params.get("temp", 25), bounds["temp_min"], bounds["temp_max"]
        )
        adjusted["humidity"] = self._clamp(
            ai_params.get("humidity", 60),
            bounds["humidity_min"],
            bounds["humidity_max"],
        )
        adjusted["ec"] = self._clamp(
            ai_params.get("ec", 1.8), bounds["ec_min"], bounds["ec_max"]
        )
        adjusted["ph"] = self._clamp(
            ai_params.get("ph", 6.0), bounds["ph_min"], bounds["ph_max"]
        )

        return adjusted

    def _clamp(self, val: float, min_val: float, max_val: float) -> float:
        return max(min_val, min(max_val, val))


class Controller:
    def __init__(self, plant_type: str = "tomato"):
        self.rules = PlantRules(plant_type)
        self._last_params: Optional[dict] = None

    async def process(self, ai_result, current_sensors: dict) -> dict:
        stage = ai_result.growth_stage
        ai_params = ai_result.recommended_params

        adjusted = self.rules.adjust_ai_params(ai_params, stage)

        self._last_params = adjusted
        return adjusted

    def get_last_params(self) -> Optional[dict]:
        return self._last_params
