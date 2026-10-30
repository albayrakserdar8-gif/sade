# Sade

**Plain-language help with Turkish official letters.**

Tax notices, enforcement orders, landlord notices and e-Devlet notifications are
written in dense legal Turkish. People miss deadlines (objection periods, payment
windows) and lose money or rights because of it. Sade reads such a letter (PDF or
phone photo) and tells you, in plain Turkish, what it is, what you need to do and
by when, and drafts a reply if one is needed.

Personal data (national ID numbers, IBANs, phone numbers, e-mail addresses,
licence plates, names and addresses) is masked before any text leaves the app.

> Status: work in progress for MozFest *Developers Wilding: Online*.

## How it uses Otari

Every AI call goes through the [Otari](https://otari.ai) gateway to open-weight
models. `src/sade/otari.py` is a thin HTTP client that also reads Otari's
routing headers and per-request cost, so the UI can show which model answered
and what it cost.

## Run it

```bash
cp .env.example .env                     # add your Otari API key
uv sync
uv run python scripts/make_samples.py   # fake sample letters into samples/
uv run sade                              # http://127.0.0.1:8000
uv run pytest
```

The sample letters are invented: every person, number and address in them is fake.

## Disclaimer

Sade does not give legal advice. For important decisions, talk to a lawyer or
the issuing office.
