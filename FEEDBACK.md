# Otari feedback

Feedback from building [Sade](README.md) on hosted otari.ai for MozFest
*Developers Wilding: Online*: two weeks, one developer, all AI calls through
Otari, open-weight models only. The summary comes first, then the notes we
kept while building, with reproduction steps.

Issue opened from this work: [mozilla-ai/otari#2727](https://github.com/mozilla-ai/otari/issues/2727),
streamed requests with gateway-run tools don't fall back to the next routing candidate.
(The GitHub account that opened it was suspended on 30 October, so the issue is
hidden for now; its full text is the "Bug: routing fallback…" section below.)

## The three questions

**When were you most tempted to bypass Otari and call the provider directly, and what happened?**

Three times.
1. A vision request (OCR of a phone photo) died after 30 s with a CloudFront 504
   HTML page, because hosted Otari cuts non-streamed responses at the edge. We
   stayed on Otari and moved every call to streaming.
2. Our fallback policy fell back fine in a quick test, but not once the
   analysis call declared code execution, web search and MCP. Writing our own
   provider failover against DeepInfra/Fireworks directly looked easier than
   debugging the gateway. We stayed on Otari: the app now retries on a second
   Otari policy, and we filed #2727.
3. Every guardrail in the catalog needs a third-party key, and `any_llm` is
   closed to tenants. We nearly ran Qwen3Guard / gpt-oss-safeguard as a
   plain model call in our own code and skipped Otari's guardrails. Instead we
   kept Otari's request-level `guardrails` and pointed them at a small
   `/validate` service of ours, which calls gpt-oss-safeguard *through* Otari.

**What did you build yourself that Otari should have handled?**

- **Fallback across policies** for streamed tool requests (the #2727 workaround):
  detect an SSE error before any output, resend to the next policy.
- **A keyless open-model guardrail**: a `/validate` service with a Turkish PII
  check and an injection judge, exposed through a Cloudflare tunnel so Otari
  can call it. Otari already serves the judge model; it should be able to
  run it as a guardrail on the organization's own key.
- **Per-user budgets for an app's own users**: one Otari API key per user,
  created by hand, plus our own spend tally, because tenants can't create
  service keys and an API key can't read its remaining budget.
- **Visibility of tool calls**: MCP calls are not reported in Chat or
  Responses output, so our MCP server logs calls per run; Responses
  `web_search_call` items carry no result URLs, so the model has to repeat them.
- **A public tunnel** so the hosted gateway can reach our MCP server and
  guardrail service.
- **A safe way to test fallbacks**: we added a deliberately broken provider
  key, which also breaks that provider for everything else in the org.

**Would you keep using Otari if it weren't required? Why?**

Yes, for this kind of app. One key gave us 160 models, many open-weight, with
prices, and the gateway-run sandbox and web search work with *any* of them.
That is what lets an open model like DeepSeek V4.1 Flash compute deadlines in
code and check the law on the web. Routing policies, per-call cost in every
response, routing headers, budgets that refuse before any model runs, and
sessions on the dashboard are all things we would otherwise write ourselves.
What would make us hesitate on hosted: the 30 s edge cut for non-streamed
calls, #2727, tool costs we can't cap per request (sandbox runs and web searches are ~95% of
our bill), and the tenant gaps listed above.

## What worked well

- One key, 160 models, prices in `/api/v1/models`; open models with tools.
- Responses API + `code_interpreter` + `json_schema` on DeepSeek (no native
  Responses API): the sandbox ran, `code_interpreter_call` items came back with
  code and logs, and the answer matched the schema.
- `otari_web_search` found official sources in one call.
- Routing policies, set up in a minute in the dashboard; `Otari-Model`,
  `Otari-Provider`, `Otari-Fallback`, `Otari-Attempt-Count` headers.
- Inline `mcp_servers` to our own streamable-HTTP server, in the same tool
  loop as code and search.
- Request-level `guardrails` with our own URL: block mode returns `403
  guardrail_violation` and no model is called.
- Budgets: `403 budget_exceeded` with `Otari-Budget-Scope` and `Retry-After`.
- `metadata` + `Otari-Conversation-Id`: each analysis is one session on the
  dashboard.

## What didn't work (details and repro below)

- Streamed requests with gateway-run tools don't fall back (#2727).
- Non-streamed requests cut at ~30 s with a CloudFront HTML 504.
- Reopening the dashboard Overview silently revoked our API key.
- `/api/v1/tools` says web search is available while the workspace has web
  access off.
- Budget holds ignore tool costs: a $0.05/day key spent $0.083.
- `otari_web_fetch` rejects `max_uses`, `otari_web_search` accepts it.
- API keys list shows "Budget: None" for keys that have one; key ceilings are
  listed by id, not name.
- Seen once: an unreachable MCP server turned into a CloudFront 504 instead
  of a tool error.

## What's missing

- Service keys or end-user budgets for tenants on hosted, and a way for a key
  to read its remaining budget.
- Keyless guardrails on open models served by Otari.
- A per-request cap on sandbox runs, and sandbox/search cost broken out in the
  response.
- MCP calls and web-search sources in Chat/Responses output.
- A "simulate failure" switch for testing routing policies.
- Speech: no text-to-speech model in the catalog (`/api/v1/audio/speech`
  answers `invalid_model`), and `/api/v1/audio/transcriptions` with
  `mistralai/voxtral-mini-3b-2507` answers "Provider doesn't support audio
  transcription". We voiced the demo video locally instead (Ming-3.0-tts with
  mlx-audio) and checked it with a local Whisper.

## Notes kept while building

### 2026-10-30 — onboarding

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

### Wins

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

### Friction (continued)

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
- **No way to test a fallback chain on hosted without breaking something.**
  To show a fallback live we added a deliberately invalid Together AI provider
  key (named `outage-sim`) and made a policy whose main candidate is DeepSeek
  on Together. It works (`Otari-Attempt-Count: 2`, `Otari-Fallback: true`),
  but the bogus key also becomes the org's Together default, so any request
  that would be served by Together now fails over too. A "simulate failure"
  option on a policy candidate (or a test header) would make this safe.
- Routing policy UI: creating a fallback is quick, but the model combobox list
  doesn't narrow while typing in some cases, and dropdown popovers stay
  floating on the page after the dialog loses focus.
- **Sandbox runs dominate cost and the model decides how many.** One letter
  analysis made 9 `code_interpreter` calls (~$0.01 each, $0.09 total) while
  the tokens cost $0.0005. `max_tool_iterations: 3` plus a prompt rule
  brought it to 2 runs. A per-request cap on code runs (like `max_uses` for
  search) or showing sandbox cost in the response would help.
- `{"type": "otari_web_fetch", "max_uses": 1}` is refused with
  `400 otari_web_fetch declarations may contain only the type field`, while
  `otari_web_search` accepts `max_uses`. Inconsistent; there's no way to cap
  fetches per request except the shared `web_search_max_calls`.
- In Responses API output, `web_search_call` items carry only the query, not
  the result URLs (Chat Completions gets `otari_tool_calls[].sources`). To
  show sources we had to ask the model to repeat the URLs it saw.
- Cost reality check for one analysis with tools: tokens ~$0.001, two
  sandbox runs ~$0.02, two web searches ~$0.03. Tools are 98% of the bill.
- **MCP over a tunnel works well.** Inline `mcp_servers` pointing at our own
  streamable-HTTP server (Python `mcp` 2.x, behind a Cloudflare quick tunnel)
  worked on the Responses API with DeepSeek: the model called all three tools
  (holidays, working-day check, create calendar event) in the same tool loop
  as code execution and web search. Putting a run id in the server URL was
  the only way to show MCP calls in our UI, since Chat/Responses output does
  not report them.
- Seen once: while our MCP server was restarting, the streamed Responses call
  came back as a CloudFront `504` HTML page after ~30 s, not as a JSON error or
  an MCP tool error the model could recover from. Likely the gateway waits on
  the MCP connection before sending any bytes.
- **Request-level guardrails with our own endpoint: works, and is the only
  keyless option for a tenant.** Every catalog guardrail needs a third-party
  key and `any_llm` is closed to organizations, so we wrote a tiny `/validate`
  service (PII regex + `gpt-oss-safeguard-120b` through Otari as an
  injection judge) and passed it as `guardrails: [{profile, url, mode:
  "block"}]`. Works on both Chat Completions and Responses; a hidden prompt
  injection in a sample letter comes back as `403 guardrail_violation` with
  our explanation, and no model is called. Would love a built-in way to use
  an Otari-served open model as the judge (e.g. `any_llm` on the org's own
  Otari key) so we don't need a public callback.
- Tried `qwen3guard-gen-8b` first: fine for harm categories, but it labelled a
  letter with an embedded "ignore previous instructions" note as
  `Controversial / PII`, not as an injection. `gpt-oss-safeguard-120b` with a
  written policy got all three samples right.
- Guardrail `input_text` is only the latest user message. Fine for us (the
  letter is the user message), but surprising if the risky content is in a
  system prompt or earlier turn.
- **Per-user budgets for an app's own users on hosted: one key per user.**
  No service keys for tenants, so each demo user got an API key with its own
  budget (dashboard: Create key → Budget). Enforcement works: once over
  budget, the next request is `403 budget_exceeded` with
  `Otari-Budget-Scope: api_token` and `Retry-After`. But this does not scale
  to real end users (a key per user, created by hand, all billed to me).
- **Budget holds ignore tool costs, so caps overshoot.** A key with a $0.05
  daily cap ran three analyses ($0.021 + $0.021 + $0.041 = $0.083) before the
  fourth was refused. The pre-dispatch hold only prices output tokens; the
  sandbox and web-search charges (most of the bill) land afterwards.
- API keys list shows **Budget: None** for keys that do have a budget (their
  ceilings show correctly under Spend & budgets).
- Spend ceilings on keys are listed as "An API key (4a6a2e43…)" — the key's
  name isn't shown, so with several keys you can't tell which is which.
- An API key cannot read its own remaining budget, so the app keeps its own
  tally from `usage.cost_usd` to show users how much they have left.

### Bug: routing fallback does not happen on streamed requests with gateway-run tools

Filed as [mozilla-ai/otari#2727](https://github.com/mozilla-ai/otari/issues/2727).

**Repro (hosted otari.ai, 30 Oct 2026).** Policy `sade-analyst-demo`: main
candidate DeepSeek V4.1 Flash 1017 on Together AI with an invalid org key
(so it fails with 401), backup DeepSeek V4.1 Flash 1017 on DeepInfra.

| Request | Result |
|---|---|
| `POST /responses`, `stream: true`, no tools | 200, `Otari-Fallback: true`, `Otari-Attempt-Count: 2` |
| same + `guardrails` only | falls back |
| same + `tools: [{"type": "code_interpreter"}]` | stream error `provider_credential_rejected`, no fallback |
| same + `tools: [{"type": "otari_web_search"}]` | same error, no fallback |
| same + inline `mcp_servers` | same error, no fallback |
| `POST /responses`, **not streamed**, + `code_interpreter` | falls back (attempt 2) |
| `POST /chat/completions`, `stream: true`, + `otari_code_execution` | `Otari-Attempt-Count: 1`, `data: {"error": {... "provider_credential_rejected"}}` |

So with streaming plus any gateway-run tool, the first candidate's failure is
streamed to the client instead of moving to `on_failure`, even though nothing
had been generated yet. On hosted, non-streamed requests are cut at ~30 s by
the edge, so for long tool-using requests there is effectively no fallback.
Workaround in Sade: when a streamed request fails with a provider error
before any output, the app resends it to the next Otari policy
(`sade-analyst-demo` → `sade-analyst` → `sade-analyst-backup`); see
`_with_policy_fallbacks` in `src/sade/otari.py`. Otari's own source and docs
say the first round of a sandbox/web-search loop should fall over, so this
looks like a hosted-only regression; MCP-only streams are not held by design.
