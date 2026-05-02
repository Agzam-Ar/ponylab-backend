import os
import time
from typing import Any
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel

from data.models import Clim, Config, Env, NSolution, Timer

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


class SensorValues(BaseModel):
    ph: float
    ec: float
    temp_solution: float
    level: str
    temp_air: float
    humidity_air: float
    co2: int
    light: float


class GreenhouseState(BaseModel):
    values: SensorValues
    description: str
    uptime: int
    time: int
    wifi: int
    errors: list[str]


async def fetch_state() -> GreenhouseState:

    def fetch_value(values: list[Any], index: int, default: str | float):  # pyright: ignore[reportExplicitAny]
        if index < len(values) and "v" in values[index]:
            return values[index]["v"]  # pyright: ignore[reportAny]
        return default

    async with httpx.AsyncClient(timeout=10.0) as client:
        for base in URLS:
            for path in ["/state"]:
                url = f"{base}{path}" if base.endswith("/") else f"{base}{path}"
                try:
                    resp = await client.get(url)
                except Exception:
                    continue
                if resp.status_code == 200:
                    data = resp.json()  # pyright: ignore[reportAny]
                    v = data.get("values", [])  # pyright: ignore[reportAny]
                    state = GreenhouseState(
                        values=SensorValues(
                            ph=float(fetch_value(v, 0, 0.0)),  # pyright: ignore[reportAny]
                            ec=float(fetch_value(v, 1, 0.0)),  # pyright: ignore[reportAny]
                            temp_solution=float(fetch_value(v, 2, 0.0)),  # pyright: ignore[reportAny]
                            level=str(fetch_value(v, 3, "none")),  # pyright: ignore[reportAny]
                            temp_air=float(fetch_value(v, 4, 0.0)),  # pyright: ignore[reportAny]
                            humidity_air=v[5]["v"] if len(v) > 5 else 0.0,  # pyright: ignore[reportAny]
                            co2=int(fetch_value(v, 5, 0)),  # pyright: ignore[reportAny]
                            light=float(fetch_value(v, 6, 0.0)),  # pyright: ignore[reportAny]
                        ),
                        description=data.get("description", ""),  # pyright: ignore[reportAny]
                        uptime=data.get("uptime", 0),  # pyright: ignore[reportAny]
                        time=data.get("time", 0),  # pyright: ignore[reportAny]
                        wifi=data.get("wifi", 0),  # pyright: ignore[reportAny]
                        errors=data.get("errors", []),  # pyright: ignore[reportAny]
                    )
                    return state
                else:
                    continue
    # raise ConnectionError(f"Cannot reach Yieldizer at {BASE_URL}")
    return GreenhouseState(
        values=SensorValues(
            ph=6,
            ec=1,
            temp_solution=1,
            level="meow",
            temp_air=25,
            humidity_air=50,
            co2=2,
            light=10,
        ),
        description="",
        uptime=123,
        time=int(time.time() * 180) % (86400),  # 1 минута = 3 часа
        wifi=1,
        errors=[],
    )


async def send_nsolution(nsolution: NSolution):
    return await post(
        "/cfg", Config(nsolution=nsolution).model_dump_json(exclude_none=True)
    )


async def send_climate(clim: Clim):
    return await post("/cfg", Config(clim=clim).model_dump_json(exclude_none=True))


async def send_timers(timers: list[Timer]):
    return await post(
        "/cfg", Config(env=Env(timers=timers)).model_dump_json(exclude_none=True)
    )


async def post(path: str, body: str) -> bool:
    async with httpx.AsyncClient(timeout=30.0) as client:
        form_data = {"jdata": body}
        for base in URLS:
            try:
                url = f"{base}{path}" if base.endswith("/") else f"{base}{path}"
                resp = await client.post(url, data=form_data)
                if resp.status_code == 200:
                    return resp.text == "ok"
                print(f"POST on {url} with {body}")
                print(f"Response: {resp.status_code} {resp.text}")
            except Exception as e:
                print(f"Error: {e}")
                continue
    return False


async def send_command(command: dict) -> bool:
    async with httpx.AsyncClient(timeout=30.0) as client:
        for base in URLS:
            for path in ["/cmd", "/api/cmd"]:
                try:
                    url = f"{base}{path}" if base.endswith("/") else f"{base}{path}"
                    print(f"POST on {url} with {command}")
                    resp = await client.post(url, json=command)
                    if resp.status_code == 200:
                        return resp.text == "ok"
                except Exception as e:
                    print(f"Error: {e}")
                    continue
    return False
