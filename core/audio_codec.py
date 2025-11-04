import opuslib_next
from typing import Optional

from .debug import Debug

class OpusEncoder:
    """Encodes raw audio (PCM) into Opus format using opuslib_next."""

    def __init__(self, rate: int = 48000, channels: int = 1, frame_size: int = 960, debug: Debug = Debug()):
        self._rate = rate
        self._channels = channels
        self._frame_size = frame_size # Number of samples per frame
        self._debug = debug
        # opuslib_next.Encoder takes sampling_rate, channels, and application
        self._encoder = opuslib_next.Encoder(self._rate, self._channels, opuslib_next.APPLICATION_AUDIO)

    def encode(self, pcm_data: bytes) -> Optional[bytes]:
        """Encodes PCM audio data into Opus format."""
        try:
            # opuslib_next expects PCM data as a byte string
            encoded_data = self._encoder.encode(pcm_data, self._frame_size)
            return encoded_data
        except Exception as e:
            self._debug.log("OpusEncoder", f"Error encoding audio: {e}")
            return None

class OpusDecoder:
    """Decodes Opus-encoded audio into raw audio (PCM) using opuslib_next."""

    def __init__(self, rate: int = 48000, channels: int = 1, debug: Debug = Debug()):
        self._rate = rate
        self._channels = channels
        self._debug = debug
        # opuslib_next.Decoder takes sampling_rate and channels
        self._decoder = opuslib_next.Decoder(self._rate, self._channels)

    def decode(self, opus_data: bytes) -> Optional[bytes]:
        """Decodes Opus audio data into PCM format."""
        try:
            # opuslib_next decodes to a byte string of PCM data
            decoded_data = self._decoder.decode(opus_data, self._rate * self._channels * 2) # Max frame size
            return decoded_data
        except Exception as e:
            self._debug.log("OpusDecoder", f"Error decoding audio: {e}")
            return None
