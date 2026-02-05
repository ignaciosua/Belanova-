# Arquitectura Belanova

## Capas

- `src/belanova/app`: orquestación de runtime, diagnóstico y utilidades CLI.
- `src/belanova/core`: configuración y cliente LLM (OpenRouter).
- `src/belanova/asr`: servicios de reconocimiento de voz.
- `src/belanova/tts`: servicios de síntesis de voz.
- `src/belanova/audio`: captura PTT y efectos de audio.
- `src/belanova/tools`: ejecución de herramientas locales/MCP.
- `src/belanova/integrations`: puentes externos (MCP skill-bridge).

## Estructura

```text
belanova/
├── assets/audio/               # sonidos runtime (thinking/error)
├── docs/context/               # prompt/contexto de sistema
├── pyproject.toml              # empaquetado y entrypoints CLI
├── scripts/                    # bootstrap, instalación, utilidades PDF
├── skills/                     # skills core del workspace (macro-agent, region-capture)
├── mcp/skill-bridge/           # implementación portable del servidor MCP
└── src/
    └── belanova/
        ├── app/
        │   ├── runtime.py
        │   ├── diagnostics.py
        │   ├── tts_test.py
        │   └── output_scan.py
        ├── core/
        │   ├── config.py
        │   └── agent.py
        ├── asr/whisper_turbo.py
        ├── tts/kokoro.py
        ├── audio/
        │   ├── ptt.py
        │   └── fx.py
        ├── tools/executor.py
        └── integrations/mcp_bridge.py
```

## Principios

- **Separación por responsabilidad:** runtime no mezcla implementación de servicios.
- **Modo estricto:** no hay wrappers legacy en raíz para app runtime.
- **CLI instalable:** comando directo `belanova` y utilidades (`belanova-doctor`, `belanova-tts-test`).
- **Core minimalista de skills:** el repo mantiene `macro-agent` y `region-capture` locales y usa skills globales vía sync.
- **Un solo bootstrap:** `scripts/bootstrap.py` mantiene instalación reproducible.

## Convenciones recomendadas

- Nuevo código de aplicación entra en `src/belanova/...`.
- Integraciones externas solo en `src/belanova/integrations`.
- Scripts operativos en `scripts/`; lógica reusable en `src/`.
