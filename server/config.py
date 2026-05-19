import os

from colorama import Fore

import logs.plant_log
import logic.rules


def _bool(value: object):
    return value is True or value == "True" or value == "1" or value == 1


class Vars:
    rules: logic.rules.PlantRules = logic.rules.PlantRules()
    log: logs.plant_log.PlantLog = logs.plant_log.PlantLog()

    LLM_BASE_URL: str = os.getenv("LLM_BASE_URL", "http://127.0.0.1:11435/v1")
    LLM_API_KEY: str = os.getenv("LLM_API_KEY", "no-key-required")
    LLM_SKIP: bool = _bool(os.getenv("LLM_SKIP", False))

    CAMERA_PLACEHOLDER: str = os.getenv("CAMERA_PLACEHOLDER", "placeholder.png")
    CAMERA_SKIP: bool = _bool(os.getenv("CAMERA_SKIP", False))

    YIELDIZER_URL: str = os.getenv("YIELDIZER_URL", "http://127.0.0.1:3001")
    YIELDIZER_TIMEOUT: float = float(os.getenv("YIELDIZER_TIMEOUT", 1.0))

    REFRESH_TIME: int = int(os.getenv("REFRESH_TIME", 60 * 10))

    @classmethod
    def print_config(cls):
        print("\n" + "=" * 20 + " LOADED CONFIG " + "=" * 20)
        for key, value in cls.__dict__.items():  # pyright: ignore[reportAny]
            if not key.startswith("__") and key not in ("rules", "log", "print_config"):
                if "KEY" in key and value != "no-key-required":
                    value = (
                        f"{value[:4]}***{value[-4:]}" if len(str(value)) > 8 else "***"  # pyright: ignore[reportAny]
                    )
                color = Fore.LIGHTYELLOW_EX
                if isinstance(value, int):
                    color = Fore.LIGHTMAGENTA_EX
                if value is True:
                    color = Fore.GREEN
                if value is False:
                    color = Fore.LIGHTRED_EX
                if isinstance(value, str) and value.startswith("http"):
                    color = Fore.CYAN

                print(f"{Fore.LIGHTBLUE_EX}{key:<20}{color} {value}{Fore.RESET}")
        print(f"{'=' * 55}\n")


Vars.print_config()
