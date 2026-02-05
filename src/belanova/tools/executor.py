import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from belanova.integrations.mcp_bridge import call_skill_bridge
from belanova.paths import PROJECT_ROOT

ROOT_DIR = PROJECT_ROOT


@dataclass
class ToolResult:
    ok: bool
    content: str


def _safe_path(path: str) -> Path:
    target = (ROOT_DIR / path).resolve()
    if not str(target).startswith(str(ROOT_DIR)):
        raise ValueError("Path fuera del directorio permitido")
    return target


class ToolExecutor:
    def __init__(
        self,
        allow_shell: bool = True,
        narrator: Callable[[str], None] | None = None,
        confirmer: Callable[[str], bool] | None = None,
        on_tool_start: Callable[[str, dict[str, Any]], None] | None = None,
        on_tool_end: Callable[[str, dict[str, Any], ToolResult], None] | None = None,
    ):
        self.allow_shell = allow_shell
        self.narrator = narrator or (lambda _text: None)
        self.confirmer = confirmer or (lambda _text: True)
        self.on_tool_start = on_tool_start or (lambda _name, _args: None)
        self.on_tool_end = on_tool_end or (lambda _name, _args, _res: None)

    def schemas(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "run_shell",
                    "description": "Ejecuta un comando de shell en el proyecto.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "command": {"type": "string"},
                            "timeout_s": {"type": "integer", "default": 60},
                        },
                        "required": ["command"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "read_file",
                    "description": "Lee un archivo del proyecto.",
                    "parameters": {
                        "type": "object",
                        "properties": {"path": {"type": "string"}},
                        "required": ["path"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "write_file",
                    "description": "Escribe o crea un archivo dentro del proyecto.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string"},
                            "content": {"type": "string"},
                        },
                        "required": ["path", "content"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "list_dir",
                    "description": "Lista archivos en un directorio del proyecto.",
                    "parameters": {
                        "type": "object",
                        "properties": {"path": {"type": "string", "default": "."}},
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "search_text",
                    "description": "Busca texto en archivos del proyecto (usa ripgrep).",
                    "parameters": {
                        "type": "object",
                        "properties": {"pattern": {"type": "string"}},
                        "required": ["pattern"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "mcp_list_skills",
                    "description": "Lista skills disponibles via MCP skill-bridge.",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "mcp_get_skill_help",
                    "description": "Obtiene ayuda detallada de un skill MCP.",
                    "parameters": {
                        "type": "object",
                        "properties": {"skill_name": {"type": "string"}},
                        "required": ["skill_name"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "mcp_run_skill",
                    "description": "Ejecuta un skill MCP con argumentos opcionales.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "skill_name": {"type": "string"},
                            "args": {"type": "array", "items": {"type": "string"}},
                        },
                        "required": ["skill_name"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "mcp_refresh_skills",
                    "description": "Refresca lista de skills MCP.",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
        ]

    def execute(self, name: str, args: dict[str, Any]) -> ToolResult:
        try:
            if not self._confirm(name, args):
                result = ToolResult(ok=False, content="Acción cancelada por el usuario.")
                self.on_tool_end(name, args, result)
                return result
            self.on_tool_start(name, args)
            if name == "run_shell":
                result = self._run_shell(args)
                self.on_tool_end(name, args, result)
                return result
            if name == "read_file":
                result = self._read_file(args)
                self.on_tool_end(name, args, result)
                return result
            if name == "write_file":
                result = self._write_file(args)
                self.on_tool_end(name, args, result)
                return result
            if name == "list_dir":
                result = self._list_dir(args)
                self.on_tool_end(name, args, result)
                return result
            if name == "search_text":
                result = self._search_text(args)
                self.on_tool_end(name, args, result)
                return result
            if name == "mcp_list_skills":
                result = self._mcp_list_skills()
                self.on_tool_end(name, args, result)
                return result
            if name == "mcp_get_skill_help":
                result = self._mcp_get_skill_help(args)
                self.on_tool_end(name, args, result)
                return result
            if name == "mcp_run_skill":
                result = self._mcp_run_skill(args)
                self.on_tool_end(name, args, result)
                return result
            if name == "mcp_refresh_skills":
                result = self._mcp_refresh_skills()
                self.on_tool_end(name, args, result)
                return result
            result = ToolResult(ok=False, content=f"Herramienta desconocida: {name}")
            self.on_tool_end(name, args, result)
            return result
        except Exception as exc:
            result = ToolResult(ok=False, content=f"Error en {name}: {exc}")
            self.on_tool_end(name, args, result)
            return result

    def _confirm(self, name: str, args: dict[str, Any]) -> bool:
        summary = self._describe_action(name, args)
        return self.confirmer(summary)

    def _describe_action(self, name: str, args: dict[str, Any]) -> str:
        try:
            if name == "run_shell":
                cmd = args.get("command", "")
                return f"Ejecutar comando en la terminal: {cmd}"
            if name == "read_file":
                return f"Leer el archivo: {args.get('path', '')}"
            if name == "write_file":
                return f"Escribir el archivo: {args.get('path', '')}"
            if name == "list_dir":
                return f"Listar el directorio: {args.get('path', '.')}"
            if name == "search_text":
                return f"Buscar texto: {args.get('pattern', '')}"
            if name == "mcp_list_skills":
                return "Listar skills MCP"
            if name == "mcp_get_skill_help":
                return f"Obtener ayuda del skill MCP: {args.get('skill_name', '')}"
            if name == "mcp_run_skill":
                return f"Ejecutar skill MCP: {args.get('skill_name', '')}"
            if name == "mcp_refresh_skills":
                return "Refrescar skills MCP"
        except Exception:
            pass
        try:
            return json.dumps({"tool": name, "args": args}, ensure_ascii=False)
        except Exception:
            return f"tool={name}"

    def _run_shell(self, args: dict[str, Any]) -> ToolResult:
        if not self.allow_shell:
            return ToolResult(ok=False, content="Ejecución de shell deshabilitada")
        command = args.get("command", "")
        timeout_s = int(args.get("timeout_s", 60))
        self.narrator(f"Voy a ejecutar un comando: {command}")
        completed = subprocess.run(
            command,
            shell=True,
            cwd=ROOT_DIR,
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
        payload = {
            "ok": completed.returncode == 0,
            "returncode": completed.returncode,
            "stdout": completed.stdout[-4000:],
            "stderr": completed.stderr[-4000:],
        }
        return ToolResult(ok=payload["ok"], content=json.dumps(payload, ensure_ascii=False))

    def _read_file(self, args: dict[str, Any]) -> ToolResult:
        path = _safe_path(args.get("path", ""))
        self.narrator(f"Leyendo el archivo {path}")
        content = path.read_text(encoding="utf-8")
        return ToolResult(ok=True, content=content)

    def _write_file(self, args: dict[str, Any]) -> ToolResult:
        path = _safe_path(args.get("path", ""))
        content = args.get("content", "")
        self.narrator(f"Escribiendo el archivo {path}")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return ToolResult(ok=True, content="ok")

    def _list_dir(self, args: dict[str, Any]) -> ToolResult:
        path = _safe_path(args.get("path", "."))
        self.narrator(f"Listando directorio {path}")
        entries = sorted([p.name for p in path.iterdir()])
        return ToolResult(ok=True, content=json.dumps(entries, ensure_ascii=False))

    def _search_text(self, args: dict[str, Any]) -> ToolResult:
        pattern = args.get("pattern", "")
        self.narrator(f"Buscando texto: {pattern}")
        cmd = ["rg", "-n", pattern, "."]
        completed = subprocess.run(
            cmd,
            cwd=ROOT_DIR,
            capture_output=True,
            text=True,
        )
        payload = {
            "ok": completed.returncode == 0,
            "stdout": completed.stdout[-4000:],
            "stderr": completed.stderr[-4000:],
        }
        return ToolResult(ok=payload["ok"], content=json.dumps(payload, ensure_ascii=False))

    def _mcp_list_skills(self) -> ToolResult:
        self.narrator("Listando skills MCP")
        result = call_skill_bridge("list_skills", {})
        return ToolResult(ok=not result.get("isError", False), content=result.get("content", ""))

    def _mcp_get_skill_help(self, args: dict[str, Any]) -> ToolResult:
        skill_name = args.get("skill_name", "")
        self.narrator(f"Obteniendo ayuda de skill MCP: {skill_name}")
        result = call_skill_bridge("get_skill_help", {"skill_name": skill_name})
        return ToolResult(ok=not result.get("isError", False), content=result.get("content", ""))

    def _mcp_run_skill(self, args: dict[str, Any]) -> ToolResult:
        skill_name = args.get("skill_name", "")
        skill_args = args.get("args", [])
        self.narrator(f"Ejecutando skill MCP: {skill_name}")
        result = call_skill_bridge("run_skill", {"skill_name": skill_name, "args": skill_args})
        return ToolResult(ok=not result.get("isError", False), content=result.get("content", ""))

    def _mcp_refresh_skills(self) -> ToolResult:
        self.narrator("Refrescando skills MCP")
        result = call_skill_bridge("refresh_skills", {})
        return ToolResult(ok=not result.get("isError", False), content=result.get("content", ""))
