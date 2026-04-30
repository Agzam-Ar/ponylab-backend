import csv
from dataclasses import dataclass
from pathlib import Path

PLANT_DATA_DIR = Path(__file__).parent.parent / "data" / "plants"

PlantValue = int | float | str


@dataclass
class PlantRule:
    value: int | float | None
    min: int | float | None
    max: int | float | None

    def range(self):
        return f"{self.min}-{self.max}"

    def clamp(self, value: int | float):
        if self.max is not None and value > self.max:
            return self.max
        if self.min is not None and value < self.min:
            return self.min
        return value


PlantParms = dict[str, int | float]
PlantRulesTable = dict[str, PlantRule]


def auto_type(value: str):
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        pass
    return None


class PlantRules:
    plant_type: str
    _table: PlantRulesTable
    _keys: list[str] = []

    def __init__(self, plant_type: str = "tomato"):
        self.plant_type = plant_type
        self._table = self._load_table(plant_type)

    def _load_table(self, plant_type: str) -> PlantRulesTable:
        path = PLANT_DATA_DIR / f"{plant_type}.csv"
        if not path.exists():
            print(f"[PlantRules] CSV not found: {path}, using defaults")
            raise RuntimeError("CSV rules not Loaded")

        rules: PlantRulesTable = {}
        with open(path, newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                param = str(row["param"])
                self._keys.append(param)
                rules[param] = PlantRule(
                    value=auto_type(row["value"]),
                    min=auto_type(row["min"]),
                    max=auto_type(row["max"]),
                )
        return rules

    def iter(self):
        return self._table.items()

    def specification(self):
        return ",\n".join(
            [
                f'"recommended_{parm}": {self._table[parm].range()}'
                for parm in self._table.keys()
            ]
        )

    def adjust_ai_params(self, ai_params: PlantParms) -> PlantParms:
        """
        Зажимает каждый параметр AI в допустимые границы из CSV.
        stage больше не используется — диапазоны единые.
        """
        for parm in self._table.keys():
            rule = self._table[parm]
            if parm in ai_params:
                before = ai_params[parm]
                ai_params[parm] = rule.clamp(before)
                if ai_params[parm] != before:
                    print(f"[PlantRules] {parm} clamped: {before} -> {ai_params[parm]}")
        return ai_params


@dataclass
class Rules:
    tomato: PlantRules = PlantRules("tomato")
