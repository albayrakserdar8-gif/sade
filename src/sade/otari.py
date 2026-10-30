"""A thin client for the Otari gateway (OpenAI-compatible, plus Otari's own
fields and headers).

We call the HTTP API directly rather than through an SDK so that every
Otari-specific piece is visible: routing headers, built-in tools, MCP
servers, guardrails, request tags and per-request cost.

Requests are always streamed: the hosted gateway sits behind an edge that
cuts non-streamed responses after ~30 s, and tool loops (code, web search,
MCP) or OCR on a large image take longer than that.

Fallback across policies (a workaround). Otari routing policies fall back
to their next candidate when a provider fails. On hosted Otari that does
not happen for streamed requests that declare gateway-run tools (code
execution, web search, MCP): the first candidate's failure arrives as an
SSE error event before any output (see FEEDBACK.md and the Otari issue).
So when a request fails *before any output* with a provider error, we send
the same request to the next Otari policy in `fallback_models`. Model
choice still lives in Otari's policies; we only do the hop Otari skipped.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from typing import Any, AsyncIterator, Awaitable, Callable, TypeVar

import httpx

from . import config

# Provider failures that are safe to retry on another policy, as long as no
# output has been streamed yet.
RETRYABLE_BEFORE_OUTPUT = {
    "provider_credential_rejected",
    "provider_error",
    "provider_not_configured",
    "upstream_rate_limited",
    "provider_stream_interrupted",
    "provider_timeout",
}

# Tests inject an httpx.MockTransport here.
TRANSPORT: httpx.AsyncBaseTransport | None = None


class OtariError(Exception):
    def __init__(self, status: int, code: str | None, detail: Any, headers: dict[str, str],
                 before_output: bool = False):
        self.status, self.code, self.detail, self.headers = status, code, detail, headers
        self.before_output = before_output
        self.call: Call | None = None
        super().__init__(f"Otari {status} {code or ''}: {detail}")

    @property
    def retryable(self) -> bool:
        """Failed before any output, for a reason another policy may not share."""
        if not self.before_output:
            return False
        return self.code in RETRYABLE_BEFORE_OUTPUT or self.status >= 500 or self.status == 424


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
    # Set when the app had to retry on the next policy (the workaround above).
    client_fallback: bool = False
    failed_attempts: list[dict] = field(default_factory=list)

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
    # Nothing was streamed, so any HTTP error is "before output".
    return OtariError(resp.status_code, code or resp.headers.get("otari-error-code"), detail,
                      dict(resp.headers), before_output=True)


def _is_error_event(event: dict) -> bool:
    return event.get("type") in ("error", "response.failed") or ("error" in event and not event.get("choices"))


def _error_code(event: dict) -> str:
    err = event.get("error") or (event.get("response") or {}).get("error") or {}
    return (err.get("code") if isinstance(err, dict) else None) or "stream_error"


def _carries_output(event: dict) -> bool:
    """Has anything reached the client that a retry would duplicate?"""
    if event.get("type") in ("response.created", "response.in_progress"):
        return False
    if "choices" in event:  # chat chunk
        if event.get("otari_tool_calls"):
            return True
        for choice in event["choices"] or []:
            delta = choice.get("delta") or {}
            if delta.get("content") or delta.get("tool_calls"):
                return True
        return False
    return True


async def _stream(path: str, body: dict, call: Call, headers: dict) -> AsyncIterator[dict]:
    """POST and yield each SSE `data:` JSON object."""
    started = time.monotonic()
    async with httpx.AsyncClient(timeout=httpx.Timeout(300, connect=15), transport=TRANSPORT) as client:
        async with client.stream("POST", f"{config.OTARI_API_BASE}/api/v1/{path}", headers=headers, json=body) as resp:
            _fill_from_headers(call, resp.headers)
            if resp.status_code >= 400:
                err = await _error_from(resp)
                call.error = f"{err.status} {err.code or ''}".strip()
                call.duration_ms = int((time.monotonic() - started) * 1000)
                err.call = call
                raise err
            seen_output = False
            async for line in resp.aiter_lines():
                if not line.startswith("data:"):
                    continue  # `event:` lines and `: keepalive` comments
                data = line[5:].strip()
                if not data or data == "[DONE]":
                    continue
                event = json.loads(data)
                if _is_error_event(event):
                    code = _error_code(event)
                    err = OtariError(502, code, event.get("error") or event, dict(resp.headers),
                                     before_output=not seen_output)
                    call.error = code
                    call.duration_ms = int((time.monotonic() - started) * 1000)
                    err.call = call
                    raise err
                seen_output = seen_output or _carries_output(event)
                yield event
    call.duration_ms = int((time.monotonic() - started) * 1000)


T = TypeVar("T")


async def _with_policy_fallbacks(
    models: list[str], attempt: Callable[[str], Awaitable[tuple[T, Call]]]
) -> tuple[T, Call]:
    """Try each policy in turn while failures happen before any output."""
    failed: list[dict] = []
    for i, model in enumerate(models):
        try:
            result, call = await attempt(model)
        except OtariError as e:
            if e.call:
                e.call.failed_attempts = failed + e.call.failed_attempts
            if i + 1 < len(models) and e.retryable:
                c = e.call
                failed.append({
                    "model": model,
                    "served": c.model_served if c else None,
                    "provider": c.provider if c else None,
                    "code": e.code,
                    "status": e.status,
                    "request_id": c.request_id if c else None,
                    "duration_ms": c.duration_ms if c else None,
                })
                continue
            raise
        call.client_fallback = i > 0
        call.failed_attempts = failed
        return result, call
    raise AssertionError("unreachable")


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
    fallback_models: list[str] | None = None,
) -> tuple[dict, Call]:
    """POST /api/v1/responses (streamed). Returns (final response object, Call)."""

    async def once(m: str) -> tuple[dict, Call]:
        body: dict[str, Any] = {
            "model": m, "input": input, "max_output_tokens": max_output_tokens, "stream": True,
            "metadata": {"app": "sade", "role": role, **(metadata or {})},
        }
        if instructions:
            body["instructions"] = instructions
        if text_format:
            body["text"] = {"format": text_format}
        if tools:
            body["tools"] = tools
        body.update(extra or {})

        call = Call(role=role, model_requested=m)
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

    return await _with_policy_fallbacks([model, *(fallback_models or [])], once)


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
    fallback_models: list[str] | None = None,
) -> tuple[str, Call]:
    """POST /api/v1/chat/completions (streamed). Returns (assistant text, Call)."""

    async def once(m: str) -> tuple[str, Call]:
        body: dict[str, Any] = {
            "model": m, "messages": messages, "max_tokens": max_tokens, "stream": True,
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

        call = Call(role=role, model_requested=m)
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

    return await _with_policy_fallbacks([model, *(fallback_models or [])], once)


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
