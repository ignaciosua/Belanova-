import time
import numpy as np
import sounddevice as sd


def tone(freq=440.0, duration=1.0, samplerate=48000):
    t = np.linspace(0, duration, int(samplerate * duration), endpoint=False)
    return 0.2 * np.sin(2 * np.pi * freq * t).astype(np.float32)


def main() -> int:
    devices = sd.query_devices()
    print("[scan] probando salidas de audio...")
    for idx, dev in enumerate(devices):
        if dev.get("max_output_channels", 0) <= 0:
            continue
        name = dev.get("name")
        rate = int(dev.get("default_samplerate", 48000))
        print(f"\n[scan] device {idx}: {name} (rate={rate})")
        audio = tone(freq=440.0, duration=1.0, samplerate=rate)
        try:
            sd.play(audio, samplerate=rate, device=idx)
            sd.wait()
        except Exception as exc:
            print(f"[scan] error en device {idx}: {exc}")
        time.sleep(0.3)
    print("\n[scan] terminado. Dime el ID donde escuchaste el tono.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
