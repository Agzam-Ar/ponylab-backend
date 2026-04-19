import httpx
import os
import re
from dataclasses import dataclass
from urllib.parse import urlparse


BASE_URL = os.getenv("YIELDIZER_URL", "http://127.0.0.1:3001")


def _get_urls(base_url: str) -> list[str]:
    parsed = urlparse(base_url)
    host = parsed.hostname
    port = parsed.port or 80

    urls = [base_url]

    if host == "127.0.0.1" or host == "localhost":
        if ":" not in host:
            urls.append(f"http://[::1]:{port}{parsed.path or ''}")

    return urls


URLS = _get_urls(BASE_URL)


@dataclass
class SensorValues:
    ph: float
    ec: float
    temp_solution: float
    level: str
    temp_air: float
    humidity_air: float
    co2: int
    light: float


@dataclass
class GreenhouseState:
    values: SensorValues
    description: str
    uptime: int
    wifi: int
    errors: list


async def fetch_state() -> GreenhouseState:
    async with httpx.AsyncClient(timeout=10.0) as client:
        for base in URLS:
            for path in ["/state", "/api/state"]:
                try:
                    url = f"{base}{path}" if base.endswith("/") else f"{base}{path}"
                    resp = await client.get(url)
                    if resp.status_code == 200:
                        data = resp.json()
                        # print(f"Data: {data}")
                        v = data.get("values", [])
                        return GreenhouseState(
                            values=SensorValues(
                                ph=v[0]["v"] if len(v) > 0 else 0.0,
                                ec=v[1]["v"] if len(v) > 1 else 0.0,
                                temp_solution=v[2]["v"] if len(v) > 2 else 0.0,
                                level=str(v[3]["v"]) if len(v) > 3 else "unknown",
                                temp_air=v[4]["v"] if len(v) > 4 else 0.0,
                                humidity_air=v[5]["v"] if len(v) > 5 else 0.0,
                                co2=v[6]["v"] if len(v) > 6 else 0,
                                light=v[7]["v"] if len(v) > 7 else 0.0,
                            ),
                            description=data.get("description", ""),
                            uptime=data.get("uptime", 0),
                            wifi=data.get("wifi", 0),
                            errors=data.get("errors", []),
                        )
                except Exception:
                    continue
    raise ConnectionError(f"Cannot reach Yieldizer at {BASE_URL}")


async def send_command(command: dict) -> bool:
    async with httpx.AsyncClient(timeout=30.0) as client:
        for base in URLS:
            for path in ["/cmd", "/api/cmd"]:
                try:
                    url = f"{base}{path}" if base.endswith("/") else f"{base}{path}"
                    resp = await client.post(url, json=command)
                    if resp.status_code == 200:
                        return resp.text == "ok"
                except Exception:
                    continue
    return False


async def set_parameter(ns: str, key: str, value) -> bool:
    return await send_command({"type": "set", "ns": ns, "key": key, "value": value})


async def set_climate(param: str, value: dict) -> bool:
    return await send_command({"type": "set_climate", "param": param, **value})
