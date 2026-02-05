import json
import os
import importlib.util
from pathlib import Path
from typing import Any

import anyio
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.client.session import ClientSession
from belanova.paths import PROJECT_ROOT


DEFAULT_MCP_CONFIG = Path.home() / ".config/Code/User/mcp.json"
WORKSPACE_SKILLS = PROJECT_ROOT / "skills"


def _append_skill_path(env: dict[str, str], path: Path) -> None:
    if not path.exists():
        return
    key = "SKILL_BRIDGE_PATHS"
    cur = env.get(key, "").strip()
    entries = [p for p in cur.split(os.pathsep) if p] if cur else []
    path_str = str(path)
    if path_str not in entries:
        entries.append(path_str)
    env[key] = os.pathsep.join(entries)


def _load_skill_bridge_config(config_path: Path) -> dict[str, Any]:
    data = json.loads(config_path.read_text(encoding="utf-8"))
    servers = data.get("servers", {})
    if "skill-bridge" not in servers:
        raise RuntimeError("'skill-bridge' was not found in mcp.json")
    return servers["skill-bridge"]


async def _call_skill_bridge(tool: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    config_path = Path(os.getenv("MCP_CONFIG_PATH", str(DEFAULT_MCP_CONFIG)))
    if not config_path.exists():
        raise RuntimeError(f"mcp.json does not exist at {config_path}")

    cfg = _load_skill_bridge_config(config_path)
    command = cfg.get("command")
    args = cfg.get("args", [])
    env = cfg.get("env", None) or {}
    merged_env = dict(os.environ)
    merged_env.update(env)
    _append_skill_path(merged_env, WORKSPACE_SKILLS)
    # Ensure GUI-related env vars are propagated for skills that need DISPLAY
    for key in ("DISPLAY", "XAUTHORITY", "WAYLAND_DISPLAY", "DBUS_SESSION_BUS_ADDRESS"):
        if os.environ.get(key):
            merged_env[key] = os.environ[key]

    if not command:
        raise RuntimeError("Skill bridge has no 'command' in mcp.json")

    server = StdioServerParameters(command=command, args=args, env=merged_env)

    timeout_s = float(os.getenv("MCP_TIMEOUT_S", "30"))
    err_path = Path("/tmp/mcp_skill_bridge.err")
    with err_path.open("w", encoding="utf-8") as errlog:
        try:
            async with stdio_client(server, errlog=errlog) as (read_stream, write_stream):
                async with ClientSession(read_stream, write_stream) as session:
                    print(f"[mcp] init server=skill-bridge command={command}")
                    print(f"[mcp] env SKILL_BRIDGE_PATHS={merged_env.get('SKILL_BRIDGE_PATHS','')}")
                    try:
                        with anyio.fail_after(timeout_s):
                            await session.initialize()
                    except TimeoutError:
                        return {"isError": True, "content": "Timeout while initializing MCP (skill-bridge)."}
                    print(f"[mcp] call tool={tool} args={arguments or {}} timeout={timeout_s}s")
                    try:
                        with anyio.fail_after(timeout_s):
                            result = await session.call_tool(tool, arguments or {})
                    except TimeoutError:
                        return {"isError": True, "content": f"Timeout while executing MCP tool: {tool}"}
                    print(f"[mcp] done tool={tool} isError={result.isError}")
        except Exception as exc:
            errlog.flush()
            err_text = ""
            try:
                err_text = err_path.read_text(encoding="utf-8").strip()
            except Exception:
                pass
            return {
                "isError": True,
                "content": f"Error MCP skill-bridge: {exc}\\n{err_text}".strip(),
            }
        # Normalize content
        content = []
        for item in result.content:
            if getattr(item, "type", "") == "text":
                content.append(item.text)
            elif getattr(item, "type", "") == "image":
                content.append(f"[image {item.mimeType} {len(item.data)} bytes]")
            else:
                content.append(str(item))
        return {
            "isError": result.isError,
            "content": "\n".join(content).strip(),
        }


def call_skill_bridge(tool: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    try:
        result = anyio.run(_call_skill_bridge, tool, arguments)
        if result.get("isError"):
            return _fallback_direct(tool, arguments or {}, Exception(result.get("content", "MCP error")))
        return result
    except Exception as exc:
        # Fallback: call skill-bridge module directly (no MCP)
        return _fallback_direct(tool, arguments or {}, exc)


def _fallback_direct(tool: str, arguments: dict[str, Any], exc: Exception) -> dict[str, Any]:
    try:
        print(f"[mcp] fallback direct: {exc}")
        config_path = Path(os.getenv("MCP_CONFIG_PATH", str(DEFAULT_MCP_CONFIG)))
        cfg = _load_skill_bridge_config(config_path)
        args_list = cfg.get("args", [])
        script_arg = None
        for item in args_list:
            if str(item).endswith(".py"):
                script_arg = item
                break
        if script_arg is None:
            return {"isError": True, "content": "Fallback failed: .py script was not found in args"}
        script_path = Path(script_arg)
        if not script_path.exists():
            return {"isError": True, "content": f"Fallback failed: {script_path} does not exist"}

        spec = importlib.util.spec_from_file_location("skill_bridge_local", script_path)
        mod = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        spec.loader.exec_module(mod)

        # Ensure SKILL_BRIDGE_PATHS and GUI env for fallback execution
        if cfg.get("env", {}).get("SKILL_BRIDGE_PATHS"):
            os.environ["SKILL_BRIDGE_PATHS"] = cfg["env"]["SKILL_BRIDGE_PATHS"]
        _append_skill_path(os.environ, WORKSPACE_SKILLS)
        for key in ("DISPLAY", "XAUTHORITY", "WAYLAND_DISPLAY", "DBUS_SESSION_BUS_ADDRESS"):
            if key in cfg.get("env", {}):
                os.environ[key] = cfg["env"][key]

        if tool == "list_skills":
            skills = mod.get_skills()
            skill_list = []
            for name, sk in skills.items():
                skill_list.append(
                    {
                        "name": name,
                        "description": sk.get("description", ""),
                        "outputs": sk.get("outputs", ["text/plain"]),
                        "path": sk.get("path", ""),
                    }
                )
            return {"isError": False, "content": json.dumps(skill_list, indent=2, ensure_ascii=False)}

        if tool == "get_skill_help":
            name = arguments.get("skill_name", "")
            skills = mod.get_skills()
            if name not in skills:
                return {"isError": True, "content": f"Skill '{name}' not found."}
            skill_path = Path(skills[name].get("path", ""))
            skill_md = skill_path / "SKILL.md"
            if skill_md.exists():
                return {"isError": False, "content": skill_md.read_text()}
            return {"isError": False, "content": "SKILL.md not found."}

        if tool == "run_skill":
            name = arguments.get("skill_name", "")
            args = arguments.get("args", [])
            skills = mod.get_skills()
            if name not in skills:
                return {"isError": True, "content": f"Skill '{name}' not found."}
            result = anyio.run(mod.execute_skill, skills[name], args)
            output = mod.detect_and_parse_output(result.data if hasattr(result, "data") else result)
            return {"isError": False, "content": str(output.data)}

        if tool == "refresh_skills":
            mod.clear_skills_cache()
            mod.get_skills()
            return {"isError": False, "content": "Skills refreshed (fallback)."}

        return {"isError": True, "content": f"Unknown tool: {tool}"}
    except Exception as e:
        return {"isError": True, "content": f"Fallback error: {e}. MCP error: {exc}"}
