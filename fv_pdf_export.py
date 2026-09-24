"""PDF-Export des Fahrplans der gezeigten Live-Instanz (fpdf2, Helvetica-Kernschrift, nur Text und Tabellen).

Die Kernschriften kennen nur Latin-1: Umlaute sind erlaubt, aber Gedankenstrich (U+2013), Minuszeichen (U+2212),
Euro-Zeichen, Emoji usw. lassen fpdf2 abstürzen. Deshalb läuft jeder Text durch pdf_text()."""
import time

import fv_constants as C
import fv_schedule as S

_REPLACEMENTS = {
    "–": "-", "—": "-", "‑": "-", "−": "-", "≥": ">=", "≤": "<=", "→": "->", "≈": "ca.", "€": "EUR", "±": "+-",
    "·": "-", "“": '"', "”": '"', "„": '"', "‘": "'", "’": "'", "⚠️": "(!)", "⚠": "(!)", "✅": "", "ℹ️": "",
    "🚛": "", "📐": "", "🎯": "", "📊": "", "🔧": "", "🎲": "", "🗺️": "", "🔁": "", "📈": "", "📄": "",
}


def pdf_text(text):
    """Text für die Helvetica-Kernschrift: bekannte Sonderzeichen ersetzen, den Rest Latin-1-sicher machen."""
    for old, new in _REPLACEMENTS.items():
        text = text.replace(old, new)
    return text.encode("latin-1", "replace").decode("latin-1")


def _de(v, digits=1, sign=False):
    text = f"{v:+.{digits}f}" if sign else f"{v:.{digits}f}"
    return text.replace(".", ",")


def _eur(v, sign=False):
    return (f"{v:+,.0f}" if sign else f"{v:,.0f}").replace(",", ".") + " EUR"


def _band(s):
    return f"{_de(s.mean, 1, True)} +- {_de(s.se)} %"


def generate_fv_pdf(settings, res, cell, x, message, series_rows, compress=True):
    """Fahrplan der gewählten Zelle als PDF: Einstellungen, Kennzahlen der vier Zellen, Meldung, Vergleich mit der Messreihe,
    Halteliste je Lkw, Hinweise zum Modell.

    settings: dict der Reglerwerte (customers, charge, range_km, window, seed); res: fv_live.solve_live; cell: Zelle des Fahrplans;
    x: fv_results.interaction_from_costs oder None (unzulässige Lage); message: Text der Meldung; series_rows: Liste
    (Beschriftung, Stat) der passenden Messreihen für Wechselwirkung I."""
    from fpdf import FPDF
    from fpdf.enums import XPos, YPos

    pdf = FPDF()
    pdf.set_compression(compress)
    pdf.add_page()

    def line(text, height=7, width=0):
        pdf.cell(width, height, pdf_text(text), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    def heading(text):
        pdf.set_font("Helvetica", "B", 12)
        line(text, 8)
        pdf.set_font("Helvetica", "", 10)

    def pairs(rows):
        for label, value in rows:
            pdf.cell(80, 6, pdf_text(label), border=0)
            line(value, 6)

    def table(headers, widths, rows, size=8):
        pdf.set_font("Helvetica", "B", size)
        pdf.set_fill_color(230, 230, 230)
        for header, width in zip(headers, widths):
            pdf.cell(width, 7, pdf_text(header), border=1, fill=True, new_x=XPos.RIGHT, new_y=YPos.TOP)
        pdf.ln(7)
        pdf.set_font("Helvetica", "", size)
        for row in rows:                                    # der automatische Seitenumbruch von fpdf2 hält die Zeile zusammen
            for value, width in zip(row, widths):
                pdf.cell(width, 7, pdf_text(str(value)), border=1, new_x=XPos.RIGHT, new_y=YPos.TOP)
            pdf.ln(7)

    def keep_together(height):
        if pdf.get_y() + height > pdf.h - pdf.b_margin:
            pdf.add_page()

    pdf.set_font("Helvetica", "B", 16)
    line("Fernverkehr: Fahrerregeln und Elektro-Lkw", 10)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(120, 120, 120)
    line(f"Erstellt: {time.strftime('%d.%m.%Y %H:%M')}  -  sebastianhanisch.net", 6)
    pdf.set_text_color(0, 0, 0)
    pdf.ln(3)

    heading("Einstellungen")
    pairs([
        ("Kunden (2 Lkw)", str(settings["customers"])), ("Typische Ladezeit", f"{settings['charge']} min"),
        ("Reichweite", f"{settings['range_km']} km"), ("Zeitfenster", str(settings["window"])),
        ("Seed (Instanz-Nr., tatsächlicher Seed)", f"{settings['seed']} ({res['seed']})"),
    ])
    pdf.ln(3)

    heading("Kosten und Kennzahlen der vier Zellen (Live-Instanz, ein einzelner Fall)")
    rows = []
    base = res["cells"][C.CELL_BASE]["total"]
    for c in C.CELLS:
        cell_data = res["cells"][c]
        if not cell_data["feasible"]:
            rows.append([C.CELL_LABELS[c], "keine zulässige Lösung", "-", "-", "-", "-"])
            continue
        m = cell_data["metrics"]
        extra = "-" if c == C.CELL_BASE or base is None else f"{_de(100 * (cell_data['total'] - base) / base, 1, True)} %"
        rows.append([C.CELL_LABELS[c], _eur(cell_data["total"]), extra, f"{m['breaks']}/{m['nights']}/{m['charges']}",
                     f"{m['km']:.0f}", _de(m["late_min"] / 60.0)])
    table(["Zelle", "Kosten", "Mehrkosten", "Pausen/Ruhen/Laden", "km", "Verspätung (h)"], [42, 40, 28, 38, 18, 24], rows)
    pdf.ln(3)

    if x is not None:
        heading("Wechselwirkung")
        pairs([
            ("Summe der Einzel-Mehrkosten", f"{_de(x['dF_pct'] + x['dE_pct'], 1, True)} % ({_eur(x['sum_eur'], True)})"),
            ("Mehrkosten beides, gemessen", f"{_de(x['dFE_pct'], 1, True)} % ({_eur(x['dFE_eur'], True)})"),
            ("Wechselwirkung I (beides minus Summe)", f"{_de(x['I_pct'], 1, True)} % ({_eur(x['I_eur'], True)})"),
        ])
        pdf.set_font("Helvetica", "", 9)
        pdf.multi_cell(0, 5, pdf_text(message), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_font("Helvetica", "", 10)
        pdf.ln(2)
    if series_rows:
        keep_together(30)
        heading("Wechselwirkung I in der Messreihe (Mittel +- Standardfehler)")
        table(["Messreihe", "I"], [130, 50], [[label, _band(stat)] for label, stat in series_rows])
        pdf.ln(3)

    keep_together(40)
    heading(f"Fahrplan: {C.CELL_LABELS[cell]}")
    cell_data = res["cells"][cell]
    if not cell_data["feasible"]:
        line("Keine zulässige Lösung für diese Zelle.")
    else:
        for t in cell_data["trucks"]:
            keep_together(30)
            pdf.set_font("Helvetica", "B", 10)
            line(f"Lkw {t['truck']}: " + " - ".join(S.place_name(node, res["n"]) for node in S.route_nodes(t["events"])), 6)
            pdf.set_font("Helvetica", "", 8)
            table(["Von", "Bis", "Ort", "Ereignis", "Einzelheit"], [30, 30, 48, 40, 42],
                  [[r["von"], r["bis"], r["ort"], r["ereignis"], r["einzelheit"]] for r in S.halteliste(t["events"], res["n"])])
            pdf.ln(3)

    keep_together(60)
    heading("Hinweise zum Modell")
    pdf.set_font("Helvetica", "", 9)
    for text in [
        "Stark stilisiert: Luftlinie, konstante Geschwindigkeit, ein Depot, alle Lkw starten gleichzeitig mit vollem Akku und "
        "frischem Fahrer. Lenk- und Ruhezeiten (EU 561/2006) sind vereinfacht: 45 min Pause nach 4,5 h, 11 h Ruhe nach 9 h Lenkzeit.",
        "Die Kostenparameter sind erfunden, nicht kalibriert (0,70 EUR/km, 32 EUR/h Fahrer, 15 EUR/h Fahrzeug, 100 EUR je Tagesruhe, "
        "40 EUR/h Verspätung): Prozentwerte sind Größenordnungen, keine Euro-Aussagen. Pausen zählen als bezahlte Fahrerzeit.",
        "Eine einzelne Instanz streut stark; die Aussage über die Wechselwirkung tragen die vorgerechneten Messreihen "
        "(60 gepaarte Instanzen je Größe, ein Urteil gilt nur ab 2 Standardfehlern).",
    ]:
        pdf.multi_cell(0, 5, pdf_text("- " + text), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    return bytes(pdf.output())
