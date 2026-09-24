"""Eingefrorene Referenzwerte: der Nachweis, dass die mechanische Aufteilung von fern.py in fv_model / fv_evaluator / fv_search nichts
an der Logik geändert hat (tools/freeze_reference.py erzeugt tests/data/fv_reference.json mit dem UNVERÄNDERTEN Original).

Vier Fälle: drei Kleininstanzen (Kosten und Touren je Zelle, auch die Stafette-Zellen) und Instanz Seed 55 der Messreihe mit
10 Kunden, wie sie tools/sweep.py auf 16 Kernen gerechnet hat (raw_live10.jsonl). Gleiche Touren, Kosten auf 1e-6 EUR: die Suche
rechnet ausschließlich mit Gleitkommazahlen der Standardbibliothek und ist deterministisch (fester Seed)."""
import json
import pathlib

import pytest

from fv_evaluator import Ev
from fv_model import Cfg, combo_name
from fv_search import make_instance, solve_all

REF = json.loads((pathlib.Path(__file__).resolve().parent / "data" / "fv_reference.json").read_text(encoding="utf-8"))
COMBOS = {"---": (0, 0, 0), "F--": (1, 0, 0), "-E-": (0, 1, 0), "FE-": (1, 1, 0), "F-S": (1, 0, 1), "FES": (1, 1, 1)}


def _run(params, cells, restarts):
    cfg = Cfg(max_rl=4)
    inst = make_instance(params["seed"], params["n"], params["K"], cfg, tw_share=params["tw_share"],
                         tw_width_h=params["tw_width_h"], tw_ref="plain")
    combos = [COMBOS[c] for c in cells]
    out, pool = solve_all(inst, cfg, combos, params["seed"], restarts=restarts)
    return inst, cfg, out, pool


@pytest.mark.parametrize("name", ["klein_a", "klein_b", "klein_c"])
def test_small_instances_reproduce_the_frozen_original_results(name):
    ref = REF[name]
    inst, cfg, out, pool = _run(ref["params"], list(ref["cells"]), ref["restarts"])
    assert inst.tw_count == ref["tw_count"] and len(pool) == ref["pool"]
    for cell, expected in ref["cells"].items():
        routes, cost, ev = out[COMBOS[cell]]
        assert [list(r) for r in routes] == expected["routes"], (name, cell)
        assert cost == pytest.approx(expected["cost"], abs=1e-6), (name, cell)
        # auch je Tour: der Evaluator allein (ohne Suche) liefert denselben Wert wie im Original
        assert [ev.cost(tuple(r)) for r in routes] == pytest.approx(expected["route_costs"], abs=1e-6), (name, cell)


def test_instance_of_the_measurement_series_is_reproduced_bit_for_bit_in_the_app_code():
    """Seed 55 aus raw_live10.jsonl (Messreihe, 6 Neustarts): Touren und Kosten aller vier Zellen wie in der Messreihe."""
    ref = REF["live10_seed55_messreihe"]
    inst, cfg, out, _ = _run(ref["params"], list(ref["cells"]), 6)
    assert inst.tw_count == ref["tw_count"]
    for cell, expected in ref["cells"].items():
        routes, cost, ev = out[COMBOS[cell]]
        assert [list(r) for r in routes] == expected["routes"], cell
        assert cost == pytest.approx(expected["cost"], abs=1e-6), cell


def test_reference_costs_are_ordered_like_the_rules():
    """Plausibilitätsprüfung der eingefrorenen Werte selbst: mehr Regeln kosten nicht weniger (Toleranz für eps-Dominanz)."""
    for name in ("klein_a", "klein_b", "klein_c", "live10_seed55_messreihe"):
        c = {k: v["cost"] for k, v in REF[name]["cells"].items()}
        assert c["F--"] > c["---"] and c["-E-"] > c["---"]
        assert c["FE-"] >= max(c["F--"], c["-E-"]) - 3.0


def test_combo_name_and_cell_names_match_the_reference_keys():
    for cell, combo in COMBOS.items():
        assert combo_name(combo) == cell
    assert Ev(make_instance(0, 6, 2, Cfg(max_rl=4)), Cfg(max_rl=4)).cost(()) == 0.0


# ---------------------------------------------------------------------------------------------------
# Bausteine gegen das Original: Geometrie, Konstruktionsheuristiken, Lokalsuche, Zeitfenster
# ---------------------------------------------------------------------------------------------------
import random  # noqa: E402

from fv_model import make_geometry  # noqa: E402
from fv_search import ffd_routes, insertion_routes, local_search, savings_routes, solve  # noqa: E402

GEOMETRY = REF["_geometry"]
CONSTRUCTIONS = REF["_constructions"]
WINDOWS = REF["_windows"]


@pytest.mark.parametrize("key", list(GEOMETRY))
def test_geometry_equals_the_frozen_original(key):
    seed, n, K = (int(x) for x in key.split("_"))
    inst = make_geometry(seed, n, K)
    ref = GEOMETRY[key]
    assert inst.Q == ref["Q"] and inst.dem[:n + 1] == ref["dem"] and inst.svc[:n + 1] == ref["svc"]
    assert [list(p) for p in inst.xy[:n + 4]] == ref["xy"]
    assert [list(inst.xy[i]) for i in inst.stations] == ref["stations"] and [list(inst.xy[i]) for i in inst.relays] == ref["relays"]


@pytest.mark.parametrize("key", list(CONSTRUCTIONS))
def test_constructions_and_local_search_equal_the_frozen_original(key):
    seed, n, K = (int(x) for x in key.split("_"))
    inst = make_geometry(seed, n, K)
    cfg = Cfg(max_rl=4)
    ref = CONSTRUCTIONS[key]
    assert savings_routes(inst) == ref["savings"] and ffd_routes(inst) == ref["ffd"]
    assert insertion_routes(inst, random.Random(seed)) == ref["insertion"]
    for label, combo in (("base", (0, 0, 0)), ("F", (1, 0, 0)), ("E", (0, 1, 0))):
        routes, cost = local_search(Ev(inst, cfg, *combo), ffd_routes(inst), random.Random(seed))
        assert routes == ref["local_" + label]["routes"] and cost == pytest.approx(ref["local_" + label]["cost"], abs=1e-6), label
    routes, cost = solve(Ev(inst, cfg), seed)
    assert routes == ref["solve_base"]["routes"] and cost == pytest.approx(ref["solve_base"]["cost"], abs=1e-6)


@pytest.mark.parametrize("key", list(WINDOWS))
def test_time_windows_equal_the_frozen_original(key):
    seed, n, K, share, width, ref_kind = key.split("_")
    inst = make_instance(int(seed), int(n), int(K), Cfg(max_rl=4), tw_share=float(share), tw_width_h=float(width), tw_ref=ref_kind)
    ref = WINDOWS[key]
    assert inst.tw_count == ref["tw_count"] and inst.e[:int(n) + 1] == ref["e"]
    assert [None if x == float("inf") else x for x in inst.l[:int(n) + 1]] == ref["l"]
