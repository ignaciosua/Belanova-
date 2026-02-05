import time

from belanova.core.agent import AgentConfig, OpenRouterAgent
from belanova.asr.whisper_turbo import create_asr
from belanova.audio.ptt import PushToTalkRecorder
from belanova.core.config import settings
from belanova.tts.kokoro import KokoroTTS, TTSConfig
from belanova.tools.executor import ToolExecutor


def main() -> int:
    print("[diag] iniciando self-check...")
    print("[diag] habla mientras mantienes la tecla push-to-talk y suelta para enviar.")

    asr = create_asr(settings)

    tts = None
    try:
        tts = KokoroTTS(
            TTSConfig(
                lang_code=settings.kokoro_lang_code,
                voice=settings.kokoro_voice,
                sample_rate=settings.kokoro_sample_rate,
                output_device=settings.audio_output_device,
                playback=settings.tts_playback,
                speed=settings.tts_speed,
                time_stretch=settings.tts_time_stretch,
                stretch_engine=settings.tts_stretch_engine,
            )
        )
        print("[diag] tts: ok")
    except Exception as exc:
        print(f"[diag] tts: deshabilitado ({exc})")

    def narrate(text: str) -> None:
        print(f"[accion] {text}")
        if tts is not None:
            tts.speak(text)

    tools = ToolExecutor(allow_shell=False, narrator=narrate)
    print(f"[diag] openrouter_base_url={settings.openrouter_base_url}")
    print(f"[diag] openrouter_model={settings.openrouter_model}")
    agent = OpenRouterAgent(
        AgentConfig(
            api_key=settings.openrouter_api_key,
            base_url=settings.openrouter_base_url,
            model=settings.openrouter_model,
            max_tool_iters=2,
            provider=settings.openrouter_provider,
        ),
        tools,
    )

    recorder = PushToTalkRecorder(settings.ptt_key, settings.sample_rate)
    chunk = recorder.record_once()
    if chunk is None or chunk.samples.size == 0:
        print("[diag] audio: fallo o vacío")
        return 1
    print("[diag] audio: ok")

    transcription = asr.transcribe(chunk.samples, chunk.sample_rate)
    print(f"[diag] asr: {transcription.text!r}")
    if not transcription.text:
        return 1

    response = agent.run(
        "Responde con una frase corta confirmando que OpenRouter funciona."
    )
    print(f"[diag] openrouter: {response}")
    if tts is not None:
        tts.speak("Diagnóstico completado")
    print("[diag] ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
