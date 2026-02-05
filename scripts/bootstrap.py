#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Iterable


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MCP_CONFIG = Path.home() / ".config/Code/User/mcp.json"
DEFAULT_SKILL_BRIDGE_DIR = Path.home() / ".config/Code/User/mcp/skill-bridge"
LOCAL_SKILL_BRIDGE_SCRIPT = PROJECT_ROOT / "mcp/skill-bridge/skill_bridge.py"
SYSTEM_PACKAGES = ["espeak-ng", "libportaudio2", "ffmpeg", "alsa-utils", "rubberband-cli"]
USER_BIN_DIR = Path.home() / ".local/bin"
SUPPORTED_MIN_PY = (3, 10)
SUPPORTED_MAX_PY_EXCL = (3, 13)


def run(
    cmd: list[str],
    *,
    check: bool = True,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    print(f"[run] {' '.join(cmd)}")
    merged_env = dict(os.environ)
    if env:
        merged_env.update(env)
    return subprocess.run(cmd, text=True, cwd=str(cwd or PROJECT_ROOT), check=check, env=merged_env)


def ensure_env_file() -> None:
    env_path = PROJECT_ROOT / ".env"
    sample = PROJECT_ROOT / ".env.example"
    if env_path.exists():
        return
    if sample.exists():
        shutil.copyfile(sample, env_path)
        print(f"[ok] .env created from {sample.name}")


def _python_version(python_bin: Path | str) -> tuple[int, int]:
    out = subprocess.check_output(
        [str(python_bin), "-c", "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"],
        text=True,
    ).strip()
    major_s, minor_s = out.split(".", 1)
    return int(major_s), int(minor_s)


def _is_supported_python(version: tuple[int, int]) -> bool:
    return SUPPORTED_MIN_PY <= version < SUPPORTED_MAX_PY_EXCL


def _iter_unique(values: Iterable[str | None]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in values:
        if not item:
            continue
        if item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


def select_base_python(preferred_python: str | None = None) -> Path:
    candidates = _iter_unique(
        [
            preferred_python,
            str(Path(sys.executable)),
            shutil.which("python3.12"),
            shutil.which("python3.11"),
            shutil.which("python3.10"),
            shutil.which("python3"),
        ]
    )
    checked: list[str] = []
    for cand in candidates:
        py = Path(cand)
        if not py.exists():
            continue
        try:
            version = _python_version(py)
        except Exception:
            continue
        checked.append(f"{py} ({version[0]}.{version[1]})")
        if _is_supported_python(version):
            print(f"[ok] selected base python: {py} ({version[0]}.{version[1]})")
            return py
    joined = ", ".join(checked) if checked else "none"
    raise RuntimeError(
        "No compatible Python was found (requires >=3.10 and <3.13). "
        f"Checked candidates: {joined}"
    )


def create_or_get_python(venv_dir: Path, skip_venv: bool, *, base_python: Path) -> Path:
    if skip_venv:
        return base_python
    py = venv_dir / "bin/python"
    if py.exists():
        try:
            current_version = _python_version(py)
            if not _is_supported_python(current_version):
                print(
                    "[warn] Current venv uses an incompatible Python "
                    f"({current_version[0]}.{current_version[1]}). Recreating..."
                )
                shutil.rmtree(venv_dir, ignore_errors=True)
        except Exception:
            shutil.rmtree(venv_dir, ignore_errors=True)
    if not venv_dir.exists():
        run([str(base_python), "-m", "venv", str(venv_dir)], check=True)
    py = venv_dir / "bin/python"
    if not py.exists():
        raise RuntimeError(f"Virtualenv python not found at {py}")
    return py


def _read_requirements_lines(req_path: Path) -> list[str]:
    return req_path.read_text(encoding="utf-8").splitlines()


def _is_torch_req(line: str) -> bool:
    stripped = line.strip().lower()
    return bool(stripped) and not stripped.startswith("#") and stripped.startswith("torch")


def _is_accelerate_req(line: str) -> bool:
    stripped = line.strip().lower()
    return bool(stripped) and not stripped.startswith("#") and stripped.startswith("accelerate")


def install_python_deps(py: Path, *, upgrade_pip: bool, torch_mode: str) -> None:
    req = PROJECT_ROOT / "requirements.txt"
    if upgrade_pip:
        result = run([str(py), "-m", "pip", "install", "--upgrade", "pip"], check=False)
        if result.returncode != 0:
            print("[warn] Could not upgrade pip; continuing with dependency installation.")

    lines = _read_requirements_lines(req)
    accelerate_reqs = [ln.strip() for ln in lines if _is_accelerate_req(ln)]
    base_lines = [ln for ln in lines if not _is_torch_req(ln) and not _is_accelerate_req(ln)]

    if torch_mode == "cpu":
        run(
            [
                str(py),
                "-m",
                "pip",
                "install",
                "--index-url",
                "https://download.pytorch.org/whl/cpu",
                "torch",
            ],
            check=True,
        )
    elif torch_mode == "default":
        run([str(py), "-m", "pip", "install", "torch"], check=True)
    else:
        raise RuntimeError(f"Invalid torch mode: {torch_mode}")

    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".txt", delete=False) as tmp:
        tmp.write("\n".join(base_lines).strip() + "\n")
        base_req_path = Path(tmp.name)

    try:
        run([str(py), "-m", "pip", "install", "-r", str(base_req_path)], check=True)
    finally:
        try:
            base_req_path.unlink(missing_ok=True)
        except Exception:
            pass

    for accel_req in accelerate_reqs:
        run([str(py), "-m", "pip", "install", accel_req], check=True)


def install_project_package(py: Path) -> None:
    run(
        [str(py), "-m", "pip", "install", "-e", str(PROJECT_ROOT), "--no-deps"],
        check=True,
    )


def install_system_deps() -> None:
    apt = shutil.which("apt-get")
    sudo = shutil.which("sudo")
    if not apt:
        print("[warn] apt-get is not available; skipping system packages.")
        return
    prefix: list[str] = []
    if sudo and os.geteuid() != 0:
        # In interactive terminals, allow sudo password prompt to avoid skipping critical deps.
        if sys.stdin.isatty():
            prefix = [sudo]
        else:
            probe = subprocess.run([sudo, "-n", "true"], capture_output=True, text=True, check=False)
            if probe.returncode != 0:
                print("[warn] sudo requires an interactive password; skipping system packages in this mode.")
                return
            prefix = [sudo]
    run(prefix + [apt, "update"], check=False)
    run(prefix + [apt, "install", "-y", *SYSTEM_PACKAGES], check=False)


def install_skill_reqs(py: Path, skills_dir: Path) -> None:
    if not skills_dir.exists():
        return
    for skill in sorted(skills_dir.iterdir()):
        if not skill.is_dir():
            continue
        for name in ("requirements.txt", "requirements-dev.txt"):
            req = skill / name
            if req.exists():
                run([str(py), "-m", "pip", "install", "-r", str(req)], check=True)


def sync_workspace_skills(py: Path) -> None:
    script = PROJECT_ROOT / "scripts/sync_workspace_skills.py"
    if not script.exists():
        print(f"[warn] {script} does not exist; skipping skills sync")
        return
    run([str(py), str(script), "--overwrite"], check=True)


def _merge_paths(existing: str, additions: list[str]) -> str:
    items = [p for p in existing.split(os.pathsep) if p] if existing else []
    for p in additions:
        if p not in items:
            items.append(p)
    return os.pathsep.join(items)


def configure_mcp_json(
    mcp_config: Path,
    skill_bridge_dir: Path,
    py: Path,
    project_skills_dir: Path,
) -> None:
    mcp_config.parent.mkdir(parents=True, exist_ok=True)
    if mcp_config.exists():
        data = json.loads(mcp_config.read_text(encoding="utf-8"))
    else:
        data = {"servers": {}, "inputs": []}

    servers = data.setdefault("servers", {})
    sb = servers.get("skill-bridge", {})
    env = dict(sb.get("env", {}) or {})

    skill_paths = [
        str(Path.home() / ".copilot/skills"),
        str(Path.home() / ".github/skills"),
        str(project_skills_dir.resolve()),
    ]
    env["SKILL_BRIDGE_PATHS"] = _merge_paths(env.get("SKILL_BRIDGE_PATHS", ""), skill_paths)

    bridge_script = skill_bridge_dir / "skill_bridge.py"
    servers["skill-bridge"] = {
        "type": "stdio",
        "command": str(py),
        "args": ["-u", str(bridge_script)],
        "env": env,
    }

    data["servers"] = servers
    mcp_config.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"[ok] mcp.json updated: {mcp_config}")


def install_skill_bridge_files(skill_bridge_dir: Path) -> None:
    if not LOCAL_SKILL_BRIDGE_SCRIPT.exists():
        raise RuntimeError(f"Local skill-bridge script not found: {LOCAL_SKILL_BRIDGE_SCRIPT}")
    skill_bridge_dir.mkdir(parents=True, exist_ok=True)
    target = skill_bridge_dir / "skill_bridge.py"
    shutil.copyfile(LOCAL_SKILL_BRIDGE_SCRIPT, target)
    target.chmod(0o755)
    print(f"[ok] skill-bridge installed at {target}")


def smoke_test(py: Path, mcp_config: Path) -> None:
    code = (
        "from belanova.integrations.mcp_bridge import call_skill_bridge; "
        "r=call_skill_bridge('list_skills', {}); "
        "print('[smoke] isError=', r.get('isError')); "
        "print('[smoke] content_head=', str(r.get('content',''))[:200])"
    )
    run(
        [str(py), "-c", code],
        check=True,
        cwd=PROJECT_ROOT,
        env={
            "MCP_CONFIG_PATH": str(mcp_config),
        },
    )


def install_user_launchers(py: Path) -> None:
    USER_BIN_DIR.mkdir(parents=True, exist_ok=True)
    launcher_map = {
        "belanova": "belanova.app.runtime",
        "belanova-doctor": "belanova.app.diagnostics",
        "belanova-tts-test": "belanova.app.tts_test",
        "belanova-output-scan": "belanova.app.output_scan",
    }
    for name, module in launcher_map.items():
        launcher_path = USER_BIN_DIR / name
        cmd = f"exec {shlex.quote(str(py))} -m {module} \"$@\""
        launcher_path.write_text(
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            f"{cmd}\n",
            encoding="utf-8",
        )
        launcher_path.chmod(0o755)
        print(f"[ok] launcher installed: {launcher_path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="One-command bootstrap to install Belanova + skill-bridge + skills.",
    )
    parser.add_argument("--venv", default=".venv", help="Virtualenv directory (default: .venv)")
    parser.add_argument("--no-venv", action="store_true", help="Do not create venv; use current Python")
    parser.add_argument(
        "--mcp-config",
        default=str(DEFAULT_MCP_CONFIG),
        help=f"Path to mcp.json (default: {DEFAULT_MCP_CONFIG})",
    )
    parser.add_argument(
        "--skill-bridge-dir",
        default=str(DEFAULT_SKILL_BRIDGE_DIR),
        help=f"Skill-bridge install directory (default: {DEFAULT_SKILL_BRIDGE_DIR})",
    )
    parser.add_argument("--skip-smoke-test", action="store_true", help="Skip quick MCP smoke test")
    parser.add_argument(
        "--install-system-deps",
        action="store_true",
        help="Try installing system packages (apt-get): espeak-ng, libportaudio2, ffmpeg, alsa-utils, rubberband-cli",
    )
    parser.add_argument("--upgrade-pip", action="store_true", help="Upgrade pip before installing requirements")
    parser.add_argument("--no-sync-skills", action="store_true", help="Do not sync external skills into workspace")
    parser.add_argument("--no-launchers", action="store_true", help="Do not install launchers in ~/.local/bin")
    parser.add_argument(
        "--torch",
        choices=["cpu", "default"],
        default="cpu",
        help="Torch installation mode: cpu (default, lighter), default (PyPI)",
    )
    parser.add_argument(
        "--python",
        default="",
        help="Base Python path/binary for venv creation (default: auto >=3.10,<3.13)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    base_python = select_base_python(args.python.strip() or None)
    venv_dir = (PROJECT_ROOT / args.venv).resolve()
    if args.install_system_deps:
        install_system_deps()
    py = create_or_get_python(venv_dir, skip_venv=bool(args.no_venv), base_python=base_python)
    install_python_deps(py, upgrade_pip=bool(args.upgrade_pip), torch_mode=args.torch)
    install_project_package(py)
    ensure_env_file()

    skill_bridge_dir = Path(args.skill_bridge_dir).expanduser().resolve()
    install_skill_bridge_files(skill_bridge_dir)

    mcp_config = Path(args.mcp_config).expanduser().resolve()
    configure_mcp_json(
        mcp_config=mcp_config,
        skill_bridge_dir=skill_bridge_dir,
        py=py,
        project_skills_dir=PROJECT_ROOT / "skills",
    )

    if not args.no_sync_skills:
        sync_workspace_skills(py)

    install_skill_reqs(py, PROJECT_ROOT / "skills")

    if not args.no_launchers:
        install_user_launchers(py)

    if not args.skip_smoke_test:
        smoke_test(py, mcp_config)

    print("\n✅ Bootstrap completed.")
    print(f"- Python runtime: {py}")
    print(f"- MCP config: {mcp_config}")
    print("- Run: belanova  (or make run)")
    if str(USER_BIN_DIR) not in os.getenv("PATH", ""):
        print(f"- Note: add {USER_BIN_DIR} to PATH to use 'belanova' globally.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
