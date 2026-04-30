import json
import base64
import time
from colorama import Fore
import httpx
import os
from dataclasses import dataclass
from openai import OpenAI

from data.yieldizer import GreenhouseState
from logic.rules import PlantParms, auto_type
from server.config import Config


LLM_BASE_URL = os.getenv("LLM_BASE_URL", "http://127.0.0.1:11435/v1")
LLM_API_KEY = os.getenv("LLM_API_KEY", "sk-no-key-required")
SKIP_AI = os.getenv("LLM_SKIP", False)


@dataclass
class AnalysisResult:
    growth_stage: str
    health: float
    disease: str
    recommended_params: PlantParms


SYSTEM_PROMPT = f"""Ты эксперт-агроном. Проанализируй фото растения.
Верни СТРОГИЙ JSON без пояснений, в полях с числом используй одно число а не диапазон:
{{
    "growth_stage": "стадия роста",
    "health": 0.0-1.0,
    "disease": "здоров/название болезни",
    {Config.rules.specification()},
    "rationale": "объяснение, почему выбраны именно эти цифры (кратко)"
}}
"""

print(f"[Analyze] SYSTEM_PROMPT: {SYSTEM_PROMPT}")


def encode_image(image_bytes: bytes) -> str:
    return base64.b64encode(image_bytes).decode("utf-8")


def log(*values: object):
    print(*values)


def analyze(image_bytes: bytes, state: GreenhouseState) -> AnalysisResult:
    log(f"\n{Fore.LIGHTBLUE_EX}[Image -> LLM]{Fore.RESET}")
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
        )

    log(f"Сервер llm: {Fore.LIGHTCYAN_EX}{LLM_BASE_URL}{Fore.RESET}")
    client = OpenAI(
        base_url=LLM_BASE_URL, api_key=LLM_API_KEY, timeout=httpx.Timeout(None)
    )

    b64 = encode_image(image_bytes)
    user_prompt = f"""Данные датчиков: {state.model_dump_json()}\nПроанализируй растение на фото."""
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
        )
    except Exception as e:
        print(f"An error occurred: {e}")
        raise RuntimeError(f"error: {e}")
