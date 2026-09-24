"""Hilfe für die Tests: echte Live-Ergebnisse (fv_live.solve_live) je Einstellung einmal pro Testlauf rechnen. Die Live-Rechnung ist
die teuerste Stelle der App (6 Kunden etwa 0,5 s, 10 Kunden etwa 5 s); Tests dürfen sie teilen, aber nie verändern."""
import copy

import fv_live

_CACHE = {}


def get_live(n=6, charge=45, range_km=400, window="mittel", seed_index=250):
    key = (n, charge, range_km, window, seed_index)
    if key not in _CACHE:
        _CACHE[key] = _REAL(n, charge, range_km, window, seed_index)
    return _CACHE[key]


def fresh_copy(res):
    """Tiefe Kopie, wenn ein Test das Ergebnis verändern will (künstliche Kosten, unzulässige Zellen)."""
    return copy.deepcopy(res)


_REAL = fv_live.solve_live                     # das Original, bevor ein Test es ersetzt
