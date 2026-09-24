"""Abnahmekriterien der Presets (Detailplan plan_fernverkehr.html, Abschnitt 7): welche Geschichte erzählt jedes Beispielszenario,
und woran erkennt man, dass sie trägt?

Einzige Quelle für tests/test_stories.py (Schwellen einzeln kippen) und tests/test_preset_stories.py (Abnahme der echten Presets).
Alle Kriterien stehen auf den vorgerechneten Messreihen (data/fv_results.json), Vorzeichen-Kriterien IMMER zusammen mit der
Standardfehler-Bedingung (Betrag > 2 SE). Die gezeigte Live-Instanz (ein Seed) bleibt qualitativ, weil eine Instanz streut; sie liegt
bewusst ausserhalb der Stichprobe-Seeds. Kein Löser mit Wall-Clock-Grenze in den Kriterien.

`criteria(name, data)` liefert für jedes Preset eine Liste (erfüllt, Text). Die Schwellen stehen als Konstanten oben, damit ein
Test jede einzeln an ihre Grenze schieben kann."""
import fv_constants as C
from fv_results import Stat

# Standard: mit Zeitfenstern ist die Kombination teurer als die Summe, und die Verspätung erklärt den größten Teil
STANDARD_OPER_MAX_SHARE = 0.40        # Betriebskosten-I höchstens 40 % des Gesamt-I
# Ohne Zeitfenster: die Kombination ist billiger, aber kaum
NO_WINDOW_MAX_ABS_I = 2.0             # |I| unter 2 Prozentpunkten
NO_WINDOW_NEG_SHARE = (0.55, 0.75)    # Anteil der Instanzen mit I < 0 zwischen 55 und 75 %
# Lange Ladung: klar billiger als die Summe
LONG_CHARGE_MAX_I = -3.0              # I höchstens -3 Prozentpunkte
LONG_CHARGE_MIN_NEG_SHARE = 0.90      # in mindestens 90 % der Instanzen I < 0
# Knappe Reichweite: die Überadditivität wächst
TIGHT_RANGE_MIN_I = 10.0              # I mindestens 10 Prozentpunkte

FACTOR = C.SE_FACTOR


def _de(v, digits=1, sign=False):
    text = f"{v:+.{digits}f}" if sign else f"{v:.{digits}f}"
    return text.replace(".", ",")


def _band(s: Stat):
    return f"{_de(s.mean, 1, True)} ± {_de(s.se)} %"


def _clear(s: Stat, sign):
    """Vorzeichen-Bedingung mit Standardfehler: sign +1 (I > 0 und > 2 SE) oder -1 (I < 0 und < -2 SE)."""
    return s.mean > FACTOR * s.se if sign > 0 else s.mean < -FACTOR * s.se


def _get(data, name, key="I"):
    return Stat.from_dict(data[name][key])


def criteria(name, data):
    """Abnahmekriterien des Presets `name` auf den Messreihen `data`: Liste (erfüllt, Text)."""
    if name == "Standard":
        i18, i10 = _get(data, "basis"), _get(data, "live10")
        o18, o10 = _get(data, "basis", "I_oper"), _get(data, "live10", "I_oper")
        f18, e18 = _get(data, "basis", "dF"), _get(data, "basis", "dE")
        return [
            (_clear(i18, +1), f"I > 0 und > 2 Standardfehler (18 Kunden, 3 Lkw, {data['basis']['used']} Instanzen): {_band(i18)}"),
            (o18.mean <= STANDARD_OPER_MAX_SHARE * i18.mean and i18.mean > 0,
             f"Betriebskosten-I höchstens 40 % des Gesamt-I (18 Kunden): {_band(o18)} von {_band(i18)}"),
            (_clear(i10, +1), f"I > 0 und > 2 Standardfehler (10 Kunden, 2 Lkw, {data['live10']['used']} Instanzen): {_band(i10)}"),
            (o10.mean <= STANDARD_OPER_MAX_SHARE * i10.mean and i10.mean > 0,
             f"Betriebskosten-I höchstens 40 % des Gesamt-I (10 Kunden): {_band(o10)} von {_band(i10)}"),
            (f18.mean > e18.mean, f"Fahrerregeln teurer als Elektro (18 Kunden): {_de(f18.mean, 1, True)} % gegen {_de(e18.mean, 1, True)} %"),
        ]
    if name == "Ohne Zeitfenster":
        s = _get(data, "kein_fenster")
        lo, hi = NO_WINDOW_NEG_SHARE
        return [
            (_clear(s, -1), f"I < 0 und < -2 Standardfehler (18 Kunden, 3 Lkw): {_band(s)}"),
            (abs(s.mean) < NO_WINDOW_MAX_ABS_I, f"|I| unter 2 Prozentpunkten: {_de(abs(s.mean))}"),
            (lo <= s.neg_share <= hi, f"Anteil der Instanzen mit I < 0 zwischen 55 und 75 %: {_de(100 * s.neg_share, 0)} %"),
        ]
    if name == "Lange Ladung":
        s = _get(data, "kein_fenster_lade90")
        return [
            (s.mean <= LONG_CHARGE_MAX_I and _clear(s, -1), f"I höchstens -3 Prozentpunkte und < -2 Standardfehler (18 Kunden, 3 Lkw): {_band(s)}"),
            (s.neg_share >= LONG_CHARGE_MIN_NEG_SHARE, f"Anteil der Instanzen mit I < 0 mindestens 90 %: {_de(100 * s.neg_share, 0)} %"),
        ]
    if name == "Knappe Reichweite":
        s = _get(data, "reich300")
        d = data["reich300"]
        return [
            (s.mean >= TIGHT_RANGE_MIN_I and _clear(s, +1),
             f"I mindestens 10 Prozentpunkte und > 2 Standardfehler (18 Kunden, 3 Lkw, nur {d['used']} von {d['instances']} Lagen "
             f"auswertbar): {_band(s)}"),
        ]
    if name == "Kurze Ladung":
        s18, s10 = _get(data, "kein_fenster_lade20"), _get(data, "live10_kein_fenster_lade20")
        return [
            (_clear(s18, +1), f"I > 0 und > 2 Standardfehler (18 Kunden, 3 Lkw): {_band(s18)}"),
            (_clear(s10, +1), f"I > 0 und > 2 Standardfehler (10 Kunden, 2 Lkw): {_band(s10)}"),
        ]
    raise KeyError(name)
