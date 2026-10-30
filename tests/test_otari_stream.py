"""The policy-fallback workaround in otari.py, against fake SSE streams."""

import asyncio
import json

import httpx
import pytest

from sade import otari

ERR_401 = {"error": {"message": "The provider rejected the gateway's credentials",
                     "type": "server_error", "code": "provider_credential_rejected"}}


def sse(*events: dict, done: bool = False) -> bytes:
    lines = [": keepalive"]
    for e in events:
        if e.get("type"):
            lines.append(f"event: {e['type']}")
        lines.append("data: " + json.dumps(e))
        lines.append("")
    if done:
        lines.append("data: [DONE]")
    return ("\n".join(lines) + "\n").encode()


def completed(text: str) -> list[dict]:
    resp = {"output": [{"type": "message", "content": [{"type": "output_text", "text": text}]}],
            "usage": {"cost_usd": "0.001", "total_tokens": 10}}
    return [{"type": "response.created"}, {"type": "response.output_text.delta", "delta": text},
            {"type": "response.completed", "response": resp}]


@pytest.fixture
def fake_otari(monkeypatch):
    """Answer per requested model; record the order of requested models."""
    seen: list[str] = []
    answers: dict[str, tuple[int, bytes]] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        model = json.loads(request.content)["model"]
        seen.append(model)
        status, body = answers[model]
        headers = {"otari-request-id": f"req-{model}", "otari-model": f"served-{model}",
                   "otari-provider": "prov", "otari-attempt-count": "1"}
        return httpx.Response(status, content=body, headers=headers)

    monkeypatch.setattr(otari, "TRANSPORT", httpx.MockTransport(handler))
    return seen, answers


def run(coro):
    return asyncio.run(coro)


def test_error_before_output_moves_to_next_policy(fake_otari):
    seen, answers = fake_otari
    answers["policy-a"] = (200, sse(ERR_401))
    answers["policy-b"] = (200, sse(*completed('{"ok": true}')))
    data, call = run(otari.responses(role="analyze", model="policy-a", input="x", fallback_models=["policy-b"]))
    assert seen == ["policy-a", "policy-b"]
    assert otari.output_json(data) == {"ok": True}
    assert call.client_fallback is True and call.model_requested == "policy-b"
    assert call.failed_attempts == [{
        "model": "policy-a", "served": "served-policy-a", "provider": "prov",
        "code": "provider_credential_rejected", "status": 502, "request_id": "req-policy-a",
        "duration_ms": call.failed_attempts[0]["duration_ms"],
    }]


def test_error_after_output_is_not_retried(fake_otari):
    seen, answers = fake_otari
    answers["policy-a"] = (200, sse({"type": "response.created"},
                                    {"type": "response.output_text.delta", "delta": "Mer"}, ERR_401))
    answers["policy-b"] = (200, sse(*completed("{}")))
    with pytest.raises(otari.OtariError) as e:
        run(otari.responses(role="analyze", model="policy-a", input="x", fallback_models=["policy-b"]))
    assert seen == ["policy-a"] and not e.value.before_output


@pytest.mark.parametrize("code", ["guardrail_violation", "budget_exceeded"])
def test_refusals_are_not_retried(fake_otari, code):
    seen, answers = fake_otari
    answers["policy-a"] = (403, json.dumps({"detail": "no", "code": code}).encode())
    with pytest.raises(otari.OtariError) as e:
        run(otari.chat(role="classify", model="policy-a", messages=[], fallback_models=["policy-b"]))
    assert seen == ["policy-a"] and e.value.code == code


def test_chat_retries_and_keeps_text(fake_otari):
    seen, answers = fake_otari
    answers["policy-a"] = (200, sse(ERR_401, done=True))
    chunk = {"choices": [{"delta": {"content": "Merhaba"}}]}
    usage = {"choices": [], "usage": {"cost_usd": "0.0001", "total_tokens": 5}}
    answers["policy-b"] = (200, sse(chunk, usage, done=True))
    text, call = run(otari.chat(role="draft", model="policy-a", messages=[], fallback_models=["policy-b"]))
    assert text == "Merhaba" and seen == ["policy-a", "policy-b"]
    assert call.client_fallback and call.cost_usd == 0.0001


def test_last_policy_failure_is_raised_with_history(fake_otari):
    seen, answers = fake_otari
    answers["policy-a"] = (200, sse(ERR_401))
    answers["policy-b"] = (200, sse(ERR_401))
    with pytest.raises(otari.OtariError) as e:
        run(otari.responses(role="analyze", model="policy-a", input="x", fallback_models=["policy-b"]))
    assert seen == ["policy-a", "policy-b"]
    assert [a["model"] for a in e.value.call.failed_attempts] == ["policy-a"]
