#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pypdf import PdfReader, PdfWriter, Transformation
from pypdf import PageObject


def _page_size(page: PageObject) -> tuple[float, float]:
    box = page.mediabox
    return float(box.width), float(box.height)


def _copy_metadata(writer: PdfWriter, reader: PdfReader) -> None:
    meta = getattr(reader, "metadata", None)
    if not meta:
        return
    try:
        writer.add_metadata({k: ("" if v is None else str(v)) for k, v in dict(meta).items()})
    except Exception:
        pass


def _copy_boxes(dst: PageObject, src: PageObject) -> None:
    # Conserva el tamaño y las cajas del PDF original (media/crop/etc).
    for name in ("mediabox", "cropbox", "bleedbox", "trimbox", "artbox"):
        try:
            setattr(dst, name, getattr(src, name))
        except Exception:
            pass


def two_up(
    input_pdf: Path,
    output_pdf: Path,
    *,
    mode: str,
    layout: str,
    dpi: int,
    white_threshold: int,
    softness: int,
    overwrite: bool,
    password: str | None,
    keep_metadata: bool,
    drop_last: bool,
) -> int:
    if not input_pdf.exists():
        raise FileNotFoundError(f"No existe: {input_pdf}")
    if output_pdf.exists() and not overwrite:
        raise FileExistsError(f"Ya existe: {output_pdf} (usa --overwrite)")

    reader = PdfReader(str(input_pdf))
    if reader.is_encrypted:
        if not password:
            raise RuntimeError("PDF encriptado (falta --password)")
        ok = reader.decrypt(password)
        if not ok:
            raise RuntimeError("Password incorrecta")

    # Normaliza rotación para que el contenido tenga /Rotate=0
    for p in reader.pages:
        try:
            p.transfer_rotation_to_content()
        except Exception:
            pass

    if not reader.pages:
        raise RuntimeError("PDF sin páginas")

    if mode not in {"overlay", "overlay_transparent", "2up"}:
        raise ValueError("mode inválido (usa 'overlay', 'overlay_transparent' o '2up')")

    if mode == "overlay":
        writer = PdfWriter()
        if keep_metadata:
            _copy_metadata(writer, reader)

        pages = list(reader.pages)
        i = 0
        while i < len(pages):
            p1 = pages[i]
            p2 = pages[i + 1] if i + 1 < len(pages) else None
            if p2 is None and drop_last:
                break

            w, h = _page_size(p1)
            out = PageObject.create_blank_page(width=w, height=h)
            _copy_boxes(out, p1)
            out.merge_page(p1, over=True)
            if p2 is not None:
                # Superpone p2 encima de p1, sin escalar ni mover.
                out.merge_page(p2, over=True)
            writer.add_page(out)
            i += 2

        output_pdf.parent.mkdir(parents=True, exist_ok=True)
        with output_pdf.open("wb") as f:
            writer.write(f)
        return 0

    if mode == "overlay_transparent":
        # Renderiza la página 2 como imagen y convierte el blanco a transparente,
        # para que el contenido de la página 1 se vea debajo sin cambiar el tamaño.
        import io

        try:
            import fitz  # PyMuPDF
        except Exception as exc:  # pragma: no cover
            raise RuntimeError(f"Falta PyMuPDF (fitz): {exc}")

        try:
            from PIL import Image
        except Exception as exc:  # pragma: no cover
            raise RuntimeError(f"Falta Pillow (PIL): {exc}")

        if dpi <= 0:
            raise ValueError("--dpi debe ser > 0")
        if not (0 <= white_threshold <= 255):
            raise ValueError("--white-threshold debe estar entre 0 y 255")
        if softness < 0:
            raise ValueError("--softness debe ser >= 0")

        src = fitz.open(str(input_pdf))
        out = fitz.open()

        def to_rgba_with_alpha(pix: "fitz.Pixmap") -> bytes:
            im = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            # Whiteness heuristic: si los 3 canales >= threshold => transparente.
            # (sin numpy; hacemos una pasada por bytes)
            rgb = im.tobytes()
            alpha = bytearray(len(rgb) // 3)
            t0 = white_threshold
            s = softness
            j = 0
            for k in range(0, len(rgb), 3):
                rr = rgb[k]
                gg = rgb[k + 1]
                bb = rgb[k + 2]
                if s == 0:
                    a = 0 if (rr >= t0 and gg >= t0 and bb >= t0) else 255
                else:
                    mn = rr if rr < gg else gg
                    mn = mn if mn < bb else bb
                    if mn <= t0:
                        a = 255
                    elif mn >= t0 + s:
                        a = 0
                    else:
                        a = int(255 * (1.0 - (mn - t0) / s))
                alpha[j] = a
                j += 1

            rgba = im.convert("RGBA")
            rgba.putalpha(Image.frombytes("L", im.size, bytes(alpha)))

            buf = io.BytesIO()
            rgba.save(buf, format="PNG", optimize=True)
            return buf.getvalue()

        scale = dpi / 72.0
        matrix = fitz.Matrix(scale, scale)

        i = 0
        n = src.page_count
        while i < n:
            base = src.load_page(i)
            ov = src.load_page(i + 1) if i + 1 < n else None
            if ov is None and drop_last:
                break

            newp = out.new_page(width=base.rect.width, height=base.rect.height)
            newp.show_pdf_page(newp.rect, src, i)

            if ov is not None:
                pix = ov.get_pixmap(matrix=matrix, alpha=False)
                png = to_rgba_with_alpha(pix)
                newp.insert_image(newp.rect, stream=png, keep_proportion=False, overlay=True)

            i += 2

        out.save(str(output_pdf))
        out.close()
        src.close()
        return 0

    max_w = 0.0
    max_h = 0.0
    for p in reader.pages:
        w, h = _page_size(p)
        max_w = max(max_w, w)
        max_h = max(max_h, h)

    if layout not in {"h", "v"}:
        raise ValueError("layout inválido (usa 'h' o 'v')")

    writer = PdfWriter()
    if keep_metadata:
        _copy_metadata(writer, reader)

    slot_w = max_w / 2.0 if layout == "h" else max_w
    slot_h = max_h if layout == "h" else max_h / 2.0

    def place(src: PageObject, dest: PageObject, *, slot_x: float, slot_y: float) -> None:
        sw, sh = _page_size(src)
        if sw <= 0 or sh <= 0:
            return
        scale = min(slot_w / sw, slot_h / sh)
        tx = slot_x + (slot_w - sw * scale) / 2.0
        ty = slot_y + (slot_h - sh * scale) / 2.0
        dest.merge_transformed_page(src, Transformation().scale(scale).translate(tx, ty), over=True)

    pages = list(reader.pages)
    i = 0
    while i < len(pages):
        p1 = pages[i]
        p2 = pages[i + 1] if i + 1 < len(pages) else None
        if p2 is None and drop_last:
            break

        out = PageObject.create_blank_page(width=max_w, height=max_h)
        if layout == "h":
            place(p1, out, slot_x=0.0, slot_y=0.0)
            if p2 is not None:
                place(p2, out, slot_x=slot_w, slot_y=0.0)
        else:
            # Vertical: primera página arriba, segunda abajo
            place(p1, out, slot_x=0.0, slot_y=slot_h)
            if p2 is not None:
                place(p2, out, slot_x=0.0, slot_y=0.0)

        writer.add_page(out)
        i += 2

    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    with output_pdf.open("wb") as f:
        writer.write(f)
    return 0


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Convierte 2 páginas en 1.\n"
            "- mode=overlay: superpone página 2 sobre la 1 (sin cambiar tamaño).\n"
            "- mode=overlay_transparent: como overlay, pero el blanco de la página 2 se vuelve transparente.\n"
            "- mode=2up: pone 2 páginas en una hoja (puede escalar para que quepan).\n\n"
            "Ejemplos:\n"
            "  python scripts/two_up_pdf.py input.pdf -o output.pdf\n"
            "  python scripts/two_up_pdf.py input.pdf -o output.pdf --mode overlay_transparent\n"
            "  python scripts/two_up_pdf.py input.pdf -o output.pdf --mode 2up --layout v\n"
        ),
        formatter_class=argparse.RawTextHelpFormatter,
    )
    p.add_argument("input", help="PDF de entrada")
    p.add_argument("-o", "--output", required=True, help="PDF de salida")
    p.add_argument(
        "--mode",
        choices=["overlay", "overlay_transparent", "2up"],
        default="overlay",
        help="overlay=superponer (sin escalar), 2up=2 páginas en una hoja",
    )
    p.add_argument(
        "--layout",
        choices=["h", "v"],
        default="h",
        help="Solo para mode=2up: h=horizontal (lado a lado), v=vertical",
    )
    p.add_argument(
        "--dpi",
        type=int,
        default=200,
        help="Solo para mode=overlay_transparent: DPI de render de la página 2 (más alto = mejor, más pesado)",
    )
    p.add_argument(
        "--white-threshold",
        type=int,
        default=245,
        help="Solo para mode=overlay_transparent: >= este valor se considera blanco (0-255)",
    )
    p.add_argument(
        "--softness",
        type=int,
        default=10,
        help="Solo para mode=overlay_transparent: rango suave para alpha (0=hard keying)",
    )
    p.add_argument("--overwrite", action="store_true", help="Sobrescribe el output si existe")
    p.add_argument("--password", help="Password si el PDF está encriptado")
    p.add_argument("--no-metadata", action="store_true", help="No copia metadata del PDF original")
    p.add_argument(
        "--drop-last",
        action="store_true",
        help="Si hay páginas impares, elimina la última en vez de dejar el hueco",
    )
    return p.parse_args(argv)


def main(argv: list[str]) -> int:
    try:
        args = _parse_args(argv)
        return two_up(
            Path(args.input).expanduser(),
            Path(args.output).expanduser(),
            mode=args.mode,
            layout=args.layout,
            dpi=int(args.dpi),
            white_threshold=int(args.white_threshold),
            softness=int(args.softness),
            overwrite=bool(args.overwrite),
            password=args.password,
            keep_metadata=not bool(args.no_metadata),
            drop_last=bool(args.drop_last),
        )
    except Exception as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
