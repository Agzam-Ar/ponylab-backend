import os
import io
from pathlib import Path
from typing import Optional
from picamera2 import Picamera2

PICAMERA2_AVAILABLE = True
PLACEHOLDER_PATH = Path(__file__).parent / "placeholder.png"
print(f"placeholder: {PLACEHOLDER_PATH}")


class Camera:
    def __init__(self):
        self._cam: Optional[object] = None
        self._use_placeholder = not PICAMERA2_AVAILABLE

    def _ensure_camera(self):
        if self._cam is None and not self._use_placeholder:
            try:
                self._cam = Picamera2()
                self._cam.start()
            except Exception as e:
                print(f"Error: {e}")
                self._use_placeholder = True

    def capture(self) -> bytes:
        self._ensure_camera()
        if self._use_placeholder or self._cam is None:
            return self._read_placeholder()

        img = self._cam.capture_array()
        buf = io.BytesIO()
        from PIL import Image

        Image.fromarray(img).convert("RGB").save(buf, format="JPEG", quality=85)
        return buf.getvalue()

    def _read_placeholder(self) -> bytes:
        if PLACEHOLDER_PATH.exists():
            return PLACEHOLDER_PATH.read_bytes()
        return b""

    def get_stream(self) -> bytes:
        return self.capture()

