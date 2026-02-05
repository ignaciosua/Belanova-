#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import base64
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from mcp.server import NotificationOptions, Server
from mcp.server.stdio import stdio_server
from mcp.types import CallToolResult, ImageContent, TextContent, Tool


class OutputType:
    IMAGE_PNG = "image/png"
    IMAGE_JPEG = "image/jpeg"
    IMAGE_GIF = "image/gif"
    IMAGE_WEBP = "image/webp"
    JSON = "application/json"
    MARKDOWN = "text/markdown"
    PLAIN = "text/plain"


class SkillOutput:
    def __init__(self, content_type: str, data: Any, raw: str = ""):
        self.content_type = content_type
        self.data = data
        self.raw = raw

    def is_image(self) -> bool:
        return self.content_type.startswith("image/")

    def is_json(self) -> bool:
        return self.content_type == OutputType.JSON

    def is_markdown(self) -> bool:
        return self.content_type == OutputType.MARKDOWN


def _ordered_unique_paths(values: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in values:
        p = str(Path(raw).expanduser())
        if not p or p in seen:
            continue
        seen.add(p)
        out.append(p)
    return out


def _skills_paths() -> list[str]:
    env_paths = os.environ.get("SKILL_BRIDGE_PATHS", "")
    extra = [p for p in env_paths.split(os.pathsep) if p.strip()]
    defaults = [
        "~/.github/skills",
        "~/.copilot/skills",
        "~/.config/Code/User/skills",
    ]
    return _ordered_unique_paths(defaults + extra)


def _extract_description(skill_md: Path) -> str:
    try:
        content = skill_md.read_text(encoding="utf-8")
    except Exception:
        return ""
    match = re.search(r"(?mi)^description:\s*(.+)\s*$", content)
    if match:
        return match.group(1).strip().strip("\"'")
    for line in content.splitlines():
        line = line.strip()
        if line and not line.startswith("#") and not line.startswith("---"):
            return line
    return ""


def discover_skills(skills_paths: list[str]) -> dict[str, dict[str, Any]]:
    skills: dict[str, dict[str, Any]] = {}
    for skills_path in skills_paths:
        base = Path(skills_path).expanduser()
        if not base.exists() or not base.is_dir():
            continue
        for skill_dir in base.iterdir():
            if not skill_dir.is_dir():
                continue

            info: dict[str, Any] = {
                "name": skill_dir.name,
                "path": str(skill_dir),
                "description": f"Skill: {skill_dir.name}",
                "script": None,
                "outputs": ["text/plain"],
            }

            skill_md = skill_dir / "SKILL.md"
            if skill_md.exists():
                desc = _extract_description(skill_md)
                if desc:
                    info["description"] = desc

            for script_name in (
                "main.py",
                f"{skill_dir.name}.py",
                f"{skill_dir.name.replace('-', '_')}.py",
                "script.py",
                "run.py",
            ):
                cand = skill_dir / script_name
                if cand.exists():
                    info["script"] = str(cand)
                    break
            if not info["script"]:
                scripts_dir = skill_dir / "scripts"
                if scripts_dir.exists() and scripts_dir.is_dir():
                    for script_name in ("main.py", "run.py"):
                        cand = scripts_dir / script_name
                        if cand.exists():
                            info["script"] = str(cand)
                            break
                    if not info["script"]:
                        for cand in sorted(scripts_dir.glob("*.py")):
                            if cand.name == "__init__.py" or cand.name.startswith("test_"):
                                continue
                            info["script"] = str(cand)
                            break
            if not info["script"]:
                for cand in sorted(skill_dir.glob("*.py")):
                    if cand.name == "__init__.py" or cand.name.startswith("test_"):
                        continue
                    info["script"] = str(cand)
                    break
            if info["script"]:
                skills[skill_dir.name] = info
    return skills


def detect_and_parse_output(output: Any) -> SkillOutput:
    if isinstance(output, SkillOutput):
        return output
    text = "" if output is None else str(output).strip()
    if not text:
        return SkillOutput(OutputType.PLAIN, "")

    if text.startswith("SKILL_OUTPUT:"):
        match = re.match(r"SKILL_OUTPUT:([^:]+):(.+)", text, re.DOTALL)
        if match:
            mime_type = match.group(1)
            data = match.group(2)
            if ";base64" in mime_type:
                mime_type = mime_type.replace(";base64", "")
                return SkillOutput(mime_type, data, text)
            if mime_type == OutputType.JSON:
                try:
                    return SkillOutput(mime_type, json.loads(data), text)
                except Exception:
                    return SkillOutput(mime_type, data, text)
            return SkillOutput(mime_type, data, text)

    data_uri_match = re.match(r"data:(image/[^;]+);base64,(.+)", text, re.DOTALL)
    if data_uri_match:
        return SkillOutput(data_uri_match.group(1), data_uri_match.group(2), text)

    if len(text) > 100 and re.match(r"^[A-Za-z0-9+/=\s]+$", text[:1000]):
        try:
            decoded = base64.b64decode(text[:100])
            if decoded.startswith(b"\x89PNG"):
                return SkillOutput(OutputType.IMAGE_PNG, text, text)
            if decoded.startswith(b"\xff\xd8\xff"):
                return SkillOutput(OutputType.IMAGE_JPEG, text, text)
            if decoded.startswith(b"GIF8"):
                return SkillOutput(OutputType.IMAGE_GIF, text, text)
            if decoded.startswith(b"RIFF") and b"WEBP" in decoded[:20]:
                return SkillOutput(OutputType.IMAGE_WEBP, text, text)
        except Exception:
            pass

    if (text.startswith("{") and text.endswith("}")) or (text.startswith("[") and text.endswith("]")):
        try:
            return SkillOutput(OutputType.JSON, json.loads(text), text)
        except Exception:
            pass

    if any(
        re.search(pattern, text, re.MULTILINE)
        for pattern in (r"^#{1,6}\s", r"^\*\*[^*]+\*\*", r"^```", r"^\s*[-*]\s", r"^\|\s*[^|]+\s*\|")
    ):
        return SkillOutput(OutputType.MARKDOWN, text, text)

    maybe_path = Path(text).expanduser()
    if maybe_path.exists() and maybe_path.is_file():
        ext = maybe_path.suffix.lower()
        mime_map = {
            ".png": OutputType.IMAGE_PNG,
            ".jpg": OutputType.IMAGE_JPEG,
            ".jpeg": OutputType.IMAGE_JPEG,
            ".gif": OutputType.IMAGE_GIF,
            ".webp": OutputType.IMAGE_WEBP,
        }
        if ext in mime_map:
            try:
                data = base64.b64encode(maybe_path.read_bytes()).decode("utf-8")
                return SkillOutput(mime_map[ext], data, text)
            except Exception:
                pass

    return SkillOutput(OutputType.PLAIN, text, text)


def convert_to_mcp_content(skill_output: SkillOutput) -> list[TextContent | ImageContent]:
    if skill_output.is_image():
        return [ImageContent(type="image", data=skill_output.data, mimeType=skill_output.content_type)]
    if skill_output.is_json():
        text = json.dumps(skill_output.data, indent=2, ensure_ascii=False)
        return [TextContent(type="text", text=f"```json\n{text}\n```")]
    return [TextContent(type="text", text=str(skill_output.data))]


async def execute_skill(skill: dict[str, Any], args: list[str] | None = None) -> SkillOutput:
    script = skill.get("script")
    if not script:
        return SkillOutput(OutputType.PLAIN, f"Error: No script found for skill {skill.get('name', 'unknown')}")
    cmd = [sys.executable, str(script)]
    if args:
        cmd.extend([str(x) for x in args])
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
            cwd=skill.get("path"),
        )
        if result.returncode != 0:
            err = (result.stderr or "").strip() or f"Skill exited with code {result.returncode}"
            return SkillOutput(OutputType.PLAIN, f"Error: {err}")
        return detect_and_parse_output(result.stdout)
    except subprocess.TimeoutExpired:
        return SkillOutput(OutputType.PLAIN, "Error: Skill execution timed out")
    except Exception as exc:
        return SkillOutput(OutputType.PLAIN, f"Error executing skill: {exc}")


server = Server("skill-bridge")
_skills_cache: dict[str, dict[str, Any]] = {}


def get_skills(force_refresh: bool = False) -> dict[str, dict[str, Any]]:
    global _skills_cache
    if force_refresh or not _skills_cache:
        _skills_cache = discover_skills(_skills_paths())
    return _skills_cache


def clear_skills_cache() -> None:
    global _skills_cache
    _skills_cache = {}


@server.list_tools()
async def list_tools() -> list[Tool]:
    tools = [
        Tool(
            name="run_skill",
            description="Run a skill by name.",
            inputSchema={
                "type": "object",
                "properties": {
                    "skill_name": {"type": "string"},
                    "args": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["skill_name"],
            },
        ),
        Tool(
            name="list_skills",
            description="List available skills.",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="get_skill_help",
            description="Return SKILL.md content for a skill.",
            inputSchema={
                "type": "object",
                "properties": {"skill_name": {"type": "string"}},
                "required": ["skill_name"],
            },
        ),
        Tool(
            name="refresh_skills",
            description="Clear cache and rediscover skills.",
            inputSchema={"type": "object", "properties": {}},
        ),
    ]
    for skill_name, info in get_skills(force_refresh=True).items():
        tools.append(
            Tool(
                name=f"skill_{skill_name}",
                description=info.get("description", f"Run {skill_name}"),
                inputSchema={
                    "type": "object",
                    "properties": {"args": {"type": "array", "items": {"type": "string"}}},
                },
            )
        )
    return tools


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> CallToolResult:
    skills = get_skills(force_refresh=False)

    if name == "refresh_skills":
        clear_skills_cache()
        refreshed = get_skills(force_refresh=True)
        return CallToolResult(
            content=[TextContent(type="text", text=f"Skills refreshed. Total: {len(refreshed)}")]
        )

    if name == "list_skills":
        payload = [
            {
                "name": skill_name,
                "description": info.get("description", ""),
                "outputs": info.get("outputs", ["text/plain"]),
                "path": info.get("path", ""),
            }
            for skill_name, info in sorted(skills.items())
        ]
        text = json.dumps(payload, indent=2, ensure_ascii=False)
        return CallToolResult(content=[TextContent(type="text", text=text)])

    if name == "get_skill_help":
        skill_name = str(arguments.get("skill_name", ""))
        skill = skills.get(skill_name)
        if not skill:
            return CallToolResult(
                content=[TextContent(type="text", text=f"Error: Skill '{skill_name}' not found.")]
            )
        skill_md = Path(skill["path"]) / "SKILL.md"
        if skill_md.exists():
            try:
                return CallToolResult(content=[TextContent(type="text", text=skill_md.read_text(encoding="utf-8"))])
            except Exception as exc:
                return CallToolResult(content=[TextContent(type="text", text=f"Error reading SKILL.md: {exc}")])
        return CallToolResult(content=[TextContent(type="text", text="SKILL.md not found.")])

    if name == "run_skill":
        skill_name = str(arguments.get("skill_name", ""))
        args = arguments.get("args", []) or []
        skill = skills.get(skill_name)
        if not skill:
            return CallToolResult(
                content=[TextContent(type="text", text=f"Error: Skill '{skill_name}' not found.")]
            )
        result = await execute_skill(skill, args)
        return CallToolResult(content=convert_to_mcp_content(result))

    if name.startswith("skill_"):
        skill_name = name[6:]
        args = arguments.get("args", []) or []
        skill = skills.get(skill_name)
        if not skill:
            return CallToolResult(content=[TextContent(type="text", text=f"Error: Skill '{skill_name}' not found.")])
        result = await execute_skill(skill, args)
        return CallToolResult(content=convert_to_mcp_content(result))

    return CallToolResult(content=[TextContent(type="text", text=f"Unknown tool: {name}")])


async def main() -> None:
    async with stdio_server() as (read_stream, write_stream):
        opts = server.create_initialization_options(notification_options=NotificationOptions(tools_changed=True))
        await server.run(read_stream, write_stream, opts)


if __name__ == "__main__":
    asyncio.run(main())
