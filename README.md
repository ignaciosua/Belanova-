# Belanova (Whisper + OpenRouter + Kokoro)

## Architecture (by layer)
- Application code: `src/belanova/`
- Installation/ops scripts: `scripts/`
- Core workspace skills: `skills/` (`macro-agent`, `region-capture`)
- Portable MCP skill bridge: `mcp/skill-bridge/`
- Runtime audio assets: `assets/audio/`
- System context: `docs/context/sistema_belanova.md`

See `docs/ARCHITECTURE.md` for details.

## Requirements
- Linux Mint 21.3 (tested)
- Python 3.10+
- NVIDIA GPU recommended (optional)
- System packages: `espeak-ng` and `libportaudio2`

Suggested Linux install:

```bash
sudo apt-get update
sudo apt-get install -y espeak-ng libportaudio2
```

## Configuration
Create `.env` with at least:

```env
OPENROUTER_API_KEY=...
OPENROUTER_MODEL=openai/gpt-4o-mini
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_PROVIDER=openai

# Optional ASR API mode
OPENAI_API_KEY=
OPENAI_BASE_URL=https://api.openai.com/v1
WHISPER_PROVIDER=auto      # auto|openai|local
WHISPER_API_MODEL=whisper-1
WHISPER_API_TIMEOUT_S=60

# Local Whisper fallback
WHISPER_MODEL_ID=openai/whisper-large-v3-turbo
WHISPER_LANGUAGE=spanish
ASR_WARMUP=1

PTT_KEY=space
AUDIO_OUTPUT_DEVICE=

KOKORO_LANG_CODE=e
KOKORO_VOICE=ef_dora
KOKORO_SAMPLE_RATE=24000
TTS_PLAYBACK=sd+aplay
TTS_SPEED=1.0
TTS_TIME_STRETCH=1
TTS_STRETCH_ENGINE=rubberband
TTS_SIMPLIFY=1

MAX_CONTEXT_TOKENS=90000
SUMMARY_TARGET_TOKENS=6000
ALLOW_SHELL=1
MAX_TOOL_ITERS=8
```

ASR behavior:
- `WHISPER_PROVIDER=auto` (default): uses OpenAI API when `OPENAI_API_KEY` is set; otherwise uses local Whisper.
- `WHISPER_PROVIDER=openai`: prefers OpenAI API (falls back to local if no key).
- `WHISPER_PROVIDER=local`: always local Whisper.

## One-command installation (recommended)

### Linux client setup
Installs system + Python deps, configures MCP/skill-bridge, syncs core skills, and creates launchers:

```bash
bash scripts/client_linux_install.sh
```

### Standard setup

```bash
bash scripts/install_all.sh
```

Options:

```bash
# Include apt system dependencies
bash scripts/install_all.sh --install-system-deps

# Use current Python without venv
python scripts/bootstrap.py --no-venv

# Force default PyPI torch build (e.g., for GPU setup)
python scripts/bootstrap.py --torch default

# Skip external skill sync
python scripts/bootstrap.py --no-sync-skills
```

## Makefile shortcuts

```bash
make setup
make setup-client
make sync-skills
make run
```

Useful targets:
- `make setup`: full bootstrap
- `make setup-client`: one-command Linux client setup
- `make sync-skills`: sync only core skills
- `make sync-skills-all`: sync all detected skills
- `make doctor`: run diagnostics
- `make tts-test`: quick TTS test

## Run

```bash
belanova
```

Alternative:

```bash
make run
```

Push-to-talk mode: hold configured key, release to send.

## Self-check

```bash
belanova-doctor
```

## TTS test

```bash
belanova-tts-test
```

## Notes
- `ALLOW_SHELL=1` allows tool shell execution.
- If `nvidia-smi` fails, fix NVIDIA driver first.
- `pynput` may require X11; global hotkeys can fail on Wayland.

## Runtime status sounds
If `assets/audio/thinkingloop.mp3` and `assets/audio/error.mp3` exist:
- `thinkingloop.mp3` loops while waiting for agent response.
- `error.mp3` plays when an error occurs.

Requires `ffmpeg` and `aplay`.

## MCP Skill Bridge
This repo ships a portable bridge at `mcp/skill-bridge/skill_bridge.py`.
Bootstrap installs it into VS Code MCP config and registers `skill-bridge` in `mcp.json`.

Default core skill sync includes `macro-agent` and `region-capture`.

Optional env vars:
- `MCP_CONFIG_PATH` (default `~/.config/Code/User/mcp.json`)
- `MCP_TIMEOUT_S` (default 30)

Available tools:
- `mcp_list_skills`
- `mcp_get_skill_help`
- `mcp_run_skill`
- `mcp_refresh_skills`

## Utility: Merge PDFs
Script: `scripts/merge_pdfs.py`

```bash
python scripts/merge_pdfs.py -o output.pdf a.pdf b.pdf
python scripts/merge_pdfs.py -o output.pdf ./folder_with_pdfs --recursive
```

## Utility: 2 pages into 1 (2-up)
Script: `scripts/two_up_pdf.py`

```bash
python scripts/two_up_pdf.py input.pdf -o output.pdf
```
