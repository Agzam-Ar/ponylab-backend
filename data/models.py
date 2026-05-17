from pydantic import BaseModel, Field

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


"""

"""


class SensorValue(BaseModel):
    r: float = Field(..., description="Сырое значение с датчика (raw)")
    t: int = Field(..., description="Тип датчика / идентификатор параметра")
    v: float | None = Field(
        None, description="Валидированное / отфильтрованное значение"
    )
    e: int | None = Field(None, description="Код ошибки или статус (если применимо)")


class Outputs(BaseModel):
    sum_on_s: list[float] = Field(
        ..., description="Суммарное время включения выходов в секундах"
    )
    func_cntdn_s: list[float] = Field(
        ..., description="Обратный отсчет таймеров функций в секундах"
    )
    ovrrd_time: list[float] = Field(
        ..., description="Время принудительного переопределения (override)"
    )
    ovrrd_state: list[int] = Field(
        ..., description="Состояние принудительного переопределения"
    )


class State(BaseModel):
    ver: str
    values: list[SensorValue] = Field(..., description="Массив показаний датчиков")
    raw_ec_msm: float = Field(
        ..., description="Сырые измерения электропроводимости (EC)"
    )
    cfghsh: int = Field(..., description="Хеш-сумма конфигурации (config hash)")
    uptime: int = Field(
        ..., description="Время непрерывной работы устройства (аптайм) в секундах"
    )
    time: int = Field(..., description="Текущее системное время устройства / эпоха")
    frhp: int = Field(..., description="Свободная память кучи (Free Heap)")
    maxahp: int = Field(
        ..., description="Максимальный аллоцируемый блок кучи (Max Alloc Heap)"
    )
    mfrhp: int = Field(
        ..., description="Минимальный зафиксированный уровень свободной памяти"
    )
    hpsz: int = Field(..., description="Общий размер кучи (Heap Size)")
    wifi: int = Field(..., description="Статус или уровень сигнала Wi-Fi")
    ofuc: int = Field(..., description="Счетчик сбоев или переполнений")
    description: str = Field(
        ..., description="Текстовый лог текущих процессов и ошибок"
    )
    outs: Outputs = Field(
        ..., description="Объект состояния исполнительных устройств (выходов)"
    )
    errors: list[str] | None = Field(None)
