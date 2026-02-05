#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from pypdf import PdfReader, PdfWriter


_NS_RE = re.compile(r"(\d+)")


def _natural_key(s: str):
    return [int(x) if x.isdigit() else x.lower() for x in _NS_RE.split(s)]


def _iter_pdf_paths(inputs: list[str], recursive: bool, natural_sort: bool) -> list[Path]:
    pdfs: list[Path] = []
    for raw in inputs:
        p = Path(raw).expanduser()
        if p.is_dir():
            it = p.rglob("*.pdf") if recursive else p.glob("*.pdf")
            pdfs.extend([x for x in it if x.is_file()])
        else:
            pdfs.append(p)

    missing = [str(p) for p in pdfs if not p.exists()]
    if missing:
        raise FileNotFoundError("Does not exist: " + ", ".join(missing))

    for p in pdfs:
        if p.suffix.lower() != ".pdf":
            raise ValueError(f"Not a PDF: {p}")

    if natural_sort:
        pdfs.sort(key=lambda x: _natural_key(x.name))
    else:
        pdfs.sort(key=lambda x: x.name.lower())
    return pdfs


def merge_pdfs(
    pdf_paths: list[Path],
    output: Path,
    *,
    password: str | None,
    overwrite: bool,
    keep_metadata: bool,
) -> None:
    if output.exists() and not overwrite:
        raise FileExistsError(f"Already exists: {output} (use --overwrite)")

    writer = PdfWriter()
    first_metadata = None

    for path in pdf_paths:
        reader = PdfReader(str(path))
        if reader.is_encrypted:
            if not password:
                raise RuntimeError(f"Encrypted PDF (missing --password): {path}")
            ok = reader.decrypt(password)
            if not ok:
                raise RuntimeError(f"Invalid password for: {path}")

        if first_metadata is None:
            first_metadata = getattr(reader, "metadata", None)

        for page in reader.pages:
            writer.add_page(page)

    if keep_metadata and first_metadata:
        try:
            writer.add_metadata(
                {k: ("" if v is None else str(v)) for k, v in dict(first_metadata).items()}
            )
        except Exception:
            # Metadata should never break merge behavior.
            pass

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("wb") as f:
        writer.write(f)


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Merge multiple PDFs (or a folder of PDFs) into a single file.\n\n"
            "Examples:\n"
            "  python scripts/merge_pdfs.py -o output.pdf a.pdf b.pdf\n"
            "  python scripts/merge_pdfs.py -o output.pdf ./parts --recursive\n"
        ),
        formatter_class=argparse.RawTextHelpFormatter,
    )
    p.add_argument(
        "inputs",
        nargs="+",
        help="PDF files and/or folders (if folder, includes *.pdf inside).",
    )
    p.add_argument("-o", "--output", required=True, help="Output PDF path.")
    p.add_argument("--recursive", action="store_true", help="Search PDFs recursively in folders.")
    p.add_argument(
        "--no-natural-sort",
        action="store_true",
        help="Disable natural sort (e.g., part2 before part10).",
    )
    p.add_argument("--overwrite", action="store_true", help="Overwrite output if it exists.")
    p.add_argument("--password", help="Password for encrypted PDFs (same for all).")
    p.add_argument(
        "--no-metadata",
        action="store_true",
        help="Do not copy metadata (title/author) from the first PDF.",
    )
    return p.parse_args(argv)


def main(argv: list[str]) -> int:
    try:
        args = _parse_args(argv)
        pdf_paths = _iter_pdf_paths(
            args.inputs,
            recursive=bool(args.recursive),
            natural_sort=not bool(args.no_natural_sort),
        )
        if not pdf_paths:
            raise RuntimeError("No PDFs were found to merge.")
        merge_pdfs(
            pdf_paths,
            Path(args.output).expanduser(),
            password=args.password,
            overwrite=bool(args.overwrite),
            keep_metadata=not bool(args.no_metadata),
        )
        print(f"[ok] generado: {args.output} (inputs={len(pdf_paths)})")
        return 0
    except Exception as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
