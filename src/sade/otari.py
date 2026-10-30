"""A thin client for the Otari gateway (OpenAI-compatible, plus Otari's own
fields and headers).

We call the HTTP API directly rather than through an SDK so that every
Otari-specific piece is visible: routing headers, built-in tools, MCP
servers, guardrails, request tags and per-request cost.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from typing import Any

import httpx

from . import config


class OtariError(Exception):
    def __init__(self, status: int, code: str | None, detail: Any, headers: dict[str, str]):
        self.status, self.code, self.detail, self.headers = status, code, detail, headers
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


def _headers(api_key: str | None, conversation_id: str | None) -> dict[str, str]:
    h = {
        "Authorization": f"Bearer {api_key or config.OTARI_API_KEY}",
        "Content-Type": "application/json",
    }
    if conversation_id:
        h["Otari-Conversation-Id"] = conversation_id
    return h


def _fill_from_headers(call: Call, headers: httpx.Headers, started: float) -> None:
    call.request_id = headers.get("otari-request-id")
    call.model_served = headers.get("otari-model")
    call.provider = headers.get("otari-provider")
    call.fallback = headers.get("otari-fallback") == "true"
    attempts = headers.get("otari-attempt-count")
    call.attempts = int(attempts) if attempts and attempts.isdigit() else None
    call.duration_ms = int((time.monotonic() - started) * 1000)


def _raise_for_status(resp: httpx.Response) -> None:
    if resp.status_code < 400:
        return
    try:
        body = resp.json()
    except ValueError:
        body = {"detail": resp.text}
    detail = body.get("detail", body)
    code = body.get("code") or (detail.get("code") if isinstance(detail, dict) else None)
    code = code or resp.headers.get("otari-error-code")
    raise OtariError(resp.status_code, code, detail, dict(resp.headers))


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
    max_output_tokens: int = 2000,
    api_key: str | None = None,
    extra: dict | None = None,
) -> tuple[dict, Call]:
    """POST /api/v1/responses. Returns (response JSON, Call)."""
    body: dict[str, Any] = {"model": model, "input": input, "max_output_tokens": max_output_tokens}
    if instructions:
        body["instructions"] = instructions
    if text_format:
        body["text"] = {"format": text_format}
    if tools:
        body["tools"] = tools
    body["metadata"] = {"app": "sade", "role": role, **(metadata or {})}
    body.update(extra or {})

    call = Call(role=role, model_requested=model)
    started = time.monotonic()
    async with httpx.AsyncClient(timeout=240) as client:
        resp = await client.post(
            f"{config.OTARI_API_BASE}/api/v1/responses",
            headers=_headers(api_key, conversation_id),
            json=body,
        )
    _fill_from_headers(call, resp.headers, started)
    try:
        _raise_for_status(resp)
    except OtariError as e:
        call.error = f"{e.status} {e.code or ''}".strip()
        e.call = call  # type: ignore[attr-defined]
        raise
    data = resp.json()
    usage = data.get("usage") or {}
    call.cost_usd = float(usage.get("cost_usd") or 0)
    call.tokens = usage.get("total_tokens")
    for item in data.get("output", []):
        if item.get("type") == "code_interpreter_call":
            logs = "".join(o.get("logs", "") for o in item.get("outputs") or [] if o.get("type") == "logs")
            call.code_runs.append({"code": item.get("code", ""), "output": logs})
    return data, call


def output_text(data: dict) -> str:
    """Concatenate the assistant text of a Responses API result."""
    parts = []
    for item in data.get("output", []):
        if item.get("type") == "message":
            for c in item.get("content") or []:
                if c.get("type") in ("output_text", "text"):
                    parts.append(c.get("text", ""))
    return "".join(parts) or data.get("output_text", "")


def output_json(data: dict) -> dict:
    text = output_text(data).strip()
    if text.startswith("```"):
        text = text.strip("`").removeprefix("json").strip()
    return json.loads(text)
