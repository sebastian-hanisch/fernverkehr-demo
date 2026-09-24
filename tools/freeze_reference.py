"""Erzeugt tests/data/fv_reference.json: eingefrorene Referenzwerte (Kosten und Touren je Zelle) für drei Kleininstanzen,
gerechnet mit dem UNVERÄNDERTEN Quelltext der Messreihe (fern.py aus messreihe_fernverkehr).

Aufruf:  python tools/freeze_reference.py <Pfad/zu/fern.py> [<Pfad/zu/raw_live10.jsonl>]

Mit dem zweiten Argument kommt zusätzlich die Instanz Seed 55 der Messreihe (10 Kunden, 2 Lkw) hinein, so wie sie tools/sweep.py auf
16 Kernen gerechnet hat: der Nachweis, dass die fv_-Module bitgleich zur Messreihe rechnen (Kosten und Touren aus raw_live10.jsonl).

Die Datei fv_reference.json wurde einmal mit dem Original erzeugt, bevor fern.py in fv_model.py / fv_evaluator.py / fv_search.py
aufgeteilt wurde. tests/test_frozen_reference.py rechnet dieselben Fälle mit den fv_-Modulen und verlangt gleiche Touren und
Kosten: der Nachweis, dass die mechanische Aufteilung nichts an der Logik geändert hat."""
import importlib.util
import json
import pathlib
import random
import sys

sys.dont_write_bytecode = True

CASES = [
    # name, Instanzparameter, Zellen, restarts
    ("klein_a", dict(seed=0, n=6, K=2, tw_share=0.6, tw_width_h=8.0), "C4", 2),
    ("klein_b", dict(seed=3, n=7, K=2, tw_share=0.0, tw_width_h=8.0), "C4", 2),
    ("klein_c", dict(seed=5, n=6, K=2, tw_share=0.8, tw_width_h=4.0), "C6", 2),
]


def load_original(path):
    spec = importlib.util.spec_from_file_location("fern_original", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["fern_original"] = mod
    spec.loader.exec_module(mod)
    return mod


GEOMETRY_CASES = [(0, 6, 2), (1, 8, 2), (2, 10, 2), (3, 12, 2), (4, 12, 2), (5, 9, 2), (6, 18, 3), (7, 6, 3)]
WINDOW_CASES = [(0, 8, 2, 0.6, 8.0, "plain"), (1, 8, 2, 0.6, 8.0, "rules"), (2, 10, 2, 0.8, 4.0, "plain"), (3, 10, 2, 0.4, 12.0, "rules")]


def freeze_building_blocks(fern):
    """Geometrie, Konstruktionsheuristiken, Lokalsuche und Zeitfenster des Originals (ohne Solver-Pool)."""
    cfg = fern.Cfg(max_rl=4)
    geometry, constructions, windows = {}, {}, {}
    for seed, n, K in GEOMETRY_CASES:
        inst = fern.make_geometry(seed, n, K)
        key = f"{seed}_{n}_{K}"
        geometry[key] = dict(Q=inst.Q, dem=inst.dem[:n + 1], svc=inst.svc[:n + 1], xy=[list(p) for p in inst.xy[:n + 4]],
                             stations=[list(inst.xy[i]) for i in inst.stations], relays=[list(inst.xy[i]) for i in inst.relays])
        ev0, evF, evE = fern.Ev(inst, cfg), fern.Ev(inst, cfg, 1, 0, 0), fern.Ev(inst, cfg, 0, 1, 0)
        c = dict(savings=fern.savings_routes(inst), ffd=fern.ffd_routes(inst),
                 insertion=fern.insertion_routes(inst, random.Random(seed)))
        for label, ev in (("base", ev0), ("F", evF), ("E", evE)):
            routes, cost = fern.local_search(ev, fern.ffd_routes(inst), random.Random(seed))
            c["local_" + label] = dict(routes=routes, cost=cost)
        routes, cost = fern.solve(fern.Ev(inst, cfg), seed)
        c["solve_base"] = dict(routes=routes, cost=cost)
        constructions[key] = c
    for seed, n, K, share, width, ref in WINDOW_CASES:
        inst = fern.make_instance(seed, n, K, cfg, tw_share=share, tw_width_h=width, tw_ref=ref)
        windows[f"{seed}_{n}_{K}_{share}_{width}_{ref}"] = dict(e=inst.e[:n + 1], l=[None if x == float("inf") else x for x in inst.l[:n + 1]],
                                                                tw_count=inst.tw_count)
    return geometry, constructions, windows


def main():
    fern = load_original(sys.argv[1])
    combos_by = {"C4": [(0, 0, 0), (1, 0, 0), (0, 1, 0), (1, 1, 0)],
                 "C6": [(0, 0, 0), (1, 0, 0), (0, 1, 0), (1, 1, 0), (1, 0, 1), (1, 1, 1)]}
    out = {}
    cfg = fern.Cfg(max_rl=4)
    for name, kw, cset, restarts in CASES:
        seed = kw["seed"]
        inst = fern.make_instance(seed, kw["n"], kw["K"], cfg, tw_share=kw["tw_share"], tw_width_h=kw["tw_width_h"])
        res, pool = fern.solve_all(inst, cfg, combos_by[cset], seed, restarts=restarts)
        cells = {}
        for c in combos_by[cset]:
            routes, cost, ev = res[c]
            cells[fern.combo_name(c)] = dict(cost=cost, routes=[list(r) for r in routes],
                                            route_costs=[ev.cost(tuple(r)) for r in routes])
        out[name] = dict(params=kw, restarts=restarts, pool=len(pool), tw_count=inst.tw_count, cells=cells)
        print(name, {k: round(v["cost"], 2) for k, v in cells.items()}, flush=True)
    out["_geometry"], out["_constructions"], out["_windows"] = freeze_building_blocks(fern)
    if len(sys.argv) > 2:
        rows = [json.loads(line) for line in pathlib.Path(sys.argv[2]).read_text(encoding="utf-8").splitlines() if line.strip()]
        r = next(x for x in rows if x["seed"] == 55)
        out["live10_seed55_messreihe"] = dict(
            hinweis="aus messreihe_fernverkehr/raw_live10.jsonl (tools/sweep.py, 16 Kerne): 10 Kunden, 2 Lkw, Fenster 60 %/8 h, "
                    "Standardparameter, solve_all mit 6 Neustarts (Standard)",
            params=dict(seed=55, n=10, K=2, tw_share=0.6, tw_width_h=8.0), tw_count=r["tw_count"],
            cells={c: dict(cost=v["total"], routes=v["routes"]) for c, v in r["cells"].items()})
    target = pathlib.Path(__file__).resolve().parent.parent / "tests" / "data" / "fv_reference.json"
    target.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print("geschrieben:", target)


if __name__ == "__main__":
    main()
