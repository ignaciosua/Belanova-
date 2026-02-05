import json
import os
from dataclasses import dataclass
from typing import Any

import requests


@dataclass
class AgentConfig:
    api_key: str
    base_url: str
    model: str
    max_tool_iters: int = 8
    provider: str = ""


class OpenRouterAgent:
    def __init__(self, config: AgentConfig, tools):
        if not config.model:
            raise RuntimeError("OPENROUTER_MODEL is not configured")
        self.config = config
        self.tools = tools
        self._last_model = config.model

    def _headers(self) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }
        referer = os.getenv("OPENROUTER_REFERER")
        title = os.getenv("OPENROUTER_TITLE")
        if referer:
            headers["HTTP-Referer"] = referer
        if title:
            headers["X-Title"] = title
        return headers

    def _endpoint(self) -> str:
        base = self.config.base_url.rstrip("/")
        if base.endswith("/chat/completions"):
            return base
        return f"{base}/chat/completions"

    def _call(self, messages: list[dict[str, Any]], tool_schemas: list[dict[str, Any]] | None):
        payload = {
            "model": self.config.model,
            "messages": messages,
        }
        if tool_schemas:
            payload["tools"] = tool_schemas
        if self.config.provider:
            payload["provider"] = {"order": [self.config.provider]}
        url = self._endpoint()
        resp = requests.post(
            url,
            headers=self._headers(),
            data=json.dumps(payload),
            timeout=120,
        )
        if resp.status_code >= 400:
            snippet = resp.text[:1000]
            raise RuntimeError(
                f"OpenRouter error {resp.status_code} at {url}: {snippet}"
            )
        return resp.json()

    def get_last_model(self) -> str:
        return self._last_model or self.config.model

    def run(self, user_text: str, messages: list[dict[str, Any]] | None = None) -> str:
        if messages is None:
            system = {
                "role": "system",
                "content": (
                    "You are an agent that can use tools to perform real actions. "
                    "Reply in English. Use tools when needed. "
                    "If you use tools, wait for results before continuing."
                ),
            }
            messages = [system, {"role": "user", "content": user_text}]
        else:
            # caller already appended user message
            pass

        self._sanitize_tool_history(messages)

        tool_schemas = self.tools.schemas()
        last_model = self.config.model
        for _ in range(self.config.max_tool_iters):
            data = self._call(messages, tool_schemas)
            last_model = data.get("model", last_model)
            msg = data["choices"][0]["message"]

            tool_calls = msg.get("tool_calls")
            if not tool_calls:
                self._last_model = last_model
                return msg.get("content", "")

            messages.append(msg)
            single_call = len(tool_calls) == 1
            for call in tool_calls:
                name = call.get("function", {}).get("name", "")
                raw_args = call.get("function", {}).get("arguments", "")
                try:
                    args = json.loads(raw_args) if raw_args else {}
                except Exception as exc:
                    err_content = f"Error parsing arguments for {name}: {exc}"
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call.get("id", ""),
                            "name": name,
                            "content": err_content,
                        }
                    )
                    continue
                result = self.tools.execute(name, args)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.get("id", ""),
                        "name": name,
                        "content": result.content,
                    }
                )
                # Short-circuit only when there is a single MCP tool call
                if single_call and name.startswith("mcp_") and result.ok and result.content:
                    self._last_model = last_model
                    return result.content

        self._last_model = last_model
        return "Stopped due to too many tool calls."

    def _sanitize_tool_history(self, messages: list[dict[str, Any]]) -> None:
        sanitized: list[dict[str, Any]] = []
        i = 0
        removed = 0
        while i < len(messages):
            msg = messages[i]
            if msg.get("role") == "assistant" and msg.get("tool_calls"):
                tool_calls = msg.get("tool_calls") or []
                ids = [c.get("id") for c in tool_calls if c.get("id")]
                j = i + 1
                seen: set[str] = set()
                while j < len(messages) and messages[j].get("role") == "tool":
                    tcid = messages[j].get("tool_call_id")
                    if tcid:
                        seen.add(tcid)
                    j += 1
                if ids and not all(tid in seen for tid in ids):
                    removed += 1
                    i = j
                    continue
                sanitized.append(msg)
                sanitized.extend(messages[i + 1 : j])
                i = j
                continue
            sanitized.append(msg)
            i += 1
        if removed:
            messages[:] = sanitized
            print(f"[agent] sanitized history: removed {removed} unmatched tool_call(s)")

    def chat(self, messages: list[dict[str, Any]], use_tools: bool = True) -> tuple[str, str]:
        tool_schemas = self.tools.schemas() if use_tools else None
        last_model = self.config.model
        data = self._call(messages, tool_schemas)
        last_model = data.get("model", last_model)
        msg = data["choices"][0]["message"]
        tool_calls = msg.get("tool_calls")
        if tool_calls:
            return "", last_model
        return msg.get("content", ""), last_model
