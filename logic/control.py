import csv
import os
import json
from pathlib import Path
import trace
from typing import Any, Optional
from ai.analyze import AnalysisResult
import data
from data.models import Clim, ClimateControl, Timer, TimerData, TableItem
from data.yieldizer import fetch_state, send_climate, set_parameter, send_timers
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
        state = await fetch_state()

        # Световой день
        light_begin = 25200
        light_end = int(params.get("light_duration", 16)) * 3600
        is_day = light_begin <= state.time <= light_end
        print(f"[Controller] Is day: {is_day}")

        try:
            # Отправка расписания света и полива на сервер
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
                            table=[TableItem(t1=light_begin, t2=light_end)],
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

        try:
            # Отправка настроек климата на сервер
            # Yieldizer дает настроить только на общую логику,
            # поэтому ручное определение день/ночь
            temp_day = int(params.get("temp_day", 25))
            temp_night = int(params.get("temp_night", 20))
            temp_target = temp_day if is_day else temp_night
            temp_margin = 2

            _ = await send_climate(
                Clim(
                    air_cooler=ClimateControl(
                        thr_on=temp_target + temp_margin,
                        thr_off=temp_target - temp_margin,
                        t_on_min=3,
                        t_on_max=30,
                        t_pause=5,
                    ),
                    heater=ClimateControl(
                        thr_on=temp_target - temp_margin,
                        thr_off=temp_target + temp_margin,
                        t_on_min=1,
                        t_on_max=20,
                        t_pause=2,
                    ),
                    extractor_t=ClimateControl(
                        thr_on=temp_target + temp_margin,
                        thr_off=temp_target - temp_margin,
                        t_on_min=3,
                        t_on_max=30,
                        t_pause=5,
                    ),
                    # TODO: Remove placeholders
                    # Увлажнитель
                    humidifier=ClimateControl(
                        thr_on=50, thr_off=55, t_on_min=0.5, t_on_max=10, t_pause=0.5
                    ),
                    # Осушитель
                    dehumidifier=ClimateControl(
                        thr_on=70, thr_off=60, t_on_min=6, t_on_max=60, t_pause=3
                    ),
                    extractor_h=ClimateControl(
                        thr_on=60, thr_off=55, t_on_min=0.5, t_on_max=10, t_pause=0.5
                    ),
                    co2=ClimateControl(
                        thr_on=1100,
                        thr_off=1200,
                        t_on_min=3,
                        t_on_max=10,
                        t_pause=0,
                    ),
                )
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
