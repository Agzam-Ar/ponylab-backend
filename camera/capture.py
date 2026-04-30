import io
from pathlib import Path
from typing import Any

picamera2_available = True
try:
    from picamera2 import Picamera2  # pyright: ignore[reportMissingTypeStubs]
except Exception:
    Picamera2 = None
    picamera2_available = False

PLACEHOLDER_PATH = Path(__file__).parent / "placeholder.png"
print(f"placeholder: {PLACEHOLDER_PATH}")


class Camera:
    _use_placeholder: bool

    def __init__(self):
        self._cam: Any = None  # pyright: ignore[reportExplicitAny]
        self._use_placeholder = not picamera2_available

    def _ensure_camera(self):
        if self._cam is None and not self._use_placeholder and Picamera2 is not None:  # pyright: ignore[reportAny]
            try:
                self._cam = Picamera2()
                self._cam.start()  # pyright: ignore[reportAny]
            except Exception as e:
                print(f"Error: {e}")
                self._use_placeholder = True

    def capture(self) -> bytes:
        self._ensure_camera()
        if self._use_placeholder or self._cam is None:  # pyright: ignore[reportAny]
            return self._read_placeholder()

        img = self._cam.capture_array()  # pyright: ignore[reportAny]
        buf = io.BytesIO()
        from PIL import Image

        Image.fromarray(img).convert("RGB").save(buf, format="JPEG", quality=85)  # pyright: ignore[reportAny]
        return buf.getvalue()

    def _read_placeholder(self) -> bytes:
        if PLACEHOLDER_PATH.exists():
            return PLACEHOLDER_PATH.read_bytes()
        return b""

    def get_stream(self) -> bytes:
        return self.capture()
