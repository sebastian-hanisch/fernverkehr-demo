"""Sucht für jedes Preset einen Anzeige-Seed: die gezeigte Live-Instanz (10 Kunden, 2 Lkw) soll die Geschichte des Presets ehrlich
erzählen, ohne ein Ausreißer zu sein. Kriterium: alle vier Zellen zulässig, Meldungszustand wie in der Messreihe am häufigsten und
die Wechselwirkung I möglichst nah am Mittel der passenden Messreihe (data/fv_results.json, Größe 10 Kunden, 2 Lkw).

Aufruf (im Projektordner):  python tools/tune_presets.py [erster_Seed] [letzter_Seed]      (Standard 200 bis 239)
Rechnet je Preset und Seed die Live-Instanz (etwa 5 s) auf mehreren Prozessen und druckt die besten Kandidaten. Die Seeds sind
Nummern der Instanz (der i-te gültige Seed), sie liegen bewusst ausserhalb der Stichprobe der Messreihe."""
import os
import pathlib
import sys
import time
from multiprocessing import Pool

sys.dont_write_bytecode = True
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import fv_constants as C  # noqa: E402
import fv_live as LV  # noqa: E402
import fv_results as R  # noqa: E402

DATA = R.load_results()
# Zielzustand je Preset (Geschichte) und die passende Messreihe in Live-Größe
TARGET = {"Standard": "teurer", "Ohne Zeitfenster": "additiv", "Lange Ladung": "billiger", "Kurze Ladung": "additiv",
          "Knappe Reichweite": "teurer"}


def run(args):
    name, seed = args
    p = C.PRESETS[name]
    res = LV.solve_live(p["customers"], p["charge"], p["range_km"], p["window"], seed)
    if not all(res["cells"][c]["feasible"] for c in C.CELLS):
        return name, seed, None
    x = R.interaction_from_costs({c: res["cells"][c]["total"] for c in C.CELLS})
    return name, seed, x["I_pct"]


def main():
    lo = int(sys.argv[1]) if len(sys.argv) > 1 else 200
    hi = int(sys.argv[2]) if len(sys.argv) > 2 else 239
    tasks = [(name, s) for name in C.PRESETS for s in range(lo, hi + 1)]
    t0 = time.time()
    with Pool(processes=max(1, (os.cpu_count() or 4) - 2)) as pool:
        rows = pool.map(run, tasks, chunksize=1)
    for name, p in C.PRESETS.items():
        s = R.find_series(DATA, 10, 2, p["window"], p["charge"], p["range_km"])
        mean = DATA[s]["I"]["mean"]
        cand = [(abs(i - mean), seed, i) for n, seed, i in rows if n == name and i is not None and R.message_state(i) == TARGET[name]]
        cand.sort()
        print(f"{name}: Messreihe {s} I = {mean:+.1f} %, Ziel '{TARGET[name]}'; beste Seeds (Abstand, Seed, I): "
              + ", ".join(f"({d:.2f}, {seed}, {i:+.2f})" for d, seed, i in cand[:5]))
    print(f"{time.time() - t0:.0f} s")


if __name__ == "__main__":
    main()
