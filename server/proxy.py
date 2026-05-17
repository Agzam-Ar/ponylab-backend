import asyncio
from contextlib import asynccontextmanager
from enum import Enum
import os
from typing import Callable

from fastapi import APIRouter, Form, HTTPException
from fastapi.responses import HTMLResponse, PlainTextResponse
from pydantic import BaseModel
from data.models import Clim, ClimateControl, Config, Sensors, State
from data.yieldizer import get, page
from logs import trace
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
SPEED_SCALE = 1


class ClimateController(BaseModel):
    """Enum для outsfn из Config"""

    index: int
    control: Callable[[Clim], ClimateControl]
    sensor: Sensors
    delta: float | dict[Sensors, float]

    def step(self, clim: Clim, state: State, out: int):
        c = self.control(clim)
        value = self.sensor.from_state(state)
        if c.under(value):  # Под диапозоном - включаем
            state.outs.sum_on_s[out] = c.t_on_min * 60
            # state.outs.func_cntdn_s[out] = c.t_on_min * 60

        if state.outs.sum_on_s[out] > 0:  # Если включен
            if isinstance(self.delta, float):
                sv = state.values[self.sensor.value]
                if sv.v:
                    sv.v += self.delta * 10
            if isinstance(self.delta, dict):
                for sensor, d in self.delta.items():
                    sv = state.values[sensor.value]
                    if sv.v:
                        sv.v += d * 10


class OutFunc(Enum):
    OFF = 254
    ON = 255
    PH_DOWN = 0
    PH_UP = 1
    FERTILIZER_A = 2  # удобрение А
    FERTILIZER_B = 3  # удобрение B
    FERTILIZER_C = 4  # удобрение С
    WATER_REFILL = 5  # долив воды
    CHILLER = 6  # чиллер
    AIR_CONDITIONER = ClimateController(
        index=7,
        control=lambda c: c.air_cooler,
        sensor=Sensors.TEMP_AIR,
        delta={
            Sensors.TEMP_AIR: -0.04,  # кондиционер эффективно охлаждает
            Sensors.HUMIDITY_AIR: -0.01,  # кондиционер побочно сушит воздух
        },
    )  # кондиционер
    DEHUMIDIFIER = ClimateController(
        index=8,
        control=lambda c: c.dehumidifier,
        sensor=Sensors.HUMIDITY_AIR,
        delta={
            Sensors.HUMIDITY_AIR: -0.04,  # осушает воздух (-2.4% в минуту)
            Sensors.TEMP_AIR: 0.008,  # побочный нагрев от компрессора
        },
    )  # осушитель
    EXHAUST_FAN = ClimateController(
        index=9,
        control=lambda c: (
            c.extractor_h
        ),  # управляется логикой вытяжки по влажности (или c.extractor_t)
        sensor=Sensors.HUMIDITY_AIR,
        delta={
            Sensors.HUMIDITY_AIR: -0.2,  # стремительно вытягивает влагу (зависит от улицы, берем среднее падение)
            Sensors.TEMP_AIR: -0.05,  # выдувает тепло наружу
            Sensors.CO2: -2.0,  # быстро сбрасывает CO2 до уличных значений
        },
    )  # вытяжка
    HUMIDIFIER = ClimateController(
        index=10,
        control=lambda c: c.humidifier,
        sensor=Sensors.HUMIDITY_AIR,
        delta=0.04,  # увлажняет на +2.4% в минуту
    )  # увлажнитель

    HEATER = ClimateController(
        index=11,
        control=lambda c: c.heater,
        sensor=Sensors.TEMP_AIR,
        delta={
            Sensors.TEMP_AIR: 0.02,  # нагрев воздуха на +1.2°C в минуту
            Sensors.HUMIDITY_AIR: -0.01,  # физическое падение относительной влажности при нагреве
        },
    )  # обогреватель
    CO2_VALVE = ClimateController(
        index=12,
        control=lambda c: c.co2,
        sensor=Sensors.CO2,
        delta=1.5,  # подача газа повышает уровень на +1.5 ppm в секунду
    )  # клапан CO2
    LIGHT = 13  # свет
    WATERING = 14  # полив
    TIMER_1 = 15  # таймер 1
    TIMER_2 = 16  # таймер 2
    TIMER_3 = 17  # таймер 3
    TIMER_4 = 18  # таймер 4
    TIMER_5 = 19  # таймер 5
    TIMER_6 = 20  # таймер 6
    MIXING = 21  # перемеш-е


OUT_FUNCS: list[None | ClimateController] = [None] * 256

for item in OutFunc:
    if isinstance(item.value, ClimateController):
        OUT_FUNCS[item.value.index] = item.value


def step():
    # Независимые параметры
    state.uptime += 1
    state.time = (state.time + 1) % 86400

    # TODO: other parms

    # Климат
    for index in range(len(state.outs.sum_on_s)):
        if state.outs.sum_on_s[index] > 0:
            state.outs.sum_on_s[index] -= 1

        if config.clim and config.outsfn:
            fid = config.outsfn[index]
            func = OUT_FUNCS[fid]
            if func:
                func.step(config.clim, state, index)

    # if config.clim:
    #     clim_step(config.clim.heater, values.temp_air, OutFunc.HEATER)
    #     clim_step(config.clim.air_cooler, values.temp_air, OutFunc.AIR_CONDITIONER)
    #     clim_step(config.clim.heater, values.temp_air, OutFunc.HEATER)


def apply_cfg(cfg: Config):
    if cfg.clim:
        config.clim = cfg.clim
    if cfg.env:
        config.env = cfg.env
    if cfg.nsolution:
        config.nsolution = cfg.nsolution
    if cfg.outsfn and config.outsfn:
        for i, fn in enumerate(cfg.outsfn):
            config.outsfn[i] = fn


@asynccontextmanager
async def proxy_lifespan(_router: APIRouter):
    task = asyncio.create_task(run_proxy_seconds())
    yield
    _ = task.cancel()


async def run_proxy_seconds():
    while True:
        try:
            await asyncio.sleep(1 / SPEED_SCALE)
            try:
                step()
            except Exception as e:
                trace.error(e)
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
