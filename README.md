# Asistente de voz (Whisper Turbo + OpenRouter + Kokoro)

## Arquitectura (ordenada por capas)
- Código de aplicación: `src/belanova/`
- Scripts de instalación/ops: `scripts/`
- Skills core del workspace: `skills/` (actualmente `macro-agent` y `region-capture`)
- Skill bridge MCP portable: `mcp/skill-bridge/`
- Assets de audio runtime: `assets/audio/`
- Contexto del sistema: `docs/context/sistema_belanova.md`

Detalle completo en `docs/ARCHITECTURE.md`.

## Requisitos
- Linux Mint 21.3 (probado)
- Python 3.10+ (detectado en tu máquina: `Python 3.12.4` desde `/home/neo/miniconda3/bin/python`)
- GPU NVIDIA (recomendado). El uso real depende de que el driver CUDA esté funcionando.
- Paquetes del sistema: `espeak-ng` (Kokoro) y `portaudio` (sounddevice)

Instalación sugerida en Linux:

```bash
sudo apt-get update
sudo apt-get install -y espeak-ng libportaudio2
```

## Configuración
Crea un `.env` con las variables:

```
OPENROUTER_API_KEY=...
OPENROUTER_MODEL=...   # por ejemplo: openai/gpt-4o-mini (default si no se define)
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_PROVIDER=openai
OPENAI_API_KEY=...     # opcional: si existe, ASR usa API de OpenAI
OPENAI_BASE_URL=https://api.openai.com/v1
WHISPER_PROVIDER=auto  # auto|openai|local
WHISPER_API_MODEL=whisper-1
WHISPER_API_TIMEOUT_S=60
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

Comportamiento ASR:
- `WHISPER_PROVIDER=auto` (default): si hay `OPENAI_API_KEY`, usa API; si no, usa modelo local.
- `WHISPER_PROVIDER=openai`: intenta API (si falta key, hace fallback a local).
- `WHISPER_PROVIDER=local`: fuerza modelo local.

Voces disponibles (ejemplos en español):
- `lang_code`: `e`
- `voice`: `ef_dora`, `em_alex`

## Instalación de dependencias

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Instalación 1 comando (recomendada)

### Cliente Linux (production-ready)
Instala dependencias del sistema + Python, configura MCP/skill-bridge, crea launchers globales (`belanova`, `belanova-doctor`, `belanova-tts-test`) y deja todo listo:

```bash
bash scripts/client_linux_install.sh
```

Nota: el instalador usa `torch` en modo CPU por defecto (más liviano para cliente).

### Instalación estándar
Instala dependencias Python, crea `.venv`, configura `mcp.json`, instala `skill-bridge`, y sincroniza solo los skills **core** al workspace (`macro-agent` y `region-capture`):

```bash
bash scripts/install_all.sh
```

Opcional (usar Python actual, sin venv):

```bash
python scripts/bootstrap.py --no-venv
```

Opcional (incluye paquetes del sistema vía `apt-get`):

```bash
bash scripts/install_all.sh --install-system-deps
```

Opcional (forzar `torch` estándar de PyPI, por ejemplo para GPU):

```bash
python scripts/bootstrap.py --torch default
```

Opcional (no sincronizar skills externos):

```bash
python scripts/bootstrap.py --no-sync-skills
```

## Makefile (atajos)

```bash
make setup
make setup-client
make sync-skills
make run
```

Targets útiles:
- `make setup`: bootstrap completo
- `make setup-client`: instalación 1 comando para cliente Linux
- `make sync-skills`: trae solo skills core al `skills/` del repo
- `make sync-skills-all`: trae todas las skills detectadas (opcional)
- `make doctor`: corre diagnóstico
- `make tts-test`: prueba TTS

### Conda (tu caso)
Estás en el entorno base de conda y el `python` activo es `/home/neo/miniconda3/bin/python` (Python 3.12.4).
Puedes instalar dependencias directamente en conda:

```bash
python -m pip install -r requirements.txt
```

Para usar GPU con PyTorch, instala la versión con CUDA que corresponda a tu driver.
Si `nvidia-smi` falla, primero arregla el driver NVIDIA.

### GPU (verificación rápida)
```bash
nvidia-smi
python - <<'PY'
import torch
print("cuda_available=", torch.cuda.is_available())
if torch.cuda.is_available():
    print(torch.cuda.get_device_name(0))
PY
```

### Notas sobre teclado
`pynput` puede requerir sesión X11. En Wayland, la captura global de teclas puede fallar.

### Audio (salida)
Si no escuchas el TTS, lista los dispositivos y fija el ID o nombre:

```bash
python - <<'PY'
import sounddevice as sd
print(sd.query_devices())
PY
```

Luego en `.env`:
```
AUDIO_OUTPUT_DEVICE=ID_O_NOMBRE
```

Para auto‑seleccionar el dispositivo Razer:
```
AUDIO_OUTPUT_DEVICE=razer
```

Playback del TTS:
- `sd` usa sounddevice
- `aplay` usa ALSA directo
- `sd+aplay` intenta sounddevice y si falla, usa aplay

Velocidad del TTS:
- `TTS_SPEED=1.0` normal
- `TTS_SPEED=1.5` más rápido (puede cambiar el pitch ligeramente)
Si quieres mantener el pitch, deja `TTS_TIME_STRETCH=1` (requiere `librosa`).
Simplificación para voz:
- `TTS_SIMPLIFY=1` reduce símbolos/Markdown en lo que se habla
- `TTS_SIMPLIFY=0` habla el texto literal
Para mejor calidad, usa Rubber Band:
- instala `pyrubberband` y el binario `rubberband`
- configura `TTS_STRETCH_ENGINE=rubberband`

### Opcional: cache y warnings
Si quieres menos ruido de logs y descargas más rápidas, puedes añadir un `HF_TOKEN`.

## Ejecutar

```bash
belanova
```

Alternativa directa:
```bash
make run
```

Modo push‑to‑talk: mantén presionada la tecla configurada y suéltala para enviar.

## Self-check

```bash
belanova-doctor
```

El diagnóstico prueba: micrófono (push‑to‑talk), Whisper, OpenRouter y TTS (si está disponible).

## Prueba de TTS

```bash
belanova-tts-test
```

Si no se escucha, revisa la sección de Audio (salida).

## Notas
- `ALLOW_SHELL=1` permite que el agente ejecute comandos en tu máquina.
- Si `nvidia-smi` falla, verifica la instalación del driver NVIDIA.

## Sonidos de estado
Si existen `assets/audio/thinkingloop.mp3` y `assets/audio/error.mp3`:
- `thinkingloop.mp3` se reproduce en loop mientras se espera la respuesta del agente
- `error.mp3` se reproduce cuando ocurre un error

Requiere `ffmpeg` y `aplay` disponibles en el sistema.

## MCP Skill Bridge
Se integra con el `mcp.json` global de VS Code para acceder a skills.

Este repo incluye un bridge portable en `mcp/skill-bridge/skill_bridge.py`.
El bootstrap lo instala en `~/.config/Code/User/mcp/skill-bridge/skill_bridge.py` y actualiza el servidor `skill-bridge` dentro de `mcp.json`.
Por defecto sincroniza al workspace los skills core `macro-agent` y `region-capture` (usa `make sync-skills-all` si quieres incluir todo).

Variables opcionales:
- `MCP_CONFIG_PATH` (por defecto `~/.config/Code/User/mcp.json`)
- `MCP_TIMEOUT_S` (timeout en segundos para llamadas MCP, por defecto 30)

Tools disponibles para el agente:
- `mcp_list_skills`
- `mcp_get_skill_help`
- `mcp_run_skill`
- `mcp_refresh_skills`

## Utilidad: fusionar PDFs

Script: `scripts/merge_pdfs.py`

Ejemplos:
```bash
python scripts/merge_pdfs.py -o salida.pdf a.pdf b.pdf
python scripts/merge_pdfs.py -o salida.pdf ./carpeta_con_pdfs --recursive
```

## Utilidad: 2 páginas en 1 (2-up)

Script: `scripts/two_up_pdf.py`

Ejemplos:
```bash
python scripts/two_up_pdf.py input.pdf -o output.pdf                 # overlay (sin cambiar tamaño)
python scripts/two_up_pdf.py input.pdf -o output.pdf --mode 2up       # 2-up (puede escalar)
python scripts/two_up_pdf.py input.pdf -o output.pdf --mode 2up --layout v
```
