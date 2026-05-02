from logic.rules import PlantRules
from logs.plant_log import PlantLog


class Config:
    rules: PlantRules = PlantRules()
    log: PlantLog = PlantLog()
