"""Laden und Auswerten der vorgerechneten Messreihe (data/fv_results.json, erzeugt von tools/build_results.py aus den Läufen
von tools/sweep.py und tools/dump_sweep.py): Stufen, Statistiken, Urteil in drei Zuständen, Meldungszustand der Live-Instanz.

Die App rechnet die Messreihe NIE live (52 Minuten auf 16 Kernen); sie liest nur diese Datei."""
import functools
import json
import pathlib
from dataclasses import dataclass

import fv_constants as C

DATA_PATH = pathlib.Path(__file__).resolve().parent / "data" / "fv_results.json"

VERDICT_TEXT = {"neg": "billiger als die Summe (belastbar)", "pos": "teurer als die Summe (belastbar)",
                "none": "nicht von additiv zu unterscheiden"}
VERDICT_SHORT = {"neg": "billiger als die Summe", "pos": "teurer als die Summe", "none": "nicht von additiv unterscheidbar"}
STATE_TEXT = {"billiger": "billiger als die Summe", "additiv": "praktisch additiv", "teurer": "teurer als die Summe"}


@dataclass(frozen=True)
class Stat:
    """Mittel ± Standardfehler einer gepaarten Stichprobe (Prozent der regelfreien Kosten, wenn nichts anderes dabeisteht)."""
    n: int
    mean: float
    se: float
    median: float = 0.0
    q1: float = 0.0
    q3: float = 0.0
    neg_share: float = 0.0

    @classmethod
    def from_dict(cls, d):
        return cls(n=int(d.get("n", 0)), mean=float(d["mean"]), se=float(d["se"]), median=float(d.get("median", 0.0)),
                   q1=float(d.get("q1", 0.0)), q3=float(d.get("q3", 0.0)), neg_share=float(d.get("neg_share", 0.0)))

    def verdict(self, factor=C.SE_FACTOR):
        return verdict(self.mean, self.se, factor)


def verdict(mean, se, factor=C.SE_FACTOR):
    """Urteil in drei Zuständen: 'neg' (billiger als die Summe), 'pos' (teurer), 'none' - ein Vorzeichen nur, wenn der Betrag des
    Mittels mehr als `factor` Standardfehler beträgt."""
    if mean > factor * se:
        return "pos"
    if mean < -factor * se:
        return "neg"
    return "none"


@functools.lru_cache(maxsize=4)
def _load(path):
    return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))


def load_results(path=None):
    """Die vorgerechnete Messreihe (nicht verändern: das Ergebnis ist zwischengespeichert)."""
    return _load(str(path or DATA_PATH))


def series_names(data):
    return [k for k in data if not k.startswith("_")]


def stat(data, name, key="I"):
    """Stat einer Kennzahl einer Konfiguration: 'I', 'dF', 'dE', 'dFE', 'I_oper', 'I_eur'."""
    return Stat.from_dict(data[name][key])


def stat_fix(data, name, key="I"):
    return Stat.from_dict(data[name]["fix"][key])


def size_label(s):
    return f"{s['n']} Kunden, {s['K']} Lkw"


def size_short(s):
    return f"{s['n']}/{s['K']}"


def count_label(s):
    """'60 Instanzen' bzw. '28 von 40 Instanzen' (ausgeschlossene genannt)."""
    return f"{s['used']} Instanzen" if not s["excluded"] else f"{s['used']} von {s['instances']} Instanzen"


def number_label(s):
    """Größenangabe an jeder Zahl: '10 Kunden, 2 Lkw, 60 Instanzen'."""
    return f"{size_label(s)}, {count_label(s)}"


# ----------------------------------------------------------------------------------------------------------------
# Wechselwirkung einer Live-Instanz und Meldungszustand
# ----------------------------------------------------------------------------------------------------------------
def interaction_from_costs(costs):
    """Mehrkosten und Wechselwirkung aus den vier Zellen-Kosten {'---','F--','-E-','FE-'} (EUR).

    I = C(F+E) - C(F) - C(E) + C(ohne): negativ = die Kombination ist billiger als die Summe der Einzelkosten. Prozentwerte
    in % der regelfreien Kosten."""
    base, f, e, fe = (costs[c] for c in C.CELLS)
    out = dict(base=base, dF_eur=f - base, dE_eur=e - base, dFE_eur=fe - base, I_eur=fe - f - e + base)
    for k in ("dF", "dE", "dFE", "I"):
        out[k + "_pct"] = 100.0 * out[k + "_eur"] / base
    out["sum_eur"] = out["dF_eur"] + out["dE_eur"]
    return out


def message_state(I_pct, threshold=C.THRESHOLD_PCT):
    """Meldung der Hauptansicht in drei Zuständen mit Schwelle in % der regelfreien Kosten (AP 0: 2 %): 'billiger' (I unter
    -Schwelle), 'additiv' (|I| bis zur Schwelle), 'teurer' (I über +Schwelle)."""
    if I_pct < -threshold:
        return "billiger"
    if I_pct > threshold:
        return "teurer"
    return "additiv"


# ----------------------------------------------------------------------------------------------------------------
# Passende Messreihe zu einer Reglerstellung
# ----------------------------------------------------------------------------------------------------------------
def find_series(data, n, K, window, charge, range_km):
    """Name der Messreihe (bezahlte Pausen, Verspätungsstrafe 40 EUR/h, Fenster nach regelfreier Referenz) mit genau dieser Größe
    und diesen Einstellungen, sonst None. Bei mehreren (live10 und live10_reich400) die mit mehr Instanzen."""
    share, width = C.WINDOW_PARAMS[window]
    best = None
    for name in series_names(data):
        s = data[name]
        o = s["overrides"]
        if s["n"] != n or s["K"] != K or s["tw_ref"] != "plain" or set(o) - {"t_typ", "R"}:
            continue
        if abs(s["tw_share"] - share) > 1e-9 or (share > 0 and abs(s["tw_width_h"] - width) > 1e-9):
            continue
        if o.get("t_typ", 45.0) != charge or o.get("R", 400.0) != range_km:
            continue
        if best is None or s["used"] > data[best]["used"]:
            best = name
    return best


# ----------------------------------------------------------------------------------------------------------------
# Achsen des Kernabschnitts: Ladezeit, Reichweite, Zeitfenster, Fahrzeuge
# ----------------------------------------------------------------------------------------------------------------
# Je Achse Gruppen (feste Nebenbedingung) mit Stufen; je Stufe die Messreihen in beiden Größen (10 Kunden/2 Lkw und 18 Kunden/3 Lkw),
# wo gemessen. Fahrzeuge: jede Stufe hat ihre eigene Größe (12 Kunden/2 Lkw, 18/3, 24/4).
AXES = {
    "Ladezeit": [
        ("ohne Zeitfenster", [("20 min", ["live10_kein_fenster_lade20", "kein_fenster_lade20"]),
                              ("45 min", ["live10_kein_fenster", "kein_fenster"]),
                              ("90 min", ["live10_kein_fenster_lade90", "kein_fenster_lade90"])]),
        ("Zeitfenster mittel", [("20 min", ["lade20"]), ("45 min", ["live10", "basis"]), ("90 min", ["lade90"])]),
    ],
    "Reichweite": [
        ("Zeitfenster mittel", [("300 km", ["live10_reich300", "reich300"]), ("400 km", ["live10_reich400", "basis"]),
                                ("600 km", ["live10_reich600", "reich600"])]),
    ],
    "Zeitfenster": [
        ("Ladezeit 45 min", [("keine", ["live10_kein_fenster", "kein_fenster"]), ("locker", ["fenster_locker"]),
                             ("mittel", ["live10", "basis"]), ("eng", ["fenster_eng"])]),
    ],
    "Fahrzeuge": [
        ("Zeitfenster mittel", [("2 Lkw", ["fahrzeuge2"]), ("3 Lkw", ["basis"]), ("4 Lkw", ["fahrzeuge4"])]),
    ],
}
AXIS_NAMES = tuple(AXES)


def axis_rows(data, axis):
    """Zeilen der Achsen-Tabelle: Gruppe, Stufe, Größe, Instanzen, I (Stat), Urteil, Name der Messreihe."""
    rows = []
    for group, levels in AXES[axis]:
        for level, names in levels:
            for name in names:
                s = data[name]
                st = Stat.from_dict(s["I"])
                rows.append(dict(axis=axis, group=group, level=level, series=name, size=size_short(s), size_label=size_label(s),
                                 used=s["used"], instances=s["instances"], excluded=s["excluded"], count=count_label(s),
                                 stat=st, verdict=st.verdict(), states=s["states"]))
    return rows


SUM_SERIES = (("live10_kein_fenster", "ohne Zeitfenster"), ("live10", "Zeitfenster mittel"),
              ("kein_fenster", "ohne Zeitfenster"), ("basis", "Zeitfenster mittel"))


def sum_rows(data):
    """Zeilen für 'Summe gegen Kombination': Mehrkosten F, E, F+E (Mittel ± SE, Median, Quartile) je Größe und Fenster."""
    rows = []
    for name, window in SUM_SERIES:
        s = data[name]
        rows.append(dict(series=name, window=window, size=size_short(s), size_label=size_label(s), count=count_label(s),
                         dF=Stat.from_dict(s["dF"]), dE=Stat.from_dict(s["dE"]), dFE=Stat.from_dict(s["dFE"]),
                         I=Stat.from_dict(s["I"])))
    return rows


def excluded_series(data):
    """Messreihen mit ausgeschlossenen Instanzen (Reichweite 300 km): Name, Größe, ausgewertet, gemessen, Gründe."""
    out = []
    for name in series_names(data):
        s = data[name]
        if s["excluded"]:
            out.append(dict(series=name, size=size_label(s), used=s["used"], instances=s["instances"], excluded=s["excluded"],
                            reasons=s.get("excluded_reasons")))
    return out
