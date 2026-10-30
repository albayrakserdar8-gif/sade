# Otari feedback log

Friction and wins noted while building, for the final feedback submission.

## 2026-10-30 — onboarding

- **Reopening Overview silently revokes the API key.** The setup guide on the
  dashboard Overview shows a key "once". Navigating away and back to Overview
  issued a new key and revoked the one we had already copied into `.env`; the
  next request got `401 {"detail":"Invalid API key"}` with no hint why.
  Repro: sign up → copy key from Overview guide → open Billing → open Overview
  again → old key is invalid. Expected: keep the first key until the first
  request lands, or warn before replacing it.
- **Web access is off by default per workspace.** First `otari_web_search` /
  `otari_web_fetch` calls returned `web search is not enabled for this
  workspace` / `web access is not enabled for this workspace`. The message is
  clear, but `GET /api/v1/tools` reported both tools as `"available": true`, so
  discovery and reality disagree. Fixed by Tools → Web search → "Allow web access".
- **No service keys / end-user budgets on hosted (so far).** The docs describe
  `is_service_key` + `Otari-End-User-Budget` for per-end-user budgets, but the
  hosted "Create key" dialog has no such option and `/api/v1/keys`,
  `/api/v1/budgets` answer `Invalid master key` to a normal API key. Unclear how a
  hosted app is meant to do per-user budgets for its own users.
- **Guardrail catalog needs third-party keys.** Every guardrail in
  `/api/v1/tool-settings/guardrails/catalog` requires an external API key
  (Alinia, Lakera, Azure, OpenAI Moderation, …). Nothing runs out of the box on
  open models, even though the catalog lists open guard models (Qwen3Guard,
  Llama Guard 4) as chat models.

## Wins

- One key, 160 models (lots of open weights: Qwen, Llama, Gemma, Mistral,
  DeepSeek, gpt-oss) with prices in `/api/v1/models`.
- `otari_code_execution` worked first try with an open model (Qwen3-235B):
  date arithmetic in a sandbox, ~$0.01.
- `otari_web_search` found an official GİB (Turkish tax office) source in one call.
- Inline `usage.cost_usd` on every response is handy for budget UI.
- `/api/v1/responses` with `code_interpreter` + `text.format: json_schema` worked
  on DeepSeek V4.1 Flash (a provider without a native Responses API): the
  gateway ran the code in its sandbox, returned `code_interpreter_call` items
  with code and logs, and the final message matched the schema. First full
  letter analysis cost $0.0005.
- Routing headers (`Otari-Model`, `Otari-Provider`, `Otari-Fallback`,
  `Otari-Attempt-Count`) make it easy to show users which model actually answered.

## Friction (continued)

- Asking for `code_interpreter` with `"container": {"type": "auto"}` (the
  OpenAI shape) silently made the sandbox persist after the request
  (`Otari-Container-Expires-At` ~20 min later). Easy to miss that this holds a
  billed sandbox; the docs explain it, but the OpenAI default shape triggers it.
- **Non-streamed requests die at ~30 s with a CloudFront 504 HTML page.** A
  vision request (Qwen3-VL-235B, ~250 KB image) took ~50 s; without
  `stream: true` the client got `504 Gateway Timeout` HTML from CloudFront,
  not a JSON error, and no `Otari-Request-ID`. Streaming the same request
  works. Tool loops (code + search + MCP) easily pass 30 s, so on hosted every
  client effectively has to stream. Worth documenting, or raising the edge timeout.
