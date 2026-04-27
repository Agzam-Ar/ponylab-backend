import csv
import os
import json
from pathlib import Path
import trace
from typing import Any, Optional
from ai.analyze import AnalysisResult
import data
from data.models import Timer, TimerData, TableItem
from data.yieldizer import set_parameter, send_timers
import traceback

from logic.rules import PlantParms, PlantRules

PLANT_DATA_DIR = Path(__file__).parent.parent / "data" / "plants"


# Маппинг наших параметров на namespace/key в Yieldizer REST API
# Структура: param_name -> (namespace, key)
YIELDIZER_PARAM_MAP = {
    "temp": ("climate", "temp_target"),
    "humidity": ("climate", "humidity_target"),
    "ec": ("nsolution", "ec_target"),
    "ph": ("nsolution", "ph_target"),
}


class Controller:
    """
    Центральный логический модуль.

    Получает результат анализа AI, корректирует рекомендации
    по таблице допустимых значений и отправляет их в теплицу.
    """

    rules: PlantRules

    def __init__(self, rules: PlantRules):
        self.rules = rules
        self._last_params: dict[Any, Any] | None = None
        self._last_stage: str | None = None

    async def process(self, ai_result: AnalysisResult, current_sensors: dict) -> dict:
        stage = ai_result.growth_stage or "default"
        ai_params = ai_result.recommended_params

        print(f"[Controller] Stage: '{stage}'")
        print(f"[Controller] AI recommended: {ai_params}")

        # stage теперь только для логирования, clamp по единым границам CSV
        adjusted = self.rules.adjust_ai_params(ai_params)
        print(f"[Controller] Adjusted params: {adjusted}")

        await self._apply_params(adjusted)

        self._last_params = adjusted
        self._last_stage = stage
        return adjusted

    async def _apply_params(self, params: PlantParms) -> None:
        try:
            # Отправка расписания света на сервер
            # Свет имеет только режим m=3 (расписание)
            irrigation_delay = int(86400 / params.get("irrigation_pulses", 1))
            irrigation_sec = int(params.get("irrigation_sec", 1))
            if irrigation_sec > irrigation_delay:
                irrigation_delay = irrigation_sec + 1
            irrigation_delay = irrigation_delay - irrigation_sec

            _ = await send_timers(
                [
                    Timer(
                        m=3,
                        data=TimerData(
                            dbegin=0,
                            dskip=0,
                            table=[
                                TableItem(
                                    t1=25200,
                                    t2=int(params.get("light_duration", 16)) * 3600,
                                )
                            ],
                        ),
                    ),
                    Timer(
                        m=2,
                        data=TimerData(
                            t1=irrigation_sec,
                            t2=irrigation_delay,
                        ),
                    ),
                ]
            )
        except Exception:
            traceback.print_exc()

        # for param_name, value in params.items():
        #     if param_name not in YIELDIZER_PARAM_MAP:
        #         # light_duration не в MAP — это нормально, уже обработан выше
        #         if param_name != "light_duration":
        #             print(f"[Controller] Unknown param '{param_name}', skipping")
        #         continue
        #
        #     ns, key = YIELDIZER_PARAM_MAP[param_name]
        #     try:
        #         success = await set_parameter(ns, key, value)
        #         if success:
        #             print(f"[Controller] Set {ns}/{key} = {value} ✓")
        #         else:
        #             print(f"[Controller] Failed to set {ns}/{key} = {value}")
        #     except Exception as e:
        #         print(f"[Controller] Error setting {ns}/{key}: {e}")

    @staticmethod
    def _clamp_light(val: float) -> float:
        """light_duration: от 12 до 18 часов."""
        return max(12.0, min(18.0, float(val)))

    def get_last_params(self) -> Optional[dict]:
        return self._last_params

    def get_last_stage(self) -> Optional[str]:
        return self._last_stage
