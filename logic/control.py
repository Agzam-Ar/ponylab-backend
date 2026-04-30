import traceback
from pathlib import Path
from colorama import Fore

from ai.analyze import AnalysisResult
from data.models import Clim, ClimateControl, TableItem, Timer, TimerData
from data.yieldizer import (
    GreenhouseState,
    send_climate,
    send_timers,
)
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


def log(*values: object):
    print(*values)


class Controller:
    """
    Центральный логический модуль.

    Получает результат анализа AI, корректирует рекомендации
    по таблице допустимых значений и отправляет их в теплицу.
    """

    rules: PlantRules

    def __init__(self, rules: PlantRules):
        self.rules = rules
        self._last_params: PlantParms | None = None
        self._last_stage: str | None = None

    async def process(self, ai_result: AnalysisResult, state: GreenhouseState):
        stage = ai_result.growth_stage or "default"
        ai_params = ai_result.recommended_params

        # stage теперь только для логирования, clamp по единым границам CSV
        adjusted = self.rules.adjust_ai_params(ai_params)

        await self._apply_params(adjusted, state)

        self._last_params = adjusted
        self._last_stage = stage
        return adjusted

    async def _apply_params(self, params: PlantParms, state: GreenhouseState) -> None:
        log(f"\n{Fore.GREEN}[Controller -> Yieldizer]{Fore.RESET}")
        # Световой день
        light_begin = 25200
        light_end = light_begin + int(params.get("light_duration", 16)) * 3600
        is_day = light_begin <= state.time <= light_end

        # Отладочный timeline
        _bars = 24 * 2
        _bar_scl = 86400 // _bars
        _bar = ["─"] * _bars
        _bar[state.time // _bar_scl] = (
            Fore.LIGHTYELLOW_EX if is_day else Fore.LIGHTBLACK_EX
        ) + "⬤"
        _bar[light_begin // _bar_scl - 1] += Fore.LIGHTYELLOW_EX
        _bar[light_end // _bar_scl - 1] += Fore.LIGHTBLACK_EX

        print(
            f"Цикл:  {Fore.LIGHTBLACK_EX}{''.join(_bar)} {Fore.RESET}{state.time // 3600:02}:{state.time // 60 % 60:02}"
        )

        try:
            # Отправка расписания света и полива на сервер
            # Свет имеет только режим m=3 (расписание)
            irrigation_pulses = int(params.get("irrigation_pulses", 1))
            irrigation_delay = int(86400 / irrigation_pulses)
            irrigation_sec = int(params.get("irrigation_sec", 1))
            if irrigation_sec > irrigation_delay:
                irrigation_delay = irrigation_sec + 1
            irrigation_delay = irrigation_delay - irrigation_sec

            _bar = [" "] * _bars
            for i in range(irrigation_pulses):
                _bar[i * (irrigation_sec + irrigation_delay) // _bar_scl] = (
                    Fore.LIGHTBLUE_EX + "∴" + Fore.RESET
                )

            log(f"Полив: {''.join(_bar)}\n")
            log(
                f"Полив: {Fore.LIGHTBLUE_EX}{irrigation_sec}{Fore.RESET} секунд с перерывом в {Fore.LIGHTBLUE_EX}{irrigation_delay // 60}{Fore.RESET} минут"
            )

            _ = await send_timers(
                [
                    Timer(
                        m=3,
                        data=TimerData(
                            dbegin=0,
                            dskip=0,
                            table=[
                                TableItem(t1=light_begin, t2=light_end - light_begin)
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

        try:
            # Отправка настроек климата на сервер
            # Yieldizer дает настроить только на общую логику,
            # поэтому ручное определение день/ночь

            temp_day = int(params.get("temp_day", 25))
            temp_night = int(params.get("temp_night", 20))
            temp_target = temp_day if is_day else temp_night
            temp_margin = 2

            humidity_day = int(params.get("humidity_day", 65))
            humidity_night = int(params.get("humidity_night", 60))
            humidity_target = humidity_day if is_day else humidity_night
            humidity_margin = 2

            co2_target = int(params.get("co2_target", 1200)) if is_day else 0
            co2_margin = 100

            log(
                f"Температура: {Fore.LIGHTGREEN_EX}{temp_target}°C{Fore.RESET}\nВлажность: {Fore.LIGHTGREEN_EX}{humidity_target}%{Fore.RESET}\nCO2: {Fore.LIGHTGREEN_EX}{co2_target} ppm{Fore.RESET}"
            )

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
                    # Вытяжка (температура)
                    extractor_t=ClimateControl(
                        thr_on=temp_target + temp_margin,
                        thr_off=temp_target - temp_margin,
                        t_on_min=3,
                        t_on_max=30,
                        t_pause=5,
                    ),
                    # Увлажнитель
                    humidifier=ClimateControl(
                        thr_on=humidity_target - humidity_margin,
                        thr_off=humidity_target + humidity_margin,
                        t_on_min=0.5,
                        t_on_max=10,
                        t_pause=0.5,
                    ),
                    # Осушитель
                    dehumidifier=ClimateControl(
                        thr_on=humidity_target + humidity_margin,
                        thr_off=humidity_target - humidity_margin,
                        t_on_min=6,
                        t_on_max=60,
                        t_pause=3,
                    ),
                    # Вытяжка (влажность)
                    extractor_h=ClimateControl(
                        thr_on=humidity_target + humidity_margin,
                        thr_off=humidity_target - humidity_margin,
                        t_on_min=0.5,
                        t_on_max=10,
                        t_pause=0.5,
                    ),
                    co2=ClimateControl(
                        thr_on=co2_target - co2_margin if is_day else 0,
                        thr_off=co2_target + co2_margin if is_day else 1,
                        t_on_min=3,
                        t_on_max=10,
                        t_pause=3,
                    ),
                )
            )
        except Exception:
            traceback.print_exc()

    @staticmethod
    def _clamp_light(val: float) -> float:
        """light_duration: от 12 до 18 часов."""
        return max(12.0, min(18.0, float(val)))

    def get_last_params(self):
        return self._last_params

    def get_last_stage(self):
        return self._last_stage
