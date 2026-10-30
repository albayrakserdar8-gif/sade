from datetime import date

from sade import dates


def test_expected_sample_deadlines():
    # Tax notice: served 16.10.2026, 30 days -> Sunday 15.11 -> Monday 16.11.
    d = dates.deadline(date(2026, 10, 16), 30)
    assert d["raw_end"] == "2026-11-15" and d["deadline"] == "2026-11-16" and d["shifted"]
    # Enforcement order: served 27.10.2026, 7 days objection, 10 days payment.
    assert dates.deadline(date(2026, 10, 27), 7)["deadline"] == "2026-11-03"
    assert dates.deadline(date(2026, 10, 27), 10)["deadline"] == "2026-11-06"
    # Rent notice: served 22.10.2026, 30 days -> Saturday 21.11 -> Monday 23.11.
    assert dates.deadline(date(2026, 10, 22), 30)["deadline"] == "2026-11-23"
    # Traffic fine via e-Tebligat: in the e-box 25.10 -> served 30.10, 15 days -> Sat 14.11 -> Mon 16.11.
    served = dates.e_tebligat_service_date(date(2026, 10, 25))
    assert served == date(2026, 10, 30)
    assert dates.deadline(served, 15)["deadline"] == "2026-11-16"


def test_holiday_shift():
    # 30 days after 29.09.2026 is 29.10.2026, Cumhuriyet Bayramı (Thursday) -> 30.10.
    d = dates.deadline(date(2026, 9, 29), 30)
    assert d["deadline"] == "2026-10-30"
    assert d["reason"] == "Cumhuriyet Bayramı"


def test_find_dates():
    found = dates.find_dates("Tebliğ Tarihi: 16.10.2026\nİhlal: 11 Ekim 2026 günü")
    assert [f["date"] for f in found] == ["2026-10-16", "2026-10-11"]
    assert found[0]["context"] == "Tebliğ Tarihi:"
