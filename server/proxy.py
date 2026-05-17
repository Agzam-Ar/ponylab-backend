import asyncio
from contextlib import asynccontextmanager
from enum import Enum
import os
from typing import Callable, override

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


class FuncController(BaseModel):
    index: int
    name: str = "неизвестно"

    delta: dict[Sensors, float] = {}
    delta_off: dict[Sensors, float] = {}

    def step(self, _config: Config, state: State, out: int):
        if state.outs.sum_on_s[out] > 0:  # Если включен
            self.apply(state)

    def get_sum(self, state: State, out: int):
        return state.outs.sum_on_s[out]

    def set_sum(self, state: State, out: int, sec: float):
        state.outs.sum_on_s[out] = sec

    def set_countdown(self, state: State, out: int, sec: float):
        if config.outsfn:
            state.outs.func_cntdn_s[config.outsfn[out]] = sec

    def set_time(self, state: State, out: int, sec: float):
        self.set_sum(state, out, sec)
        self.set_countdown(state, out, sec)

    def set_desc(self, state: State, sec: float):
        s = int(abs(sec))
        state.description += f"{self.name} {'вкл' if sec > 0 else 'выкл'} [{(s // 60):02d}:{(s % 60):02d}]<br>"
        pass

    def apply(self, state: State):
        for sensor, d in self.delta.items():
            sv = state.values[sensor.value]
            if sv.v:
                sv.v += d * 10

    def apply_off(self, state: State):
        for sensor, d in self.delta_off.items():
            sv = state.values[sensor.value]
            if sv.v:
                sv.v += d * 10


class ClimateController(FuncController):
    """Enum для outsfn из Config"""

    control: Callable[[Clim], ClimateControl]
    sensor: Sensors

    @override
    def step(self, config: Config, state: State, out: int):
        sum = self.get_sum(state, out)
        if config.clim is not None:
            c = self.control(config.clim)
            value = self.sensor.from_state(state)
            if c.under(value) and sum < 1:  # Под диапозоном - включаем
                sum = c.t_on_min * 60

        if sum > 0:
            sum -= 1
            self.apply(state)
            self.set_desc(state, sum)
        else:
            self.apply_off(state)

        self.set_time(state, out, sum)


class TimersController(FuncController):
    timer: int

    _time: int = 0
    _pause: int = 0

    @override
    def step(self, config: Config, state: State, out: int):
        if config.env is not None:
            t = config.env.timers[self.timer]
            if t.m == 2:
                if self._time > 0:
                    self._time -= 1
                    self.apply(state)
                    self.set_time(state, out, self._time)
                    self.set_desc(state, self._pause)
                elif self._pause > 0:
                    self._pause -= 1
                    self.set_desc(state, -self._pause)
                    self.apply_off(state)
                else:
                    self._time = 0 if t.data.t1 is None else t.data.t1
                    self._pause = 0 if t.data.t2 is None else t.data.t2
            if t.m == 3 and t.data.table:
                pause = 86400 - state.time
                for item in t.data.table:
                    if item.t1 < state.time < item.t2:
                        self.apply(state)
                        time = item.t2 - state.time
                        self.set_time(state, out, time)
                        self.set_desc(state, time)
                        pause = 0
                        break
                    if state.time < item.t1:
                        pause = min(pause, item.t1 - state.time)

                if pause > 0:
                    self.set_desc(state, -pause)
                    self.apply_off(state)


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
        name="кондиционер",
        control=lambda c: c.air_cooler,
        sensor=Sensors.TEMP_AIR,
        delta={
            Sensors.TEMP_AIR: -0.04,  # кондиционер эффективно охлаждает
            Sensors.HUMIDITY_AIR: -0.01,  # кондиционер побочно сушит воздух
        },
    )
    DEHUMIDIFIER = ClimateController(
        index=8,
        name="осушитель",
        control=lambda c: c.dehumidifier,
        sensor=Sensors.HUMIDITY_AIR,
        delta={
            Sensors.HUMIDITY_AIR: -0.04,  # осушает воздух (-2.4% в минуту)
            Sensors.TEMP_AIR: 0.008,  # побочный нагрев от компрессора
        },
    )
    EXHAUST_FAN = ClimateController(
        index=9,
        name="вытяжка",
        control=lambda c: (
            c.extractor_h
        ),  # управляется логикой вытяжки по влажности (или c.extractor_t)
        sensor=Sensors.HUMIDITY_AIR,
        delta={
            Sensors.HUMIDITY_AIR: -0.2,  # стремительно вытягивает влагу (зависит от улицы, берем среднее падение)
            Sensors.TEMP_AIR: -0.05,  # выдувает тепло наружу
            Sensors.CO2: -2.0,  # быстро сбрасывает CO2 до уличных значений
        },
    )
    HUMIDIFIER = ClimateController(
        index=10,
        name="увлажнитель",
        control=lambda c: c.humidifier,
        sensor=Sensors.HUMIDITY_AIR,
        delta={Sensors.HUMIDITY_AIR: 0.04},  # увлажняет на +2.4% в минуту
    )
    HEATER = ClimateController(
        index=11,
        name="обогреватель",
        control=lambda c: c.heater,
        sensor=Sensors.TEMP_AIR,
        delta={
            Sensors.TEMP_AIR: 0.02,  # нагрев воздуха на +1.2°C в минуту
            Sensors.HUMIDITY_AIR: -0.01,  # физическое падение относительной влажности при нагреве
        },
    )
    CO2_VALVE = ClimateController(
        index=12,
        name="клапан СО2",
        control=lambda c: c.co2,
        sensor=Sensors.CO2,
        delta={Sensors.CO2: 1.5},  # подача газа повышает уровень на +1.5 ppm в секунду
    )
    LIGHT = TimersController(
        index=13,
        name="свет",
        timer=0,
        delta_off={
            Sensors.LIGHT: 5000.0,  # мгновенный приток освещенности (в люксах)
            Sensors.TEMP_AIR: 0.005,  # побочный нагрев воздуха от ламп (0.3°C в минуту)
        },
    )
    WATERING = TimersController(
        index=14,
        name="полив",
        timer=1,
        delta={},
    )
    TIMER_1 = 15  # таймер 1
    TIMER_2 = 16  # таймер 2
    TIMER_3 = 17  # таймер 3
    TIMER_4 = 18  # таймер 4
    TIMER_5 = 19  # таймер 5
    TIMER_6 = 20  # таймер 6
    MIXING = 21  # перемеш-е


OUT_FUNCS: list[None | FuncController] = [None] * 256

for item in OutFunc:
    if isinstance(item.value, FuncController):
        OUT_FUNCS[item.value.index] = item.value


def step():
    state.description = ""
    # Независимые параметры
    state.uptime += 1
    state.time = (state.time + 1) % 86400

    state.values[Sensors.LIGHT.value].v = 0

    # TODO: other parms

    # Климат
    # for index in range(len(state.outs.func_cntdn_s)):
    #     if state.outs.func_cntdn_s[index] > 0:
    #         state.outs.func_cntdn_s[index] -= 1

    for index in range(len(state.outs.sum_on_s)):
        # if state.outs.sum_on_s[index] > 0:
        #     state.outs.sum_on_s[index] -= 1

        if config.outsfn:
            fid = config.outsfn[index]
            func = OUT_FUNCS[fid]
            if func:
                func.step(config, state, index)

    # Таймеры


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
