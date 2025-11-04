from abc import ABC, abstractmethod
from typing import Iterator

import mss
from .streamable import Streamable, ScreenFrame
from .debug import Debug

class Capture(ABC):
    """An interface for capturing streamable data."""

    @abstractmethod
    def capture_gen(self) -> Iterator[Streamable]:
        """A generator that yields streamable data."""
        pass

class ScreenCapture(Capture):
    """A class for capturing the screen."""

    def __init__(self, monitor_id: int = 1, debug: Debug = Debug()):
        self._sct = mss.mss()
        self._monitor = self._sct.monitors[monitor_id]
        self._debug = debug
        self._debug.log("ScreenCapture", f"Capturing monitor {monitor_id}: {self._monitor}")

    def capture_gen(self) -> Iterator[Streamable]:
        """A generator that yields screen frames."""
        while True:
            sct_img = self._sct.grab(self._monitor)
            self._debug.log("ScreenCapture", f"Captured frame of size {sct_img.size}")
            if sct_img.size[0] == 0 or sct_img.size[1] == 0:
                self._debug.log("ScreenCapture", "Captured empty frame, skipping.")
                continue
            yield ScreenFrame(sct_img)
