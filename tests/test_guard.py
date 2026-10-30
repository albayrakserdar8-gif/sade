from fastapi.testclient import TestClient

from sade import config, guard
from sade.main import app


def test_check_pii():
    assert guard.check_pii("T.C. Kimlik No: [TCKN_1], IBAN: [IBAN_1]")["valid"] is True
    blocked = guard.check_pii("T.C. Kimlik No: 11111111110")
    assert blocked["valid"] is False and "T.C. kimlik no" in blocked["explanation"]


def test_validate_follows_otari_contract(monkeypatch):
    monkeypatch.setattr(config, "PUBLIC_SECRET", "s3cret")
    client = TestClient(app)
    body = {"profile": "tr-pii", "input_text": "IBAN: TR33 0006 1005 1978 6457 8413 26", "validate_kwargs": {}}
    r = client.post("/x/s3cret/guard/run-1/validate", json=body)
    assert r.status_code == 200
    data = r.json()
    assert data["profile"] == "tr-pii"
    assert data["result"]["valid"] is False and data["result"]["score"] == 1.0
    assert guard.GUARD_LOG.pop("run-1")[0]["profile"] == "tr-pii"
    # Wrong secret: not found.
    assert client.post("/x/wrong/guard/run-1/validate", json=body).status_code == 404


def test_tunnel_cannot_reach_the_app(monkeypatch):
    monkeypatch.setattr(config, "PUBLIC_SECRET", "s3cret")
    client = TestClient(app)
    assert client.get("/api/samples").status_code == 200
    assert client.get("/api/samples", headers={"cf-ray": "abc"}).status_code == 404
