from dataclasses import dataclass
import io
from typing import Any

import numpy as np
import requests
import soundfile as sf
import torch
from transformers import AutoModelForSpeechSeq2Seq, AutoProcessor, pipeline
from transformers.utils import logging as hf_logging


@dataclass
class Transcription:
    text: str


class WhisperTurboASR:
    def __init__(self, model_id: str, language: str = "spanish"):
        self.model_id = model_id
        self.language = language
        self.device, self.device_idx, self.dtype = self._select_device()
        print(f"[asr] device={self.device} dtype={self.dtype}")

        hf_logging.set_verbosity_error()

        model_kwargs = {
            "low_cpu_mem_usage": True,
            "use_safetensors": True,
        }
        try:
            model_kwargs["dtype"] = self.dtype
            model = AutoModelForSpeechSeq2Seq.from_pretrained(self.model_id, **model_kwargs)
        except TypeError:
            model_kwargs.pop("dtype", None)
            model_kwargs["torch_dtype"] = self.dtype
            model = AutoModelForSpeechSeq2Seq.from_pretrained(self.model_id, **model_kwargs)
        model.to(self.device)

        processor = AutoProcessor.from_pretrained(self.model_id)
        self._pipe = pipeline(
            "automatic-speech-recognition",
            model=model,
            tokenizer=processor.tokenizer,
            feature_extractor=processor.feature_extractor,
            device=self.device_idx,
            ignore_warning=True,
        )

    def _select_device(self):
        if torch.cuda.is_available():
            return "cuda:0", 0, torch.float16
        if torch.backends.mps.is_available():
            return "mps", 0, torch.float16
        return "cpu", -1, torch.float32

    def transcribe(self, audio, sample_rate: int) -> Transcription:
        if audio is None or len(audio) == 0:
            return Transcription(text="")

        result = self._pipe(
            {"array": audio, "sampling_rate": sample_rate},
            chunk_length_s=30,
            generate_kwargs={"task": "transcribe", "language": self.language},
        )
        text = result.get("text", "").strip()
        return Transcription(text=text)

    def warmup(self, sample_rate: int = 16000) -> None:
        silence = torch.zeros(sample_rate // 2, dtype=torch.float32).numpy()
        _ = self.transcribe(silence, sample_rate)


class OpenAIWhisperASR:
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        language: str = "spanish",
        timeout_s: int = 60,
    ):
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is not configured for ASR API")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.language = language
        self.timeout_s = timeout_s
        self._endpoint = f"{self.base_url}/audio/transcriptions"
        print(f"[asr] provider=openai model={self.model} endpoint={self._endpoint}")

    def _api_language(self) -> str | None:
        lang = (self.language or "").strip().lower()
        if not lang:
            return None
        aliases = {
            "spanish": "es",
            "english": "en",
        }
        if lang in aliases:
            return aliases[lang]
        if len(lang) == 2:
            return lang
        return None

    def transcribe(self, audio: Any, sample_rate: int) -> Transcription:
        if audio is None or len(audio) == 0:
            return Transcription(text="")

        samples = np.asarray(audio, dtype=np.float32)
        wav = io.BytesIO()
        sf.write(wav, samples, sample_rate, format="WAV", subtype="PCM_16")
        wav.seek(0)

        headers = {"Authorization": f"Bearer {self.api_key}"}
        data = {"model": self.model}
        lang = self._api_language()
        if lang:
            data["language"] = lang
        files = {"file": ("audio.wav", wav, "audio/wav")}

        try:
            response = requests.post(
                self._endpoint,
                headers=headers,
                data=data,
                files=files,
                timeout=self.timeout_s,
            )
        except Exception as exc:
            raise RuntimeError(f"ASR API connection error: {exc}") from exc

        if not response.ok:
            snippet = response.text[:300].replace("\n", " ").strip()
            raise RuntimeError(f"ASR API HTTP {response.status_code}: {snippet}")

        payload = response.json()
        text = str(payload.get("text", "")).strip()
        return Transcription(text=text)

    def warmup(self, sample_rate: int = 16000) -> None:
        # No preload needed for API mode.
        return None


def create_asr(settings: Any):
    provider = (getattr(settings, "whisper_provider", "auto") or "auto").strip().lower()
    if provider not in {"auto", "local", "openai"}:
        print(f"[asr] unknown whisper_provider ({provider}), using auto")
        provider = "auto"

    has_openai_key = bool(getattr(settings, "openai_api_key", "").strip())
    use_openai = has_openai_key if provider == "auto" else provider == "openai"

    if use_openai and has_openai_key:
        return OpenAIWhisperASR(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            model=settings.whisper_api_model,
            language=settings.whisper_language,
            timeout_s=settings.whisper_api_timeout_s,
        )

    if use_openai and not has_openai_key:
        print("[asr] OPENAI_API_KEY not configured; falling back to local model")

    return WhisperTurboASR(settings.whisper_model_id, language=settings.whisper_language)
