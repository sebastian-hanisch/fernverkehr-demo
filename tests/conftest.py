"""Projektwurzel und tests/ auf den Importpfad, damit `pytest tests/` auch ohne `python -m` die fv_-Module und die
Test-Hilfsmodule (fv_checks, vrp_reference, live_cache) findet. Dazu die Fixtures für die App-Tests: die echte Live-Rechnung mit
verkleinerter Kundenzahl (AppTest rechnet nie mit 10 oder 12 Kunden)."""
import pathlib
import sys

import pytest

sys.dont_write_bytecode = True
TESTS = str(pathlib.Path(__file__).resolve().parent)
ROOT = str(pathlib.Path(__file__).resolve().parent.parent)
for p in (ROOT, TESTS):
    if p not in sys.path:
        sys.path.insert(0, p)


@pytest.fixture
def small_live(monkeypatch):
    """Ersetzt fv_live.solve_live durch eine Fassung, die dieselbe Rechnung immer mit 6 Kunden ausführt (Ergebnisse je Einstellung
    zwischengespeichert, echter Code, nur kleiner). Die App ruft die Rechnung über das Modul auf, deshalb greift das."""
    import fv_live
    import live_cache

    def solve_small(n, charge, range_km, window, seed_index):
        return live_cache.get_live(6, charge, range_km, window, seed_index)

    monkeypatch.setattr(fv_live, "solve_live", solve_small)
    return solve_small
