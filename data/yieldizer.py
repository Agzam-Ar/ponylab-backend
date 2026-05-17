import os
from typing import Any
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel

from data.models import Clim, Config, Env, NSolution, State, Timer

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
    co2: float
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

    def from_api(_state: State):
        v = _state.values
        return GreenhouseState(
            values=SensorValues(
                ph=float(fetch_value(v, 0, 0.0)),
                ec=float(fetch_value(v, 1, 0.0)),
                temp_solution=float(fetch_value(v, 2, 0.0)),
                level=str(fetch_value(v, 3, "none")),
                temp_air=float(fetch_value(v, 4, 0.0)),
                humidity_air=float(fetch_value(v, 5, 0.0)),
                co2=float(fetch_value(v, 6, 0.0)),
                light=float(fetch_value(v, 7, 0.0)),
            ),
            description=_state.description,
            uptime=_state.uptime,
            time=_state.time,
            wifi=_state.wifi,
            errors=_state.errors or [],
        )

    async with httpx.AsyncClient(timeout=10.0) as client:
        for base in URLS:
            for path in ["/state"]:
                url = f"{base}{path}" if base.endswith("/") else f"{base}{path}"
                try:
                    resp = await client.get(url)
                except Exception:
                    continue
                if resp.status_code == 200:
                    _state = State.model_validate_json(resp.text)
                    return from_api(_state)
                else:
                    continue
    # raise ConnectionError(f"Cannot reach Yieldizer at {BASE_URL}")
    from server.proxy import state

    return from_api(state)


async def get(url: str = "/", timeout: float = 1.0):
    async with httpx.AsyncClient(timeout=timeout) as client:
        for base in URLS:
            try:
                return await client.get(f"{base}{url}")
            except Exception:
                continue


async def page(timeout: float):
    async with httpx.AsyncClient(timeout=timeout) as client:
        for base in URLS:
            try:
                return await client.get(f"{base}/")
            except Exception:
                continue


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
                # print(body)
                continue
    return False
