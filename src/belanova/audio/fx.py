import subprocess
import threading
import time
from pathlib import Path
import shutil


ROOT_DIR = Path(__file__).parent.resolve()
TMP_DIR = Path("/tmp")


def _wav_path_for(mp3_path: Path) -> Path:
    return TMP_DIR / (mp3_path.stem + ".wav")


def ensure_wav(mp3_path: Path) -> Path:
    wav_path = _wav_path_for(mp3_path)
    if wav_path.exists() and wav_path.stat().st_mtime >= mp3_path.stat().st_mtime:
        return wav_path
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(mp3_path),
        "-ac",
        "1",
        "-ar",
        "44100",
        str(wav_path),
    ]
    subprocess.run(cmd, capture_output=True, text=True, check=False)
    return wav_path


def play_wav_blocking(wav_path: Path, stop_event: threading.Event | None = None) -> None:
    proc = subprocess.Popen(["aplay", str(wav_path)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    while True:
        if stop_event and stop_event.is_set():
            proc.terminate()
            break
        if proc.poll() is not None:
            break
        time.sleep(0.05)


def loop_mp3(mp3_path: Path, stop_event: threading.Event, volume: float = 0.85) -> None:
    ffplay = shutil.which("ffplay")
    if ffplay:
        # ffplay can loop seamlessly in a single process
        proc = subprocess.Popen(
            [
                ffplay,
                "-nodisp",
                "-autoexit",
                "-loglevel",
                "error",
                "-loop",
                "0",
                "-af",
                f"volume={volume}",
                str(mp3_path),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        while proc.poll() is None:
            if stop_event.is_set():
                proc.terminate()
                try:
                    proc.wait(timeout=0.5)
                except Exception:
                    proc.kill()
                break
            time.sleep(0.05)
        return

    # Fallback: loop via aplay (can introduce small gaps)
    wav_path = ensure_wav(mp3_path)
    while not stop_event.is_set():
        play_wav_blocking(wav_path, stop_event=stop_event)
        time.sleep(0.05)
