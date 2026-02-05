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
        print(f"[test] could not list devices: {exc}")

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
    text = "Hello. This is an English Kokoro voice test."
    print(f"[test] text={text!r}")
    print("[test] generating and playing audio...")
    audio = tts.speak(text, return_audio=True)
    if audio is None:
        print("[test] no audio was generated")
        return 1
    try:
        import soundfile as sf
        wav_path = "/tmp/kokoro_test.wav"
        sf.write(wav_path, audio, settings.kokoro_sample_rate)
        print(f"[test] wav saved at {wav_path}")
        try:
            import sounddevice as sd
            print("[test] playing wav with sounddevice (default)...")
            sd.play(audio, samplerate=settings.kokoro_sample_rate)
            sd.wait()
        except Exception as exc:
            print(f"[test] error playing with sounddevice: {exc}")
        try:
            import subprocess
            print("[test] playing wav with aplay...")
            subprocess.run(["aplay", wav_path], check=False)
        except Exception as exc:
            print(f"[test] error playing with aplay: {exc}")
    except Exception as exc:
        print(f"[test] could not save/play wav: {exc}")
    print("[test] done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
