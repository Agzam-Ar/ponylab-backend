import json
import base64
import math
import time
import traceback
from colorama import Fore
import httpx
import os
from dataclasses import dataclass
from openai import OpenAI

from data.yieldizer import GreenhouseState
from logic.rules import PlantParms, auto_type


LLM_BASE_URL = os.getenv("LLM_BASE_URL", "http://127.0.0.1:11435/v1")
LLM_API_KEY = os.getenv("LLM_API_KEY", "sk-no-key-required")
SKIP_AI = os.getenv("LLM_SKIP", False)


@dataclass
class AnalysisResult:
    growth_stage: str
    health: float
    disease: str
    recommended_params: PlantParms
    rationale: str


def encode_image(image_bytes: bytes) -> str:
    return base64.b64encode(image_bytes).decode("utf-8")


def log(*values: object):
    print(*values)


def calculate_vpd(temp: float, humidity: float):
    svp = 0.61078 * math.exp((17.27 * temp) / (temp + 237.3))
    avp = svp * (humidity / 100)
    return svp - avp


def analyze(image_bytes: bytes, state: GreenhouseState) -> AnalysisResult:
    from server.config import Config

    log(f"\n{Fore.LIGHTBLUE_EX}[Image -> LLM]{Fore.RESET}")

    SYSTEM_PROMPT = f"""Ты эксперт-агроном. Проанализируй фото растения.
    Верни СТРОГИЙ JSON без пояснений, в полях с числом используй одно число а не диапазон:
    {{
        "growth_stage": "стадия роста",
        "health": 0.0-1.0,
        "disease": "здоров/название болезни",
        {Config.rules.specification()},
        "rationale": "объяснение-план для себя, почему выбраны именно эти цифры (кратко)"
    }}
    """

    # Определение вектора тренда

    state20, time20 = Config.log.find_state(20 * 60)
    d_temp = state.values.temp_air - state20.values.temp_air
    d_hum = state.values.humidity_air - state20.values.humidity_air

    state3h, time3h = Config.log.find_state(60 * 60 * 3)
    d_ec = state.values.ec - state3h.values.ec
    d_ph = state.values.ph - state3h.values.ph

    vdp = calculate_vpd(state.values.temp_air, state.values.humidity_air)

    current_time_str = f"{state.time // 3600:02d}:{(state.time % 3600) // 60:02d}"
    light_start_time = "07:00"

    # Результат предыдущего промпта
    last_result = Config.log.last_result()

    user_prompt = f"""
    Текущее время и режим
    - Время в теплице: {current_time_str}
    - График: начало дня в {light_start_time}, длина определяется тобой

    Текущее состояние:
    - Температура: {state.values.temp_air}°C (Δ за {time20 // 60} мин: {d_temp:+.1f}°C)
    - Влажность: {state.values.humidity_air}% (Δ за {time20 // 60} мин: {d_hum:+.1f}%)
    - Раствор EC: {state.values.ec} (Δ за {time3h // 60} мин: {d_ec:+.2f})
    - pH: {state.values.ph} (Δ за {time3h // 60} мин: {d_ph:+.2f})
    - VPD: {vdp:.2f} kPa
    - CO2: {state.values.co2} ppm
    - Освещенность: {state.values.light} lux
    - Ошибки: {state.errors}  

    Предыдущая тактика:
    - Твое решение: {json.dumps(last_result.recommended_params, ensure_ascii=False) if last_result is not None else "<нет>"}
    - Твое обоснование: {last_result.rationale if last_result is not None else "<нет>"}.

    Задание
    - Проанализируй фото растения на предмет болезней и стадии роста
    - Если скоро рассвет/закат — подготовь климат заранее
    - Сравни текущие дельты с твоими прошлыми установками
    - Выдай обновленные параметры в JSON
    """

    if SKIP_AI:
        log(f"{Fore.LIGHTYELLOW_EX}Skipped with default values{Fore.RESET}")
        recommended_parms: PlantParms = {}
        for parm, rule in Config.rules.iter():
            if rule.value is not None:
                recommended_parms[parm] = rule.value

        return AnalysisResult(
            growth_stage="Бебебе",
            health=0.77,
            disease="Здоров",
            recommended_params=recommended_parms,
            rationale="Включи ИИ",
        )

    log(f"Сервер llm: {Fore.LIGHTCYAN_EX}{LLM_BASE_URL}{Fore.RESET}")
    client = OpenAI(
        base_url=LLM_BASE_URL, api_key=LLM_API_KEY, timeout=httpx.Timeout(None)
    )

    b64 = encode_image(image_bytes)
    # user_prompt = f"""Данные датчиков: {state.model_dump_json()}\nПроанализируй растение на фото."""
    log(f"=== Системный промпт ===\n{Fore.WHITE}{SYSTEM_PROMPT}{Fore.RESET}\n===")
    log(f"=== Промпт ===\n{Fore.WHITE}{user_prompt}{Fore.RESET}\n===")
    _start = time.perf_counter()
    response = client.chat.completions.create(
        model="local-model",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
                    },
                ],
            },
        ],
        response_format={"type": "json_object"},
        temperature=0,
    )
    log(
        f"{Fore.LIGHTGREEN_EX}Response ready!{Fore.RESET} ({int(time.perf_counter() - _start)}s)"
    )
    try:
        data = json.loads(response.choices[0].message.content or "")  # pyright: ignore[reportAny]
        log(
            f"=== Данные ===\n{Fore.LIGHTGREEN_EX}{json.dumps(data, indent=4, ensure_ascii=False)}{Fore.RESET}\n==="
        )
        parms: PlantParms = {}
        for parm, rule in Config.rules.iter():
            ai_parm = auto_type(data.get(f"recommended_{parm}", rule.value))  # pyright: ignore[reportAny]
            if ai_parm is not None:
                parms[parm] = ai_parm

        return AnalysisResult(
            growth_stage=str(data.get("growth_stage", "Не определено")),  # pyright: ignore[reportAny]
            health=float(data.get("health", 0.5)),  # pyright: ignore[reportAny]
            disease=data.get("disease", "healthy"),  # pyright: ignore[reportAny]
            recommended_params=parms,
            rationale=data.get("rationale", ""),  # pyright: ignore[reportAny]
        )
    except Exception as e:
        print(f"An error occurred: {e}")
        traceback.print_exc()
        raise RuntimeError(f"error: {e}")
