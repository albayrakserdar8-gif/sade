from sade import privacy


def test_tckn_checksum():
    assert privacy.is_valid_tckn("11111111110")
    assert privacy.is_valid_tckn("22222222220")
    assert not privacy.is_valid_tckn("11111111111")
    assert not privacy.is_valid_tckn("01111111110")
    assert not privacy.is_valid_tckn("2026048213")


def test_iban_checksum():
    assert privacy.is_valid_iban("TR33 0006 1005 1978 6457 8413 26")
    assert not privacy.is_valid_iban("TR34 0006 1005 1978 6457 8413 26")


def test_mask_and_unmask_roundtrip():
    text = (
        "Borçlu: Mehmet Demir (T.C. Kimlik No: 22222222220)\n"
        "Adresi: Deneme Cad. No:12 Bahçelievler/İstanbul\n"
        "IBAN: TR33 0006 1005 1978 6457 8413 26\n"
        "Tel: 0532 123 45 67, e-posta mehmet@example.com, Plaka 34 ABC 123\n"
        "Dosya No: 2026/48213, tutar 45.415,40 TL, tarih 27.10.2026\n"
    )
    m = privacy.mask(text)
    for secret in ["Mehmet Demir", "22222222220", "Bahçelievler", "TR33", "0532", "mehmet@", "34 ABC 123"]:
        assert secret not in m.text
    # Amounts, file numbers and dates must survive.
    for keep in ["2026/48213", "45.415,40 TL", "27.10.2026"]:
        assert keep in m.text
    assert m.counts == {"AD": 1, "ADRES": 1, "IBAN": 1, "TCKN": 1, "TELEFON": 1, "EPOSTA": 1, "PLAKA": 1}
    assert privacy.unmask(m.text, m.mapping) == text


def test_invalid_eleven_digit_number_is_not_masked():
    m = privacy.mask("Referans: 12345678901")
    assert m.mapping == {}
