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


"""
Настройки растворного узла
"""


class NSolution(BaseModel):
    mixing_time_min: int

    ph_down_trig: float
    pump_ph_down_quant_s: float

    ph_up_trig: float
    pump_ph_up_quant_s: float

    ec_down_trig_msm: float
    pump_ec_down_quant_s: float

    ec_up_trig_msm: float
    pump_ec_up_quant_s: float

    b_koeff: float
    c_koeff: float

    pump_water_lvl_quant_s: float

    lvl_ignore_time_min: int
    lvl_run_delay_min: int
    lvl_off_delay_min: int

    temp_ctrl_on_temp: float
    temp_ctrl_off_temp: float

    temp_ctrl_time_on_above_min: int
    temp_ctrl_time_on_below_min: int
    temp_ctrl_time_off_above_min: int

    ph_protection_delta: float
    ec_protection_percent: float


"""
Общий конфиг
"""


class Config(BaseModel):
    env: Env | None = None
    clim: Clim | None = None
    nsolution: NSolution | None = None
