import asyncio
from contextlib import asynccontextmanager
import os
from shutil import ExecError

from fastapi import APIRouter, Form, HTTPException
from fastapi.responses import HTMLResponse, PlainTextResponse
from data.models import Config, State
from data.yieldizer import get, page
from logs.trace import error


try:
    with open("server/snapshots/state.json", "r", encoding="utf-8") as f:
        state = State.model_validate_json(f.read())
    with open("server/snapshots/cfg.json", "r", encoding="utf-8") as f:
        config = Config.model_validate_json(f.read())
except Exception as e:
    error(e)
    print(e)


FALLBACK_FILE = os.getenv("FALLBACK_FILE", "server/yieldizer.html")
SPEED_SCALE = 1000


def step():
    state.time = (state.time + 1) % 86400
    state.uptime += 1
    # TODO: other parms


def apply_cfg(cfg: Config):
    if cfg.clim:
        config.clim = cfg.clim
    if cfg.env:
        config.env = cfg.env
    if cfg.nsolution:
        config.nsolution = cfg.nsolution


@asynccontextmanager
async def proxy_lifespan(_router: APIRouter):
    task = asyncio.create_task(run_proxy_seconds())
    yield
    _ = task.cancel()


async def run_proxy_seconds():
    while True:
        try:
            await asyncio.sleep(1 / SPEED_SCALE)
            step()
        except asyncio.CancelledError:
            break
        except Exception as _:
            await asyncio.sleep(1)


proxy = APIRouter(lifespan=proxy_lifespan)  # Создайте роутер


@proxy.get("/ponylab")
async def proxy_ponylab():
    res = await page(0.25)
    print(f"/ponylab: {res}")
    if res is not None:
        return res

    if os.path.exists(FALLBACK_FILE):
        with open(FALLBACK_FILE, "r", encoding="utf-8") as f:
            stub_data = f.read()
        return HTMLResponse(content=stub_data, status_code=200)
    else:
        return PlainTextResponse("Yieldizer error (Stub missing)", status_code=500)


@proxy.get("/state")
async def proxy_state():
    res = await get("/state", 1)
    if res is not None:
        return res.json()  # pyright: ignore[reportAny]
    return state


@proxy.get("/cfg")
async def proxy_get_cfg():
    res = await get("/cfg", 1)
    if res is not None:
        return res.json()  # pyright: ignore[reportAny]
    return config


@proxy.post("/cfg")
async def proxy_post_cfg(jdata: str = Form(...)):
    try:
        cfg = Config.model_validate_json(jdata)
        apply_cfg(cfg)
        return {"text": "ok", "wrong_values": []}
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Ошибка: {e}")


print("Proxy endpoints loaded")


# Описываем логику старта и стопа секундного цикла для прокси


# Создаем роутер и передаем ему свой lifespan
router = APIRouter(lifespan=proxy_lifespan)
