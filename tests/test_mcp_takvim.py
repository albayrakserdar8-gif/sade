from sade import mcp_takvim


def test_holidays_and_business_day():
    names = [h["ad"] for h in mcp_takvim.resmi_tatiller(2026, None)]
    assert "Cumhuriyet Bayramı" in names
    r = mcp_takvim.is_gunu_mu("2026-11-21", None)
    assert r["is_gunu"] is False and r["sonraki_is_gunu"] == "2026-11-23"
    assert mcp_takvim.is_gunu_mu("29.10.2026", None)["neden"] == "Cumhuriyet Bayramı"


def test_calendar_event_is_personalized_locally():
    r = mcp_takvim.takvim_etkinligi_olustur("Kira öde", "2026-11-23", "[IBAN_1] hesabına öde", None)
    mcp_takvim.personalize(r["ics_id"], lambda t: t.replace("[IBAN_1]", "TR33 0006"))
    filename, data = mcp_takvim.ics_bytes(r["ics_id"])
    text = data.decode()
    assert filename == "sade-2026-11-23.ics"
    assert "DTSTART;VALUE=DATE:20261123" in text
    assert "TR33 0006 hesabına öde" in text and "[IBAN_1]" not in text
    assert "TRIGGER:-P2D" in text
