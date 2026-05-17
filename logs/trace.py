from pretty_errors import (  # pyright: ignore[reportMissingTypeStubs]
    excepthook,  # pyright: ignore[reportUnknownVariableType]
)


def error(e: Exception):
    excepthook(type(e), e, e.__traceback__)
