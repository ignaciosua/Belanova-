import os
from dataclasses import dataclass

from dotenv import load_dotenv
from belanova.paths import PROJECT_ROOT

load_dotenv(PROJECT_ROOT / ".env")


def _get_env(name: str, default: str | None = None) -> str:
    value = os.getenv(name, default)
    if value is None:
        raise RuntimeError(f"Missing required env var: {name}")
    return value


@dataclass
class Settings:
    # OpenRouter
    openrouter_api_key: str = _get_env("OPENROUTER_API_KEY")
    openrouter_base_url: str = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    openrouter_model: str = os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini")
    openrouter_provider: str = os.getenv("OPENROUTER_PROVIDER", "")

    # Audio
    sample_rate: int = int(os.getenv("AUDIO_SAMPLE_RATE", "16000"))
    ptt_key: str = os.getenv("PTT_KEY", "space")
    audio_output_device: str = os.getenv("AUDIO_OUTPUT_DEVICE", "")

    # Whisper
    whisper_provider: str = os.getenv("WHISPER_PROVIDER", "auto").lower()
    whisper_model_id: str = os.getenv("WHISPER_MODEL_ID", "openai/whisper-large-v3-turbo")
    whisper_language: str = os.getenv("WHISPER_LANGUAGE", "spanish")
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_base_url: str = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    whisper_api_model: str = os.getenv("WHISPER_API_MODEL", "whisper-1")
    whisper_api_timeout_s: int = int(os.getenv("WHISPER_API_TIMEOUT_S", "60"))
    asr_warmup: bool = os.getenv("ASR_WARMUP", "1") == "1"

    # Kokoro
    kokoro_lang_code: str = os.getenv("KOKORO_LANG_CODE", "e")
    kokoro_voice: str = os.getenv("KOKORO_VOICE", "ef_dora")
    kokoro_sample_rate: int = int(os.getenv("KOKORO_SAMPLE_RATE", "24000"))
    tts_playback: str = os.getenv("TTS_PLAYBACK", "sd+aplay")
    tts_speed: float = float(os.getenv("TTS_SPEED", "1.0"))
    tts_time_stretch: bool = os.getenv("TTS_TIME_STRETCH", "1") == "1"
    tts_stretch_engine: str = os.getenv("TTS_STRETCH_ENGINE", "rubberband")
    tts_simplify: bool = os.getenv("TTS_SIMPLIFY", "1") == "1"
    max_context_tokens: int = int(os.getenv("MAX_CONTEXT_TOKENS", "90000"))
    summary_target_tokens: int = int(os.getenv("SUMMARY_TARGET_TOKENS", "6000"))

    # Tools / safety
    allow_shell: bool = os.getenv("ALLOW_SHELL", "1") == "1"
    max_tool_iters: int = int(os.getenv("MAX_TOOL_ITERS", "8"))


settings = Settings()
