#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import shutil
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEST_DEFAULT = PROJECT_ROOT / "skills"
SOURCE_DEFAULTS = [
    Path.home() / ".copilot/skills",
    Path.home() / ".github/skills",
    Path.home() / ".config/Code/User/skills",
]
CORE_SKILLS = {"macro-agent", "region-capture"}
EXCLUDED_DIR_NAMES = {
    "__pycache__",
    ".git",
    ".pytest_cache",
    ".mypy_cache",
}
EXCLUDED_REL_DIRS = {
    Path("data/recordings"),
    Path("data/captures"),
    Path("data/local"),
}
EXCLUDED_FILE_SUFFIXES = {".pyc", ".pyo"}


def _path_startswith(path: Path, base: Path) -> bool:
    try:
        path.relative_to(base)
        return True
    except ValueError:
        return False


def _is_skill_dir(path: Path) -> bool:
    if not path.is_dir():
        return False
    if (path / "SKILL.md").exists() or (path / "skill.json").exists():
        return True
    return any(path.glob("*.py"))


def _collect_sources(extra_sources: list[Path]) -> list[Path]:
    env_paths = os.getenv("SKILL_BRIDGE_PATHS", "")
    env_sources = [Path(p).expanduser() for p in env_paths.split(os.pathsep) if p.strip()]
    merged = [*SOURCE_DEFAULTS, *env_sources, *extra_sources]
    out: list[Path] = []
    seen: set[str] = set()
    for source in merged:
        resolved = source.expanduser().resolve()
        key = str(resolved)
        if key in seen:
            continue
        seen.add(key)
        out.append(resolved)
    return out


def _ignore_factory(source_root: Path, max_file_mb: int):
    max_bytes = max_file_mb * 1024 * 1024

    def _ignore(current_dir: str, names: list[str]) -> set[str]:
        current = Path(current_dir)
        ignored: set[str] = set()
        rel_current = current.relative_to(source_root)

        for name in names:
            rel = rel_current / name
            full = current / name
            if name in EXCLUDED_DIR_NAMES:
                ignored.add(name)
                continue
            if any(_path_startswith(rel, blocked) for blocked in EXCLUDED_REL_DIRS):
                ignored.add(name)
                continue
            if full.is_file() and full.suffix.lower() in EXCLUDED_FILE_SUFFIXES:
                ignored.add(name)
                continue
            if full.is_file():
                try:
                    if full.stat().st_size > max_bytes:
                        ignored.add(name)
                except OSError:
                    pass
        return ignored

    return _ignore


def sync_skills(
    *,
    dest: Path,
    extra_sources: list[Path],
    overwrite: bool,
    max_file_mb: int,
    profile: str,
) -> tuple[int, int]:
    dest = dest.expanduser().resolve()
    dest.mkdir(parents=True, exist_ok=True)

    copied = 0
    skipped = 0

    sources = _collect_sources(extra_sources)
    for source in sources:
        if not source.exists() or not source.is_dir():
            continue
        if source == dest:
            continue
        for skill_dir in sorted(source.iterdir()):
            if not _is_skill_dir(skill_dir):
                continue
            name = skill_dir.name
            if profile == "core" and name not in CORE_SKILLS:
                skipped += 1
                continue
            target = dest / name
            if target.exists():
                if not overwrite:
                    skipped += 1
                    continue
                shutil.rmtree(target)
            ignore = _ignore_factory(skill_dir.resolve(), max_file_mb=max_file_mb)
            shutil.copytree(skill_dir, target, ignore=ignore)
            copied += 1
    return copied, skipped


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sincroniza skills externos al workspace local (`skills/`).",
    )
    parser.add_argument("--dest", default=str(DEST_DEFAULT), help=f"Directorio destino (default: {DEST_DEFAULT})")
    parser.add_argument(
        "--source",
        action="append",
        default=[],
        help="Path extra de skills (repeatable). Además usa defaults y SKILL_BRIDGE_PATHS.",
    )
    parser.add_argument("--overwrite", action="store_true", help="Sobrescribe skills existentes en destino.")
    parser.add_argument(
        "--max-file-mb",
        type=int,
        default=25,
        help="No copia archivos mayores a este tamaño (MB). Default: 25",
    )
    parser.add_argument(
        "--profile",
        choices=["core", "all"],
        default="core",
        help="core=solo skills core del proyecto (default), all=todas las detectadas",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    copied, skipped = sync_skills(
        dest=Path(args.dest),
        extra_sources=[Path(x) for x in args.source],
        overwrite=bool(args.overwrite),
        max_file_mb=int(args.max_file_mb),
        profile=args.profile,
    )
    print(f"[ok] skills sincronizados: copied={copied} skipped={skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
