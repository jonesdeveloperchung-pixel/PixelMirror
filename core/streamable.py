from abc import ABC, abstractmethod
from typing import Any

class Streamable(ABC):
    """An interface for streamable data types."""

    @abstractmethod
    def get_data(self) -> Any:
        """Get the data to be streamed."""
        pass

class ScreenFrame(Streamable):
    """A class to represent a screen frame."""

    def __init__(self, frame):
        self._frame = frame

    def get_data(self) -> Any:
        return self._frame
