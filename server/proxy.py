import asyncio
from contextlib import asynccontextmanager
from enum import Enum
import os
import random
from time import time
from typing import Callable, override

from fastapi import APIRouter, Form, HTTPException, Response
from fastapi.responses import HTMLResponse, PlainTextResponse
from pydantic import BaseModel
from data.models import Clim, ClimateControl, Cmd, Config, NSolution, Sensors, State
from data.yieldizer import get, page
from logs import trace
from logs.trace import error


try:
    with open("server/snapshots/state.json", "r", encoding="utf-8") as f:
        state = State.model_validate_json(f.read())
        state.time = int(time()) % 86400

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

    delta: dict[Sensors, float | Callable[[float], float]] = {}
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

    def set_desc(self, state: State, sec: float, text: str | None = None):
        s = int(abs(sec))
        state.description += f"{self.name} {text if text is not None else 'вкл' if sec > 0 else 'выкл'} [{(s // 60):02d}:{(s % 60):02d}]<br>"
        pass

    def apply(self, state: State):
        for sensor, d in self.delta.items():
            if isinstance(d, float):
                sensor.add(state, d + max(-1, min(1, random.uniform(-d, d) * 0.15)))
            elif isinstance(d, Callable):
                sensor.set(state, d(sensor.get(state)))

    def apply_off(self, state: State):
        for sensor, d in self.delta_off.items():
            sv = state.values[sensor.value]
            if sv.v:
                sv.v += d + max(-1, min(1, random.uniform(-d, d) * 0.15))


class LimitsController(FuncController):
    sensor: Sensors

    def border_on(self, _config: Config):
        return 0.0

    def border_off(self, _config: Config):
        return 0.0

    def time_min(self, _config: Config):
        return 0.0

    @override
    def step(self, config: Config, state: State, out: int):
        sum = self.get_sum(state, out)

        if sum < 1 and self.under(
            self.sensor.get(state), self.border_on(config), self.border_off(config)
        ):  # Под диапозоном - включаем
            sum = self.time_min(config) * 60

        if sum > 0:
            sum -= 1
            self.apply(state)
            self.set_desc(state, sum)
        else:
            self.apply_off(state)

        self.set_time(state, out, sum)

    def under(self, value: float, a: float, b: float):
        if a < b:
            return value < a
        return value > b


class ClimateLimitsController(LimitsController):
    control: Callable[[Clim], ClimateControl]

    @override
    def border_on(self, config: Config):
        if config.clim is None:
            return 0.0
        return self.control(config.clim).thr_on

    @override
    def border_off(self, config: Config):
        if config.clim is None:
            return 0.0
        return self.control(config.clim).thr_off

    @override
    def time_min(self, config: Config):
        if config.clim is None:
            return 0.0
        return self.control(config.clim).t_on_min


class ChillerLimitsController(LimitsController):
    @override
    def border_on(self, _config: Config):
        return 0.0 if config.nsolution is None else config.nsolution.temp_ctrl_on_temp

    @override
    def border_off(self, _config: Config):
        return 0.0 if config.nsolution is None else config.nsolution.temp_ctrl_off_temp

    @override
    def time_min(self, _config: Config):
        return (
            0.0
            if config.nsolution is None
            else config.nsolution.temp_ctrl_time_off_above_min
        )


class SolutionController(FuncController):
    _pause: float = 0
    sensor: Sensors
    trigger: Callable[[NSolution, float], bool]
    time: Callable[[NSolution], float]

    @override
    def step(self, _config: Config, state: State, out: int):
        sum = self.get_sum(state, out)
        print(f"[{self.sensor.name}] пауза: {self._pause}")

        if (
            sum < 1
            and self._pause < 1
            and config.nsolution
            and self.trigger(config.nsolution, self.sensor.get(state))
        ):  # Под диапозоном - включаем
            sum = self.time(config.nsolution)
            self._pause = config.nsolution.mixing_time_min * 60

        if sum > 0:
            sum -= 1
            self.apply(state)
            self.set_desc(state, sum)
        else:
            if self._pause > 0:
                self._pause -= 1
                self.set_desc(state, self._pause, "запрет")
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
    PH_DOWN = SolutionController(
        index=0,
        name="pH DOWN",
        sensor=Sensors.PH,
        trigger=lambda s, v: v > s.ph_down_trig,
        time=lambda s: s.pump_ph_down_quant_s,
        delta={
            Sensors.PH: -0.02,
        },
    )
    PH_UP = SolutionController(
        index=1,
        name="pH UP",
        sensor=Sensors.PH,
        trigger=lambda s, v: v < s.ph_up_trig,
        time=lambda s: s.pump_ph_up_quant_s,
        delta={
            Sensors.PH: 0.02,
        },
    )
    FERTILIZER_A = SolutionController(
        index=2,
        name="удобрение A",
        sensor=Sensors.EC,
        trigger=lambda s, v: v < s.ec_up_trig_msm,
        time=lambda s: s.pump_ec_up_quant_s,
        delta={
            Sensors.EC: 0.02,  # один квант работы насоса поднимает EC на 0.02 mS/cm
            Sensors.PH: -0.01,  # побочное закисление раствора от концентрата
        },
    )
    FERTILIZER_B = SolutionController(
        index=3,
        name="удобрение B",
        sensor=Sensors.EC,
        trigger=lambda s, v: v < s.ec_up_trig_msm,
        time=lambda s: s.pump_ec_up_quant_s,
        delta={
            Sensors.EC: 0.02,
            Sensors.PH: -0.01,
        },
    )
    FERTILIZER_C = SolutionController(
        index=4,
        name="удобрение C",
        sensor=Sensors.EC,
        trigger=lambda s, v: v < s.ec_up_trig_msm,
        time=lambda s: s.pump_ec_up_quant_s,
        delta={
            Sensors.EC: 0.02,
            Sensors.PH: -0.005,  # разные компоненты могут влиять на pH с разной силой
        },
    )
    WATER_REFILL = SolutionController(
        index=5,
        name="долив воды",
        sensor=Sensors.LEVEL,
        trigger=lambda s, v: v < 1,  # триггер по падению уровня жидкости
        time=lambda s: s.pump_water_lvl_quant_s,
        delta={
            Sensors.LEVEL: lambda x: (
                x + (1 if random.random() < 0.05 else 0)
            ),  # уровень жидкости растет (рандом ибо требуются целые числа)
            # Долив чистой воды разбавляет соли и меняет pH (лямбда или дельта смешивания):
            Sensors.PH: lambda x: x * 0.99 + (7.5) * 0.01,
            Sensors.EC: lambda x: x * 0.99 + (0.3) * 0.01,
        },
    )
    CHILLER = ChillerLimitsController(
        index=6,
        name="чиллер",
        sensor=Sensors.TEMP_SOLUTION,
        delta={
            Sensors.TEMP_SOLUTION: -0.04,
        },
    )
    AIR_CONDITIONER = ClimateLimitsController(
        index=7,
        name="кондиционер",
        control=lambda c: c.air_cooler,
        sensor=Sensors.TEMP_AIR,
        delta={
            Sensors.TEMP_AIR: -0.04,  # кондиционер эффективно охлаждает
            Sensors.HUMIDITY_AIR: -0.01,  # кондиционер побочно сушит воздух
        },
    )
    DEHUMIDIFIER = ClimateLimitsController(
        index=8,
        name="осушитель",
        control=lambda c: c.dehumidifier,
        sensor=Sensors.HUMIDITY_AIR,
        delta={
            Sensors.HUMIDITY_AIR: -0.04,  # осушает воздух (-2.4% в минуту)
            Sensors.TEMP_AIR: 0.008,  # побочный нагрев от компрессора
        },
    )
    EXHAUST_FAN = ClimateLimitsController(
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
    HUMIDIFIER = ClimateLimitsController(
        index=10,
        name="увлажнитель",
        control=lambda c: c.humidifier,
        sensor=Sensors.HUMIDITY_AIR,
        delta={Sensors.HUMIDITY_AIR: 0.04},  # увлажняет на +2.4% в минуту
    )
    HEATER = ClimateLimitsController(
        index=11,
        name="обогреватель",
        control=lambda c: c.heater,
        sensor=Sensors.TEMP_AIR,
        delta={
            Sensors.TEMP_AIR: 0.02,  # нагрев воздуха на +1.2°C в минуту
            Sensors.HUMIDITY_AIR: -0.01,  # физическое падение относительной влажности при нагреве
        },
    )
    CO2_VALVE = ClimateLimitsController(
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
        delta={
            Sensors.CO2: 0.02,
        },
        delta_off={
            Sensors.LIGHT: 12212.0,  # мгновенный приток освещенности (в люксах)
            Sensors.TEMP_AIR: 0.005,  # побочный нагрев воздуха от ламп (0.3°C в минуту)
            Sensors.CO2: -0.08,
        },
    )
    WATERING = TimersController(
        index=14,
        name="полив",
        timer=1,
        delta={
            # При поливе тратится раствор и разбавляется водой
            Sensors.PH: lambda x: x * 0.99 + (7.5) * 0.01,
            Sensors.EC: lambda x: x * 0.99 + (0.3) * 0.01,
        },
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
    # Пассивные параметры
    state.uptime += 1
    state.time = (state.time + 1) % 86400
    state.wifi = random.randint(-43, -40)

    Sensors.LIGHT.set(state, 37)
    Sensors.TEMP_AIR.add(
        state,
        (Sensors.TEMP_SOLUTION.get(state) - Sensors.TEMP_AIR.get(state)) * 0.0005
        - 0.00001,
    )

    # Раствор
    # if Sensors.

    # Климат/таймеры
    for index in range(len(state.outs.sum_on_s)):
        if config.outsfn:
            fid = config.outsfn[index]
            func = OUT_FUNCS[fid]
            if func:
                if state.outs.ovrrd_time[index] > 0:
                    if state.outs.ovrrd_state[index] == 1:
                        func.apply(state)
                    else:
                        func.apply_off(state)
                    state.outs.ovrrd_time[index] -= 1
                    continue
                func.step(config, state, index)


def apply_cmd(cmd: Cmd):
    if cmd.type == "out_ctrl":
        state.outs.ovrrd_state[cmd.num] = cmd.state
        state.outs.ovrrd_time[cmd.num] = cmd.time


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


@proxy.post("/cmd")
async def proxy_post_cfg(jdata: str = Form(...)):
    try:
        cmd = Cmd.model_validate_json(jdata)
        apply_cmd(cmd)
        return Response("ok", media_type="text/plain")
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Ошибка: {e}")


print("Proxy endpoints loaded")


# Описываем логику старта и стопа секундного цикла для прокси


# Создаем роутер и передаем ему свой lifespan
router = APIRouter(lifespan=proxy_lifespan)
