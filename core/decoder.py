from abc import ABC, abstractmethod
import struct
from io import BytesIO
from typing import Any

from PIL import Image

from .streamable import Streamable, ScreenFrame
from .debug import Debug

class Decoder(ABC):
    """An interface for decoding streamable data."""

    @abstractmethod
    def decode(self, data: bytes) -> Streamable:
        """Decode the raw bytes into streamable data."""
        pass

class JpegDecoder(Decoder):
    """A class for decoding JPEG images."""

    def __init__(self, debug: Debug = Debug()):
        self._debug = debug

    def decode(self, data: bytes) -> tuple[Streamable, float]:
        """Decode the JPEG bytes into a ScreenFrame and return the timestamp."""
        # Extract timestamp (first 8 bytes for a double)
        timestamp = struct.unpack('d', data[:8])[0]
        jpeg_data = data[8:]

        self._debug.log("JpegDecoder", f"Received jpeg_data starting with: {jpeg_data[:10].hex()}")

        img = Image.open(BytesIO(jpeg_data))
        return ScreenFrame(img), timestamp
