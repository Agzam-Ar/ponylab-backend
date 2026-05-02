import logs.plant_log
import logic.rules


class Config:
    rules: logic.rules.PlantRules = logic.rules.PlantRules()
    log: logs.plant_log.PlantLog = logs.plant_log.PlantLog()
