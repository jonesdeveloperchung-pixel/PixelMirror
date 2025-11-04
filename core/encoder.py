from abc import ABC, abstractmethod
import time
import struct
from io import BytesIO

from PIL import Image

from .streamable import Streamable
from .debug import Debug

class Encoder(ABC):
    """An interface for encoding streamable data."""

    @abstractmethod
    def encode(self, data: Streamable) -> bytes:
        """Encode the streamable data."""
        pass

class JpegEncoder(Encoder):
    """A class for encoding images as JPEGs."""

    def __init__(self, quality: int = 70, debug: Debug = Debug()):
        self._quality = quality
        self._debug = debug

    def encode(self, data: Streamable) -> bytes:
        """Encode the image as a JPEG."""
        frame = data.get_data()
        img = Image.frombytes("RGB", frame.size, frame.bgra, "raw", "BGRX")
        with BytesIO() as buf:
            img.save(buf, format="JPEG", quality=self._quality)
            encoded_data = buf.getvalue()
            
            # Prepend timestamp to the encoded data
            timestamp = time.time()
            timestamp_bytes = struct.pack('d', timestamp) # 'd' for double (8 bytes)
            final_data = timestamp_bytes + encoded_data

            self._debug.log("JpegEncoder", f"Encoded frame with timestamp to size {len(final_data)}")
            return final_data
