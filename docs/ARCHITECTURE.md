# Belanova Architecture

## Layers

- `src/belanova/app`: runtime orchestration, diagnostics, and CLI utilities.
- `src/belanova/core`: configuration and LLM client (OpenRouter).
- `src/belanova/asr`: speech recognition services.
- `src/belanova/tts`: speech synthesis services.
- `src/belanova/audio`: push-to-talk capture and audio effects.
- `src/belanova/tools`: local/MCP tool execution.
- `src/belanova/integrations`: external bridges (MCP skill-bridge).

## Structure

```text
belanova/
├── assets/audio/               # runtime sounds (thinking/error)
├── docs/context/               # system prompt/context
├── pyproject.toml              # packaging and CLI entrypoints
├── scripts/                    # bootstrap, installation, PDF utilities
├── skills/                     # workspace core skills (macro-agent, region-capture)
├── mcp/skill-bridge/           # portable MCP server implementation
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

## Principles

- **Separation of concerns:** runtime orchestration stays separate from service implementations.
- **Strict mode:** no legacy root wrappers for runtime app logic.
- **Installable CLI:** direct command `belanova` plus helpers (`belanova-doctor`, `belanova-tts-test`).
- **Minimal core skills:** the repo keeps `macro-agent` and `region-capture` locally and uses global skills via sync.
- **Single bootstrap flow:** `scripts/bootstrap.py` keeps installation reproducible.

## Recommended Conventions

- New application code goes under `src/belanova/...`.
- External integrations stay under `src/belanova/integrations`.
- Operational scripts live in `scripts/`; reusable logic goes in `src/`.
