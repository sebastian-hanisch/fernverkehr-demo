"""Das VOLLE Bau-Gate: alle Korrektheits-Checks des Fahrplan-Modells in der Fassung der Messreihe (check.py, ca. 3 Minuten,
3,9 Mio. simulierte Pläne für die Brute-Force-Referenz). Läuft einmal lokal vor dem Commit, nicht in der CI: dort laufen dieselben
Prüfungen verkleinert (tests/test_checks.py).

Aufruf (im Projektordner):  python tools/check_full.py"""
import pathlib
import sys
import time

sys.dont_write_bytecode = True
ROOT = pathlib.Path(__file__).resolve().parent.parent
for p in (ROOT, ROOT / "tests"):
    sys.path.insert(0, str(p))

import fv_checks as K  # noqa: E402


def main():
    t0 = time.time()
    K.check_alloff_equals_vrp_demo()
    K.check_validator_and_cost_recompute()
    K.check_switches_bite()
    K.check_unpaid_pause()
    K.check_brute_force()
    K.check_brute_force_chain2()
    K.check_dp_dominance_off()
    K.check_monotonicity_and_eps()
    K.check_search()
    K.check_adaptation()
    K.check_solve_all()
    print(f"\nalle Checks bestanden ({time.time() - t0:.0f} s)")


if __name__ == "__main__":
    main()
