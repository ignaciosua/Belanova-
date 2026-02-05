---
name: region-capture
description: "Interactive UI element capture skill. Use to create/update template images and element metadata for desktop automation. Captures are stored in shared runtime data used by macro-agent."
---

# Region Capture

Interactive capture tool for building and maintaining the visual element map used by automation skills.

Use this skill when you need to:
- register a new UI element template image,
- add more template variants to an existing element,
- refresh element captures after UI changes.

## Usage

```bash
python ~/.copilot/skills/region-capture/region_capture.py
```

Optional custom data dir:

```bash
python ~/.copilot/skills/region-capture/region_capture.py --data-dir /path/to/data
```

## Controls

- `f`: freeze screen and capture with visual frame
- `c` or `Space`: direct capture
- `+` / `-`: resize both axes
- `x` / `X`: resize width
- `y` / `Y`: resize height
- `r`: reset to `200x200`
- `q` / `ESC`: quit

## Data Path

By default, this skill stores captures and updates `elements.json` in the shared runtime directory used by `macro-agent`:

- `../macro-agent/data/local/`

This keeps capture and execution workflows aligned.
