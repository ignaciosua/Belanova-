import os

from belanova.core.config import settings
from belanova.tts.kokoro import KokoroTTS, TTSConfig


def main() -> int:
    print(f"[test] AUDIO_OUTPUT_DEVICE={settings.audio_output_device!r}")
    try:
        import sounddevice as sd
        print("[test] devices:")
        for idx, dev in enumerate(sd.query_devices()):
            if dev.get("max_output_channels", 0) > 0:
                print(f"  {idx}: {dev.get('name')} (rate={dev.get('default_samplerate')})")
        print("  default:", sd.default.device)
    except Exception as exc:
        print(f"[test] no pude listar dispositivos: {exc}")

    tts = KokoroTTS(
        TTSConfig(
            lang_code=settings.kokoro_lang_code,
            voice=settings.kokoro_voice,
            sample_rate=settings.kokoro_sample_rate,
            output_device=settings.audio_output_device,
            speed=settings.tts_speed,
            time_stretch=settings.tts_time_stretch,
            stretch_engine=settings.tts_stretch_engine,
        )
    )
    text = "Hola. Esta es una prueba de voz de Kokoro en español."
    print(f"[test] texto={text!r}")
    print("[test] generando y reproduciendo audio...")
    audio = tts.speak(text, return_audio=True)
    if audio is None:
        print("[test] no se generó audio")
        return 1
    try:
        import soundfile as sf
        wav_path = "/tmp/kokoro_test.wav"
        sf.write(wav_path, audio, settings.kokoro_sample_rate)
        print(f"[test] wav guardado en {wav_path}")
        try:
            import sounddevice as sd
            print("[test] reproduciendo wav con sounddevice (default)...")
            sd.play(audio, samplerate=settings.kokoro_sample_rate)
            sd.wait()
        except Exception as exc:
            print(f"[test] error reproduciendo con sounddevice: {exc}")
        try:
            import subprocess
            print("[test] reproduciendo wav con aplay...")
            subprocess.run(["aplay", wav_path], check=False)
        except Exception as exc:
            print(f"[test] error reproduciendo con aplay: {exc}")
    except Exception as exc:
        print(f"[test] no pude guardar/reproducir wav: {exc}")
    print("[test] listo")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
