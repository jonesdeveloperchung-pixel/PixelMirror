import pyaudio
import numpy as np
from typing import Optional

from .debug import Debug

class AudioCapture:
    """Captures audio from the system's default input device."""

    def __init__(self, format=pyaudio.paInt16, channels=1, rate=44100, chunk=1024, debug: Debug = Debug()):
        self._format = format
        self._channels = channels
        self._rate = rate
        self._chunk = chunk
        self._debug = debug
        self._pyaudio = pyaudio.PyAudio()
        self._stream: Optional[pyaudio.Stream] = None

    def start(self):
        """Starts the audio capture stream."""
        if self._stream is None:
            self._stream = self._pyaudio.open(
                format=self._format,
                channels=self._channels,
                rate=self._rate,
                input=True,
                frames_per_buffer=self._chunk
            )
            self._debug.log("AudioCapture", "Audio capture started.")

    def stop(self):
        """Stops the audio capture stream."""
        if self._stream is not None:
            self._stream.stop_stream()
            self._stream.close()
            self._stream = None
            self._debug.log("AudioCapture", "Audio capture stopped.")

    def capture_frame(self) -> Optional[bytes]:
        """Captures a single frame of audio data."""
        if self._stream is not None:
            try:
                data = self._stream.read(self._chunk, exception_on_overflow=False)
                return data
            except Exception as e:
                self._debug.log("AudioCapture", f"Error capturing audio frame: {e}")
        return None

    def __del__(self):
        """Ensures the PyAudio instance is terminated when the object is destroyed."""
        if self._pyaudio:
            self._pyaudio.terminate()

