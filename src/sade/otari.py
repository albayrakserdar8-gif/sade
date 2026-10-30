"""A thin client for the Otari gateway (OpenAI-compatible, plus Otari's own
fields and headers).

We call the HTTP API directly rather than through an SDK so that every
Otari-specific piece is visible: routing headers, built-in tools, MCP
servers, guardrails, request tags and per-request cost.

Requests are always streamed: the hosted gateway sits behind an edge that
cuts non-streamed responses after ~30 s, and tool loops (code, web search,
MCP) or OCR on a large image take longer than that.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from typing import Any, AsyncIterator

import httpx

from . import config


class OtariError(Exception):
    def __init__(self, status: int, code: str | None, detail: Any, headers: dict[str, str]):
        self.status, self.code, self.detail, self.headers = status, code, detail, headers
        self.call: Call | None = None
        super().__init__(f"Otari {status} {code or ''}: {detail}")


@dataclass
class Call:
    """What one gateway call did, for the UI's Otari panel."""

    role: str
    model_requested: str
    model_served: str | None = None
    provider: str | None = None
    fallback: bool = False
    attempts: int | None = None
    cost_usd: float = 0.0
    duration_ms: int | None = None
    request_id: str | None = None
    tokens: int | None = None
    error: str | None = None
    code_runs: list[dict] = field(default_factory=list)
    web_calls: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def _headers(api_key: str | None, conversation_id: str | None, extra: dict | None) -> dict[str, str]:
    h = {
        "Authorization": f"Bearer {api_key or config.OTARI_API_KEY}",
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
    }
    if conversation_id:
        h["Otari-Conversation-Id"] = conversation_id
    h.update(extra or {})
    return h


def _fill_from_headers(call: Call, headers: httpx.Headers) -> None:
    call.request_id = headers.get("otari-request-id")
    call.model_served = headers.get("otari-model")
    call.provider = headers.get("otari-provider")
    call.fallback = headers.get("otari-fallback") == "true"
    attempts = headers.get("otari-attempt-count")
    call.attempts = int(attempts) if attempts and attempts.isdigit() else None


async def _error_from(resp: httpx.Response) -> OtariError:
    raw = await resp.aread()
    try:
        body = json.loads(raw)
    except ValueError:
        body = {"detail": raw.decode(errors="replace")[:300]}
    detail = body.get("detail", body) if isinstance(body, dict) else body
    code = (body.get("code") if isinstance(body, dict) else None) or (
        detail.get("code") if isinstance(detail, dict) else None
    )
    return OtariError(resp.status_code, code or resp.headers.get("otari-error-code"), detail, dict(resp.headers))


async def _stream(path: str, body: dict, call: Call, headers: dict) -> AsyncIterator[dict]:
    """POST and yield each SSE `data:` JSON object."""
    started = time.monotonic()
    async with httpx.AsyncClient(timeout=httpx.Timeout(300, connect=15)) as client:
        async with client.stream("POST", f"{config.OTARI_API_BASE}/api/v1/{path}", headers=headers, json=body) as resp:
            _fill_from_headers(call, resp.headers)
            if resp.status_code >= 400:
                err = await _error_from(resp)
                call.error = f"{err.status} {err.code or ''}".strip()
                call.duration_ms = int((time.monotonic() - started) * 1000)
                err.call = call
                raise err
            async for line in resp.aiter_lines():
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if not data or data == "[DONE]":
                    continue
                event = json.loads(data)
                if event.get("type") in ("error", "response.failed") or "error" in event and not event.get("choices"):
                    err = OtariError(502, "stream_error", event.get("error") or event, dict(resp.headers))
                    call.error = "stream error"
                    err.call = call
                    raise err
                yield event
    call.duration_ms = int((time.monotonic() - started) * 1000)


async def responses(
    *,
    role: str,
    model: str,
    input: str | list,
    instructions: str | None = None,
    text_format: dict | None = None,
    tools: list[dict] | None = None,
    metadata: dict[str, str] | None = None,
    conversation_id: str | None = None,
    max_output_tokens: int = 3000,
    api_key: str | None = None,
    headers: dict | None = None,
    extra: dict | None = None,
) -> tuple[dict, Call]:
    """POST /api/v1/responses (streamed). Returns (final response object, Call)."""
    body: dict[str, Any] = {
        "model": model, "input": input, "max_output_tokens": max_output_tokens, "stream": True,
        "metadata": {"app": "sade", "role": role, **(metadata or {})},
    }
    if instructions:
        body["instructions"] = instructions
    if text_format:
        body["text"] = {"format": text_format}
    if tools:
        body["tools"] = tools
    body.update(extra or {})

    call = Call(role=role, model_requested=model)
    final: dict | None = None
    async for event in _stream("responses", body, call, _headers(api_key, conversation_id, headers)):
        if event.get("type") == "response.completed":
            final = event.get("response")
    if final is None:
        raise OtariError(502, "incomplete_stream", "stream ended without response.completed", {})

    usage = final.get("usage") or {}
    call.cost_usd = float(usage.get("cost_usd") or 0)
    call.tokens = usage.get("total_tokens")
    for item in final.get("output", []):
        if item.get("type") == "code_interpreter_call":
            logs = "".join(o.get("logs", "") for o in item.get("outputs") or [] if o.get("type") == "logs")
            call.code_runs.append({"code": item.get("code", ""), "output": logs})
        elif item.get("type") == "web_search_call":
            action = item.get("action") or {}
            call.web_calls.append({
                "type": "web_fetch" if action.get("type") in ("open_page", "fetch") else "web_search",
                "status": item.get("status"),
                "query": action.get("query"),
                "url": action.get("url"),
            })
    return final, call


async def chat(
    *,
    role: str,
    model: str,
    messages: list[dict],
    response_format: dict | None = None,
    tools: list[dict] | None = None,
    metadata: dict[str, str] | None = None,
    conversation_id: str | None = None,
    max_tokens: int = 1500,
    temperature: float | None = 0,
    api_key: str | None = None,
    headers: dict | None = None,
    extra: dict | None = None,
) -> tuple[str, Call]:
    """POST /api/v1/chat/completions (streamed). Returns (assistant text, Call)."""
    body: dict[str, Any] = {
        "model": model, "messages": messages, "max_tokens": max_tokens, "stream": True,
        "stream_options": {"include_usage": True},
        "metadata": {"app": "sade", "role": role, **(metadata or {})},
    }
    if temperature is not None:
        body["temperature"] = temperature
    if response_format:
        body["response_format"] = response_format
    if tools:
        body["tools"] = tools
    body.update(extra or {})

    call = Call(role=role, model_requested=model)
    parts: list[str] = []
    web: dict[str, dict] = {}
    async for event in _stream("chat/completions", body, call, _headers(api_key, conversation_id, headers)):
        for choice in event.get("choices") or []:
            parts.append((choice.get("delta") or {}).get("content") or "")
        for tc in event.get("otari_tool_calls") or []:
            web[tc["id"]] = tc  # the ended entry replaces the started one
        if event.get("usage"):
            call.cost_usd = float(event["usage"].get("cost_usd") or 0)
            call.tokens = event["usage"].get("total_tokens")
    call.web_calls = list(web.values())
    return "".join(parts), call


def output_text(data: dict) -> str:
    """Concatenate the assistant text of a Responses API result."""
    parts = []
    for item in data.get("output", []):
        if item.get("type") == "message":
            for c in item.get("content") or []:
                if c.get("type") in ("output_text", "text"):
                    parts.append(c.get("text", ""))
    return "".join(parts) or data.get("output_text", "")


def parse_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`").removeprefix("json").strip()
    return json.loads(text)


def output_json(data: dict) -> dict:
    return parse_json(output_text(data))
