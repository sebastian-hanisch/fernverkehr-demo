"""PDF-Export: Sonderzeichen-Bereinigung (fpdf2 stürzt bei Gedankenstrich, Euro-Zeichen, Emoji und dem Minuszeichen U+2212 ab - mit den
GENAUEN Zeichen testen), Erzeugung für jede Zelle, unzulässige Zellen, Inhalte im unkomprimierten PDF."""
import pytest

import fv_constants as C
import fv_results as R
from fv_pdf_export import generate_fv_pdf, pdf_text
from fv_ui_panel import matching_series, message
from live_cache import fresh_copy, get_live

DATA = R.load_results()


def test_pdf_text_replaces_en_dash_and_em_dash():
    assert "–" not in pdf_text("Fahrt – Pause") and "—" not in pdf_text("Fahrt — Pause")
    assert pdf_text("a – b") == "a - b" and pdf_text("a — b") == "a - b"


def test_pdf_text_replaces_euro_sign_with_eur():
    assert pdf_text("100 €") == "100 EUR" and "€" not in pdf_text("100 €")


def test_pdf_text_replaces_unicode_minus_sign_with_ascii():
    assert pdf_text("−5 %") == "-5 %" and pdf_text("−") == "-"


def test_pdf_text_strips_or_replaces_emoji_and_symbols():
    cleaned = pdf_text("🚛 📐 🎯 📊 🔧 🎲 ✅ ℹ️ ⚠️ 🗺️ 🔁 📈 📄 ≥ ≤ → ≈ ± · „x“ ‘y’")
    cleaned.encode("latin-1")
    assert "🚛" not in cleaned and ">=" in cleaned and "<=" in cleaned and "->" in cleaned and "+-" in cleaned and '"x"' in cleaned


def test_pdf_text_keeps_german_umlauts():
    text = pdf_text("Übernachtungen für Lkw – Größe ß")
    assert text == "Übernachtungen für Lkw - Größe ß"


def test_pdf_text_result_is_always_latin1_encodable():
    tricky = "Gang–Route € ≥ ≤ → ≈ ± · „x“ ‘y’ ⚠️ ✅ ℹ️ 🚛📐🎯 − Ω λ 日本 ‑ ▶"
    pdf_text(tricky).encode("latin-1")


def test_core_font_really_renders_the_cleaned_literal_characters():
    """Die kritischen Zeichen laufen durch pdf_text und lassen fpdf2 nicht abstürzen; ungereinigt stürzt es ab."""
    from fpdf import FPDF
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 7, pdf_text("– € 🚛 − ≥ Übernachtung Größe"))
    assert bytes(pdf.output())[:4] == b"%PDF"
    raw = FPDF()
    raw.add_page()
    raw.set_font("Helvetica", "", 10)
    with pytest.raises(Exception):
        raw.cell(0, 7, "– € −")
        bytes(raw.output())


def _pdf(res, cell=C.CELL_FE, compress=True, **over):
    x = None
    costs = {c: res["cells"][c]["total"] for c in C.CELLS}
    if all(v is not None for v in costs.values()):
        x = R.interaction_from_costs(costs)
    _, text = message(res, x, DATA)
    settings = dict(customers=res["n"], charge=res["charge"], range_km=res["range_km"], window=res["window"], seed=res["seed_index"])
    settings.update(over)
    series = [(R.number_label(DATA[n]), R.Stat.from_dict(DATA[n]["I"])) for n in matching_series(res, DATA)]
    return generate_fv_pdf(settings, res, cell, x, text, series, compress=compress)


def _plain(data):
    """Text der unkomprimierten PDF-Seiten; Klammern sind in PDF-Zeichenketten maskiert."""
    return data.decode("latin-1").replace("\\(", "(").replace("\\)", ")")


@pytest.mark.parametrize("cell", C.CELLS)
def test_pdf_generation_for_every_cell(cell):
    data = _pdf(get_live(), cell)
    assert data[:4] == b"%PDF" and len(data) > 2000


def test_pdf_generation_for_every_window_and_range():
    for window in C.WINDOW_OPTIONS:
        assert _pdf(get_live(6, 45, 400, window, 20))[:4] == b"%PDF"
    for r in C.RANGE_OPTIONS:
        assert _pdf(get_live(6, 45, r, "mittel", 4))[:4] == b"%PDF"


def test_pdf_with_an_infeasible_electric_cell_does_not_crash():
    res = get_live(6, 45, 300, "keine", 10)                   # echte Lage ohne zulässige Elektro-Lösung
    assert not res["cells"][C.CELL_E]["feasible"]
    for cell in C.CELLS:
        assert _pdf(res, cell)[:4] == b"%PDF"


def test_pdf_without_matching_series_and_without_message_is_still_valid():
    res = get_live()
    assert generate_fv_pdf(dict(customers=6, charge=45, range_km=400, window="mittel", seed=1), res, C.CELL_FE, None, "", [])[:4] == b"%PDF"


def test_pdf_text_contains_the_key_numbers_when_uncompressed():
    res = get_live()
    text = _plain(_pdf(res, C.CELL_FE, compress=False))
    x = R.interaction_from_costs({c: res["cells"][c]["total"] for c in C.CELLS})
    assert "Fernverkehr: Fahrerregeln und Elektro-Lkw" in text and "Wechselwirkung I" in text
    assert f"{x['I_pct']:+.1f}".replace(".", ",") in text
    assert f"{res['cells'][C.CELL_FE]['total']:,.0f}".replace(",", ".") in text
    assert "Fahrplan: beides (F+E)" in text and "Lkw 1: Depot" in text and "Tagesruhe" in text
    assert "18 Kunden, 3 Lkw, 60 Instanzen" in text and "10 Kunden, 2 Lkw, 60 Instanzen" in text
    assert "erfunden, nicht kalibriert" in text and "60 gepaarte" in text


def test_pdf_lists_every_stop_of_the_chosen_cell():
    res = get_live()
    text = _plain(_pdf(res, C.CELL_F, compress=False))
    for t in res["cells"][C.CELL_F]["trucks"]:
        assert f"Lkw {t['truck']}: Depot" in text
        for c in t["route"]:
            assert f"Kunde {c}" in text
    assert "Fahrplan: Fahrerregeln (F)" in text


def test_pdf_shows_seed_and_settings():
    text = _plain(_pdf(get_live(), compress=False, seed=77))
    assert "Typische Ladezeit" in text and "45 min" in text and "400 km" in text and "mittel" in text and "77 (" in text


def test_long_plans_span_several_pages_without_error():
    res = fresh_copy(get_live(6, 45, 400, "mittel", 4))
    # Halteliste künstlich verlängern: viele Ereignisse erzwingen einen Seitenumbruch
    t = res["cells"][C.CELL_FE]["trucks"][0]
    last = t["events"][-1][2]
    extra = [("wait", last + 10 * i, last + 10 * (i + 1), 1) for i in range(120)]
    t["events"] = list(t["events"]) + extra
    data = _pdf(res, compress=False)
    assert data[:4] == b"%PDF" and data.count(b"/Type /Page\n") >= 3 and _plain(data).count("Warten") >= 120
