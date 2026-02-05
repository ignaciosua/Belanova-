from dataclasses import dataclass
from typing import Optional

import numpy as np
import sounddevice as sd
import torch
import subprocess
from pathlib import Path
try:
    import librosa
except Exception:
    librosa = None
try:
    import pyrubberband as pyrb
except Exception:
    pyrb = None

try:
    from kokoro import KPipeline
except Exception as exc:  # pragma: no cover - runtime dependency
    KPipeline = None
    _IMPORT_ERROR = exc
else:
    _IMPORT_ERROR = None


@dataclass
class TTSConfig:
    lang_code: str
    voice: str
    sample_rate: int = 24000
    output_device: str = ""
    playback: str = "sd+aplay"
    speed: float = 1.0
    time_stretch: bool = True
    stretch_engine: str = "rubberband"


class KokoroTTS:
    def __init__(self, config: TTSConfig):
        if KPipeline is None:
            raise RuntimeError(f"Kokoro not available: {_IMPORT_ERROR}")
        self.config = config
        self._pipe = KPipeline(lang_code=self.config.lang_code)
        self._aplay_proc: subprocess.Popen | None = None
        self._stop_flag = False

        output = self._resolve_output_device(self.config.output_device)
        if output is not None:
            sd.default.device = (None, output)
        self._output_device = output
        sd.default.samplerate = self.config.sample_rate
        try:
            device = sd.default.device
            print(f"[tts] output_device={device}")
            if self._output_device is not None:
                info = sd.query_devices(self._output_device, "output")
                print(f"[tts] output_info={info.get('name')} rate={info.get('default_samplerate')}")
        except Exception:
            pass

    def _resolve_output_device(self, output_device: str):
        if not output_device:
            return None
        if output_device.lower() == "default":
            return None
        if output_device.lower() == "auto":
            return self._find_device(["razer", "kraken"])
        if output_device.isdigit():
            return int(output_device)
        if output_device.lower() in ("razer", "kraken", "razer kraken"):
            return self._find_device(["razer", "kraken"])
        return output_device

    def _find_device(self, keywords: list[str]):
        devices = sd.query_devices()
        for idx, dev in enumerate(devices):
            name = dev.get("name", "").lower()
            if dev.get("max_output_channels", 0) <= 0:
                continue
            if all(k in name for k in keywords):
                print(f"[tts] auto-select output device {idx}: {dev.get('name')}")
                return idx
        print("[tts] no se encontró dispositivo coincidente; usando default")
        return None

    def speak(self, text: str, return_audio: bool = False):
        if not text.strip():
            return None
        self._stop_flag = False
        chunks = []
        for _id, _token, audio in self._pipe(text, voice=self.config.voice):
            if self._stop_flag:
                print("[tts] stop_flag activo, cortando habla")
                break
            if isinstance(audio, torch.Tensor):
                audio = audio.detach().cpu().numpy()
            elif isinstance(audio, list):
                audio = np.array(audio, dtype=np.float32)
            if isinstance(audio, np.ndarray):
                audio = audio.astype(np.float32, copy=False)
                peak = float(np.max(np.abs(audio))) if audio.size else 0.0
                print(f"[tts] audio_len={audio.size} peak={peak:.4f}")
                if self.config.speed and self.config.speed != 1.0:
                    audio = self._speed_up(audio, self.config.speed)
                    print(f"[tts] speed={self.config.speed} new_len={audio.size}")
                chunks.append(audio)
                if peak > 0.0:
                    target = 0.8
                    if peak < target:
                        audio = audio * (target / peak)
                # +3 dB ≈ *1.414
                audio = audio * 1.414
            else:
                print(f"[tts] audio tipo inesperado: {type(audio)}")
                continue
            samplerate = self.config.sample_rate
            try:
                out_dev = sd.default.device[1]
                info = sd.query_devices(out_dev, "output")
                device_rate = int(info.get("default_samplerate", samplerate))
                if device_rate and device_rate != samplerate:
                    audio = self._resample(audio, samplerate, device_rate)
                    samplerate = device_rate
            except Exception as exc:
                print(f"[tts] warn: no pude leer samplerate del dispositivo ({exc})")

            try:
                sd.check_output_settings(device=sd.default.device[1], samplerate=samplerate, channels=1)
            except Exception as exc:
                print(f"[tts] error: salida no soporta {samplerate} Hz ({exc})")

            if not return_audio and not self._stop_flag:
                self._play_audio(audio, samplerate)
        if not chunks:
            print("[tts] no se generó audio en la tubería")
            return None
        merged = np.concatenate(chunks)
        return merged if return_audio else None

    def _play_audio(self, audio: np.ndarray, samplerate: int) -> None:
        playback = (self.config.playback or "sd+aplay").lower()
        print(f"[tts] playback={playback}")
        if "sd" in playback:
            try:
                print("[tts] usando sounddevice...")
                if self._output_device is None:
                    sd.play(audio, samplerate=samplerate)
                else:
                    sd.play(audio, samplerate=samplerate, device=self._output_device)
                sd.wait()
            except Exception as exc:
                print(f"[tts] error sounddevice: {exc}")
        if "aplay" in playback:
            try:
                wav_path = Path("/tmp/kokoro_last.wav")
                import soundfile as sf
                sf.write(wav_path, audio, samplerate)
                print(f"[tts] usando aplay: {wav_path}")
                self._aplay_proc = subprocess.Popen(
                    ["aplay", str(wav_path)],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                stdout, stderr = self._aplay_proc.communicate()
                if self._aplay_proc.returncode != 0:
                    print(f"[tts] aplay error rc={self._aplay_proc.returncode} stderr={stderr.strip()}")
            except Exception as exc:
                print(f"[tts] error aplay: {exc}")

    def stop(self) -> None:
        self._stop_flag = True
        try:
            sd.stop()
        except Exception:
            pass
        try:
            if self._aplay_proc and self._aplay_proc.poll() is None:
                self._aplay_proc.terminate()
        except Exception:
            pass

    def _resample(self, audio: np.ndarray, src_rate: int, dst_rate: int) -> np.ndarray:
        if src_rate == dst_rate or audio.size == 0:
            return audio
        duration = audio.size / float(src_rate)
        dst_len = max(1, int(duration * dst_rate))
        src_x = np.linspace(0.0, duration, num=audio.size, endpoint=False)
        dst_x = np.linspace(0.0, duration, num=dst_len, endpoint=False)
        return np.interp(dst_x, src_x, audio).astype(np.float32)

    def _speed_up(self, audio: np.ndarray, speed: float) -> np.ndarray:
        if speed <= 0:
            return audio
        if speed == 1.0 or audio.size == 0:
            return audio
        # Time-stretch (keeps pitch) using Rubber Band if available.
        if self.config.time_stretch and self.config.stretch_engine == "rubberband" and pyrb is not None:
            try:
                return pyrb.time_stretch(audio.astype(np.float32), self.config.sample_rate, speed)
            except Exception as exc:
                print(f"[tts] warn: rubberband fallo ({exc}), probando librosa")
        # Time-stretch (keeps pitch) using librosa if available.
        if self.config.time_stretch and librosa is not None:
            try:
                return librosa.effects.time_stretch(audio.astype(np.float32), rate=speed)
            except Exception as exc:
                print(f"[tts] warn: time_stretch fallo ({exc}), usando resample simple")
        # Fallback: resample (changes pitch).
        src_len = audio.size
        dst_len = max(1, int(src_len / speed))
        src_x = np.linspace(0.0, 1.0, num=src_len, endpoint=False)
        dst_x = np.linspace(0.0, 1.0, num=dst_len, endpoint=False)
        return np.interp(dst_x, src_x, audio).astype(np.float32)
