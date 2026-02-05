import json
import os
import subprocess
import sys
from pathlib import Path

CONFIG_PATH = Path(os.getenv("MCP_CONFIG_PATH", str(Path.home() / ".config/Code/User/mcp.json")))

def load_skill_paths():
    if CONFIG_PATH.exists():
        data = json.loads(CONFIG_PATH.read_text())
        servers = data.get("servers", {})
        sb = servers.get("skill-bridge", {})
        env = sb.get("env", {})
        paths = env.get("SKILL_BRIDGE_PATHS", "")
        if paths:
            return [Path(p) for p in paths.split(os.pathsep) if p]
    env_paths = os.getenv("SKILL_BRIDGE_PATHS", "")
    if env_paths:
        return [Path(p) for p in env_paths.split(os.pathsep) if p]
    return []


def iter_skills(paths):
    for base in paths:
        if not base.exists():
            continue
        for child in base.iterdir():
            if child.is_dir():
                yield child


def find_requirements(skill_dir: Path):
    for name in ("requirements.txt", "requirements-dev.txt"):
        p = skill_dir / name
        if p.exists():
            return p
    return None


def main():
    paths = load_skill_paths()
    if not paths:
        print("No SKILL_BRIDGE_PATHS were found.")
        return 1

    reqs = []
    for skill in iter_skills(paths):
        req = find_requirements(skill)
        if req:
            reqs.append(req)
            print(f"[skill] {skill.name} -> {req}")
        else:
            print(f"[skill] {skill.name} -> no requirements.txt")

    if not reqs:
        print("No requirements to install.")
        return 0

    for req in reqs:
        print(f"[pip] install -r {req}")
        subprocess.run([sys.executable, "-m", "pip", "install", "-r", str(req)], check=False)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
