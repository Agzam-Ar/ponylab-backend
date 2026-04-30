import json
import base64
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
    "recommended_temp": 20-30,
    "recommended_humidity": 40-80,
    "recommended_ec": 1.0-3.0,
    "recommended_ph": 5.5-6.5,
    "light_duration": 12-18
}}
"""

print(f"[Analyze] SYSTEM_PROMPT: {SYSTEM_PROMPT}")


def encode_image(image_bytes: bytes) -> str:
    return base64.b64encode(image_bytes).decode("utf-8")


def analyze(image_bytes: bytes, state: GreenhouseState) -> AnalysisResult:
    if SKIP_AI:
        print("[analyze] Warning: AI skip")
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
    print(f"Prompt to {LLM_BASE_URL}")
    client = OpenAI(
        base_url=LLM_BASE_URL, api_key=LLM_API_KEY, timeout=httpx.Timeout(120000.0)
    )

    b64 = encode_image(image_bytes)
    user_prompt = (
        f"""Данные датчиков: {json.dumps(state)}\nПроанализируй растение на фото."""
    )
    print(f"Prompt: {user_prompt}")
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
    print("response ready!")
    try:
        print(f"{response.choices}")
        data = json.loads(response.choices[0].message.content or "")
        print(f"Result: {data}")
        parms: PlantParms = {}
        for parm, rule in Config.rules.iter():
            ai_parm = auto_type(f"{data.get(f'recommended_{parm}', rule.value)}")
            if ai_parm is not None:
                parms[parm] = ai_parm
        return AnalysisResult(
            growth_stage=data.get("growth_stage", "Не определено"),
            health=float(data.get("health", 0.5)),
            disease=data.get("disease", "healthy"),
            recommended_params=parms,
        )
    except Exception as e:
        print(f"An error occurred: {e}")
        raise RuntimeError(f"error: {e}")
