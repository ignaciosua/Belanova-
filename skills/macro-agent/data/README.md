# Macro Agent Data

This directory separates safe example data from local runtime data:

- `examples/`: safe, versioned files used to show structure.
- `local/`: runtime-generated data (captures, sequences, sound state). This folder is in `.gitignore` to avoid committing sensitive data.

If you need to customize elements or sequences, do it from runtime; changes will be stored in `data/local/`.
