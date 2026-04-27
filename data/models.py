from pydantic import BaseModel

"""
Настройки таймеров
"""


class TableItem(BaseModel):
    t1: int
    t2: int


class TimerData(BaseModel):
    # расписание
    dbegin: int | None = None
    dskip: int | None = None
    table: list[TableItem] | None = None

    # циклический
    t1: int | None = None
    t2: int | None = None


class Timer(BaseModel):
    m: int
    data: TimerData


class Env(BaseModel):
    timers: list[Timer]


class Config(BaseModel):
    env: Env


"""
Настройки контроллера климата
"""


class ClimateControl(BaseModel):
    thr_on: float
    thr_off: float
    t_on_min: float
    t_on_max: float
    t_pause: float


class Clim(BaseModel):
    air_cooler: ClimateControl
    dehumidifier: ClimateControl
    extractor_t: ClimateControl
    extractor_h: ClimateControl
    humidifier: ClimateControl
    co2: ClimateControl
    heater: ClimateControl
