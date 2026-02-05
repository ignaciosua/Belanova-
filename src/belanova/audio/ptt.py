import threading
from dataclasses import dataclass
from typing import Optional

import numpy as np
import sounddevice as sd
from pynput import keyboard


@dataclass
class AudioChunk:
    samples: np.ndarray
    sample_rate: int


class PushToTalkRecorder:
    def __init__(self, key: str = "space", sample_rate: int = 16000):
        self.sample_rate = sample_rate
        self._key = self._parse_key(key)
        self._recording = threading.Event()
        self._pressed = threading.Event()
        self._released = threading.Event()
        self._frames: list[np.ndarray] = []

    def _parse_key(self, key: str):
        key = key.lower().strip()
        if key == "space":
            return keyboard.Key.space
        if key == "enter":
            return keyboard.Key.enter
        if key == "shift":
            return keyboard.Key.shift
        if key == "ctrl" or key == "control":
            return keyboard.Key.ctrl
        if key == "alt":
            return keyboard.Key.alt
        if key in ("alt_r", "right_alt", "ralt"):
            return keyboard.Key.alt_r
        if key in ("alt_l", "left_alt", "lalt"):
            return keyboard.Key.alt_l
        if key in ("altgr", "alt_gr"):
            return keyboard.Key.alt_gr
        return keyboard.KeyCode.from_char(key)

    def _on_press(self, key):
        if key == keyboard.Key.esc:
            self._released.set()
            return False
        if key == self._key and not self._pressed.is_set():
            self._pressed.set()
            self._recording.set()
            self.on_ptt_press()
        return True

    def _on_release(self, key):
        if key == self._key and self._pressed.is_set():
            self._recording.clear()
            self._released.set()
            self.on_ptt_release()
            return False
        return True

    def _audio_callback(self, indata, frames, time, status):
        if status:
            return
        if self._recording.is_set():
            self._frames.append(indata.copy())

    def record_once(
        self,
        on_press: Optional[callable] = None,
        on_release: Optional[callable] = None,
        start_immediately: bool = False,
    ) -> Optional[AudioChunk]:
        self._frames = []
        self._pressed.clear()
        self._released.clear()
        self.on_ptt_press = on_press or (lambda: None)
        self.on_ptt_release = on_release or (lambda: None)
        if start_immediately:
            self._pressed.set()
            self._recording.set()

        with keyboard.Listener(on_press=self._on_press, on_release=self._on_release) as listener:
            with sd.InputStream(
                samplerate=self.sample_rate,
                channels=1,
                dtype="float32",
                callback=self._audio_callback,
            ):
                self._released.wait()
            listener.stop()

        if not self._pressed.is_set():
            return None

        if not self._frames:
            return AudioChunk(samples=np.zeros((0,), dtype=np.float32), sample_rate=self.sample_rate)

        audio = np.concatenate(self._frames, axis=0).reshape(-1)
        return AudioChunk(samples=audio, sample_rate=self.sample_rate)
