import sys
import threading
import re
import json
import time
from pathlib import Path
from pynput import keyboard

from belanova.core.agent import AgentConfig, OpenRouterAgent
from belanova.asr.whisper_turbo import create_asr
from belanova.audio.ptt import PushToTalkRecorder
from belanova.core.config import settings
from belanova.tts.kokoro import KokoroTTS, TTSConfig
from belanova.tools.executor import ToolExecutor
from belanova.audio.fx import loop_mp3, ensure_wav, play_wav_blocking
from belanova.paths import PROJECT_ROOT


def main() -> int:
    print(f"[runtime] python={sys.executable}")
    print(f"[runtime] version={sys.version.split()[0]}")
    print(f"[runtime] AUDIO_OUTPUT_DEVICE={settings.audio_output_device!r}")
    print(f"[runtime] TTS_PLAYBACK={settings.tts_playback!r}")

    asr = create_asr(settings)
    if settings.asr_warmup:
        print("[asr] warmup...")
        asr.warmup(settings.sample_rate)

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
        print(f"[tts] playback={settings.tts_playback}")
    except Exception as exc:
        print(f"[tts] deshabilitado: {exc}")

    def _extract_json(text: str):
        # Try fenced JSON block
        block = re.search(r"```json\s*(.*?)\s*```", text, flags=re.S | re.I)
        if block:
            try:
                return json.loads(block.group(1))
            except Exception:
                pass
        # Try raw JSON
        t = text.strip()
        if (t.startswith("{") and t.endswith("}")) or (t.startswith("[") and t.endswith("]")):
            try:
                return json.loads(t)
            except Exception:
                pass
        return None

    def _summarize_json(obj, max_items=10):
        if isinstance(obj, dict):
            parts = []
            for k, v in obj.items():
                parts.append(f"{k}: {v}")
            return "; ".join(parts)
        if isinstance(obj, list):
            items = []
            for i, item in enumerate(obj[:max_items], 1):
                items.append(f"item {i}: {_summarize_json(item)}")
            if len(obj) > max_items:
                items.append(f"y {len(obj) - max_items} mas")
            return "; ".join(items)
        return str(obj)

    def simplify_for_tts(text: str) -> str:
        json_obj = _extract_json(text)
        t = _summarize_json(json_obj) if json_obj is not None else text
        # If this looks like RSS feed output, keep only fecha/resumen lines for TTS
        if "Feed:" in t and ("Resumen:" in t or "Fecha:" in t):
            kept = []
            for line in t.splitlines():
                stripped = line.strip()
                low = stripped.lower()
                if low.startswith("resumen:") or low.startswith("fecha:"):
                    kept.append(stripped)
            if kept:
                t = " ".join(kept)
        # Remove repeated asterisks explicitly
        t = re.sub(r"\*+", " ", t)
        t = re.sub(r"```.*?```", " ", t, flags=re.S)
        t = re.sub(r"`([^`]+)`", r"\1", t)
        t = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", t)
        # Remove explicit Link lines and URLs before punctuation filtering
        t = re.sub(r"(?im)^\s*link:\s*.*$", " ", t)
        t = re.sub(r"(?i)\b(link|url|href)\s*:\s*\S+", " ", t)
        t = re.sub(r"\bhttps?://\S+", " ", t)
        t = re.sub(r"\bwww\.\S+", " ", t)
        t = re.sub(r"^\s*#+\s*", "", t, flags=re.M)
        t = re.sub(r"^\s*[-*+]\s+", "", t, flags=re.M)
        t = re.sub(r"^\s*\d+\.\s+", "", t, flags=re.M)
        t = re.sub(r"[\*_~>#|{}\[\]<>]", " ", t)
        # Allow only alphanumeric + common punctuation for TTS clarity
        t = re.sub(r"[^0-9A-Za-záéíóúÁÉÍÓÚñÑüÜ\s.,¿?¡!;:\-()]", " ", t)
        t = re.sub(r"\s+", " ", t).strip()
        return t

    tts_lock = threading.Lock()
    tts_call_id = 0
    agent_inflight = threading.Lock()

    def speak_tts(text: str, tag: str = "generic") -> None:
        if tts is None:
            return
        nonlocal tts_call_id
        tts_call_id += 1
        call_id = tts_call_id
        if tts_lock.locked():
            print(f"[tts] warn: lock already held (call={call_id} tag={tag})")
        with tts_lock:
            t0 = time.perf_counter()
            print(f"[tts] start call={call_id} tag={tag}")
            pause_thinking()
            spoken = simplify_for_tts(text) if settings.tts_simplify else text
            print(f"[tts_text] {spoken}")
            tts.speak(spoken)
            dt = time.perf_counter() - t0
            print(f"[tts] end call={call_id} tag={tag} dur={dt:.2f}s")
        resume_thinking_if_needed()

    def narrate(text: str) -> None:
        print(f"[accion] {text}")
        if tts is not None:
            speak_tts(text, tag="action")

    recorder = PushToTalkRecorder(settings.ptt_key, settings.sample_rate)
    ptt_key = recorder._key
    ptt_interrupt = threading.Event()
    thinking_mp3 = PROJECT_ROOT / "assets/audio/thinkingloop.mp3"
    error_mp3 = PROJECT_ROOT / "assets/audio/error.mp3"

    thinking_stop = None
    thinking_thread = None
    thinking_should_run = False

    def stop_thinking():
        nonlocal thinking_stop, thinking_thread, thinking_should_run
        thinking_should_run = False
        if thinking_stop:
            thinking_stop.set()
            print("[thinking] stop")
        if thinking_thread:
            thinking_thread.join(timeout=1)
        try:
            import subprocess
            subprocess.run(["pkill", "-f", "thinkingloop.mp3"], check=False)
        except Exception:
            pass
        thinking_stop = None
        thinking_thread = None

    def start_thinking():
        nonlocal thinking_stop, thinking_thread, thinking_should_run
        thinking_should_run = True
        if tts_lock.locked():
            print("[thinking] defer (tts active)")
            return
        if thinking_mp3.exists() and thinking_thread is None:
            thinking_stop = threading.Event()
            thinking_thread = threading.Thread(target=loop_mp3, args=(thinking_mp3, thinking_stop, 0.50), daemon=True)
            thinking_thread.start()
            print("[thinking] start")

    def pause_thinking():
        nonlocal thinking_stop, thinking_thread
        if thinking_stop:
            thinking_stop.set()
            print("[thinking] pause")
        if thinking_thread:
            thinking_thread.join(timeout=1)
        thinking_stop = None
        thinking_thread = None

    def resume_thinking_if_needed():
        if thinking_should_run:
            start_thinking()

    def confirm_action(summary: str) -> bool:
        prompt = (
            f"Voy a realizar la siguiente acción: {summary}. "
            "Di 'Confirmar' para continuar o 'Cancelar' para abortar."
        )
        print(f"[confirm] {summary}")
        stop_thinking()
        if tts is not None:
            speak_tts(prompt, tag="confirm")
        print("[confirm] Mantén presionada la tecla y di Confirmar o Cancelar.")
        chunk = recorder.record_once(start_immediately=True)
        if chunk is None or chunk.samples.size == 0:
            return False
        reply = asr.transcribe(chunk.samples, chunk.sample_rate).text.lower()
        print(f"[confirm] respuesta={reply!r}")
        if "confirm" in reply:
            return True
        if "cancel" in reply:
            return False
        return False

    def on_tool_start(name: str, args: dict) -> None:
        # Start thinking while executing intermediate actions
        print(f"[tool] start {name} {args}")
        start_thinking()

    def on_tool_end(name: str, args: dict, result) -> None:
        print(f"[tool] end {name} ok={result.ok}")
        stop_thinking()

    tools = ToolExecutor(
        allow_shell=settings.allow_shell,
        narrator=narrate,
        confirmer=confirm_action,
        on_tool_start=on_tool_start,
        on_tool_end=on_tool_end,
    )
    agent = OpenRouterAgent(
        AgentConfig(
            api_key=settings.openrouter_api_key,
            base_url=settings.openrouter_base_url,
            model=settings.openrouter_model,
            max_tool_iters=settings.max_tool_iters,
            provider=settings.openrouter_provider,
        ),
        tools,
    )

    def _global_on_press(key):
        if key == ptt_key and tts is not None:
            tts.stop()
            print("[tts] stop (global ptt)")
            ptt_interrupt.set()
        return True

    global_listener = keyboard.Listener(on_press=_global_on_press)
    global_listener.start()

    system_base = (
        "Eres un agente que puede usar herramientas para realizar acciones reales. "
        "Responde en español. Usa herramientas cuando haga falta. "
        "Si usas herramientas, espera sus resultados antes de continuar."
    )
    system_context = ""
    context_path = PROJECT_ROOT / "docs/context/sistema_belanova.md"
    if context_path.exists():
        try:
            system_context = context_path.read_text(encoding="utf-8")
        except Exception:
            system_context = ""

    history: list[dict[str, str]] = [
        {"role": "system", "content": system_base},
    ]
    if system_context:
        history.append({"role": "system", "content": f"Project context:\n{system_context}"})

    def estimate_tokens(messages: list[dict[str, str]]) -> int:
        # Approx: 4 chars per token + small overhead per message
        chars = sum(len(m.get("content", "")) for m in messages)
        return max(1, chars // 4 + len(messages) * 8)

    def summarize_history() -> None:
        nonlocal history
        summary_prompt = [
            {
                "role": "system",
                "content": (
                    "Resume la conversación de forma completa y útil para continuar el trabajo. "
                    "Incluye decisiones clave, configuraciones, errores encontrados y soluciones. "
                    "Sé conciso pero no omitas detalles importantes."
                ),
            },
            {"role": "user", "content": "\n".join([m["content"] for m in history if m["role"] != "system"])},
        ]
        summary, model_used = agent.chat(summary_prompt, use_tools=False)
        print(f"[resumen] modelo={model_used}")
        history = [
            history[0],
            {"role": "system", "content": f"Resumen de contexto:\n{summary}"},
        ]

    print("Listo. Mantén presionada la tecla para hablar y suelta para enviar.")
    print(f"Tecla push-to-talk: {settings.ptt_key}. Presiona ESC para salir.")
    if tts is not None:
        speak_tts(f"Tecla push to talk: {settings.ptt_key}", tag="startup")

    while True:
        def on_ptt_press():
            if tts is not None:
                tts.stop()
                print("[tts] stop (ptt)")

        start_immediately = ptt_interrupt.is_set()
        if start_immediately:
            ptt_interrupt.clear()
        chunk = recorder.record_once(on_press=on_ptt_press, start_immediately=start_immediately)
        if chunk is None:
            break
        if chunk.samples.size == 0:
            continue

        transcription = asr.transcribe(chunk.samples, chunk.sample_rate)
        if not transcription.text:
            continue

        print(f"[tu] {transcription.text}")
        history.append({"role": "user", "content": transcription.text})
        if estimate_tokens(history) >= settings.max_context_tokens:
            summarize_history()
        # Use full history when calling the agent
        if not agent_inflight.acquire(blocking=False):
            print("[agent] ya hay una llamada en curso, ignorando este input")
            continue
        start_thinking()
        try:
            print("[agent] call")
            response = agent.run(transcription.text, messages=history)
            print("[agent] done")
        except Exception as exc:
            stop_thinking()
            agent_inflight.release()
            print(f"[error] {exc}")
            if error_mp3.exists():
                wav = ensure_wav(error_mp3)
                play_wav_blocking(wav)
            continue
        stop_thinking()
        agent_inflight.release()
        if response:
            history.append({"role": "assistant", "content": response})
            print(f"[modelo] {agent.get_last_model()}")
            print(f"[agente] {response}")
            if tts is not None:
                stop_thinking()
                speak_tts(response, tag="response")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
