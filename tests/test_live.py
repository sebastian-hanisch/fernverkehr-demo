"""Die Live-Instanz (fv_live.py): Seed-Auswahl (nur gültige Lagen), Aufbau der Instanz aus den Reglern, die vier Zellen, Fahrpläne
gegen den unabhängigen Validator, Kostenzerlegung, Determinismus, Randfälle (6 und 12 Kunden, Reichweite 300 und 600, alle
Zeitfenster-Stufen). Nur die Randfälle mit 12 Kunden rechnen länger (etwa 10 s); alles andere nutzt 6 bis 8 Kunden."""
import pytest

import fv_checks as K
import fv_constants as C
import fv_live as LV
from fv_evaluator import cost_from_events, plan_stats
from fv_model import Cfg, is_feasible, make_geometry
from live_cache import get_live


# ---------------------------------------------------------------------------------------------------
# Seed-Auswahl: der i-te GÜLTIGE Seed
# ---------------------------------------------------------------------------------------------------
def test_valid_seed_definition_every_customer_reachable_by_round_trip():
    n, R = 10, 300
    for seed in range(40):
        inst = make_geometry(seed, n, 2)
        ev = __import__("fv_evaluator").Ev(inst, LV.live_cfg(45, R), 0, 1, 0)
        expected = all(is_feasible(ev.cost((c,))) for c in range(1, n + 1))
        assert LV.seed_is_valid(seed, n, 2, R) == expected


def test_valid_seeds_are_exactly_the_reachable_ones_in_ascending_order():
    seeds = LV.valid_seeds(15, 10, 2, 300)
    assert seeds == sorted(seeds) and len(set(seeds)) == 15
    assert all(LV.seed_is_valid(s, 10, 2, 300) for s in seeds)
    skipped = [s for s in range(seeds[-1]) if s not in seeds]
    assert skipped and not any(LV.seed_is_valid(s, 10, 2, 300) for s in skipped)       # nichts Gültiges übersprungen


def test_seed_convention_matches_the_measurement_series():
    """Die Messreihe live10 (tools/sweep.py) beginnt mit den ersten gültigen Seeds bei Reichweite 300: 6, 7, 10, 11, 14, 16 ..."""
    assert LV.valid_seeds(6, 10, 2, 300) == [6, 7, 10, 11, 14, 16]
    assert LV.nth_valid_seed(0, 10, 2, 300) == 6 and LV.nth_valid_seed(5, 10, 2, 300) == 16


def test_larger_range_accepts_more_layouts_and_smaller_range_is_a_subset():
    s300, s400, s600 = (set(LV.valid_seeds(40, 8, 2, r)) for r in (300, 400, 600))
    assert LV.valid_seeds(40, 8, 2, 300)[-1] > LV.valid_seeds(40, 8, 2, 600)[-1]           # bei 300 km fällt vieles weg
    assert {s for s in s300 if s <= max(s400 & s300)} <= s400
    assert LV.nth_valid_seed(0, 8, 2, 300) >= LV.nth_valid_seed(0, 8, 2, 600)


def test_every_setting_gets_only_valid_instances():
    for n, R in ((6, 300), (8, 400), (12, 300), (12, 600)):
        for i in (0, 1, 7, 50, 100):
            assert LV.seed_is_valid(LV.nth_valid_seed(i, n, 2, R), n, 2, R), (n, R, i)


def test_seed_lookup_is_cached_and_stable():
    a = LV.nth_valid_seed(30, 9, 2, 400)
    assert LV.nth_valid_seed(30, 9, 2, 400) == a and LV.valid_seeds(31, 9, 2, 400)[-1] == a
    assert LV.valid_seeds(10, 9, 2, 400) == LV.valid_seeds(31, 9, 2, 400)[:10]


def test_the_highest_seed_of_the_slider_is_found_quickly():
    """0 bis 299: das Suchen des 300. gültigen Seeds bleibt unter einer Sekunde je Einstellung (Rechenzeit ohne Wall-Clock-Grenze:
    hier nur, dass es gelingt und gültig ist)."""
    seed = LV.nth_valid_seed(C.SEED_RANGE[1], 6, 2, 300)
    assert LV.seed_is_valid(seed, 6, 2, 300) and seed >= C.SEED_RANGE[1]


# ---------------------------------------------------------------------------------------------------
# Instanz aus den Reglern
# ---------------------------------------------------------------------------------------------------
def test_live_cfg_takes_charge_time_and_range():
    cfg = LV.live_cfg(90, 600)
    assert (cfg.t_typ, cfg.R) == (90.0, 600.0) and cfg.max_rl == 4
    assert Cfg(max_rl=4).c_km == cfg.c_km and cfg.pause_paid is True


@pytest.mark.parametrize("window", C.WINDOW_OPTIONS)
def test_build_instance_applies_the_window_level(window):
    inst, cfg, seed = LV.build_instance(8, 45, 400, window, 3)
    share, width = C.WINDOW_PARAMS[window]
    assert inst.n == 8 and inst.K == 2 and seed == LV.nth_valid_seed(3, 8, 2, 400)
    if share == 0.0:
        assert inst.tw_count == 0
    else:
        assert 0 < inst.tw_count <= 8
        assert all(abs(inst.l[c] - inst.e[c] - width * 60.0) < 1e-9 for c in range(1, 9) if inst.l[c] < 1e17)


def test_window_levels_are_ordered_by_tightness():
    counts = [LV.build_instance(12, 45, 400, w, 5)[0].tw_count for w in C.WINDOW_OPTIONS]
    assert counts[0] == 0 and counts[1] <= counts[2] <= counts[3] and counts[3] > 0


# ---------------------------------------------------------------------------------------------------
# Das Ergebnis: vier Zellen, Fahrpläne, Kostenzerlegung
# ---------------------------------------------------------------------------------------------------
@pytest.fixture(scope="module")
def res():
    return get_live()


def test_result_has_the_instance_and_four_cells(res):
    assert res["n"] == 6 and res["K"] == 2 and res["seed"] == LV.nth_valid_seed(250, 6, 2, 400) and res["seed_index"] == 250
    assert (res["charge"], res["range_km"], res["window"]) == (45, 400, "mittel")
    assert set(res["cells"]) == set(C.CELLS)
    assert len(res["xy"]) == 1 + 6 + 12 + 4 and res["stations"] == list(range(7, 19)) and len(res["dem"]) == 7
    assert res["late"][0] is None and res["capacity"] > 0 and res["seconds"] >= 0.0


def test_every_cell_is_a_valid_partition_with_its_own_cost(res):
    for name, cell in res["cells"].items():
        assert cell["feasible"] and cell["total"] > 0
        assert sorted(c for r in cell["routes"] for c in r) == list(range(1, 7)), name
        assert len(cell["routes"]) == res["K"] and len(cell["trucks"]) == sum(1 for r in cell["routes"] if r)
        assert cell["fix_total"] is not None and cell["total"] <= cell["fix_total"] + 1e-6, name    # neu geplant nie schlechter


def test_schedules_pass_the_independent_validator_and_the_cost_recomputation(res):
    cfg = LV.live_cfg(res["charge"], res["range_km"])
    inst, _, _ = LV.build_instance(res["n"], res["charge"], res["range_km"], res["window"], res["seed_index"])
    for name, cell in res["cells"].items():
        F, E, _ = C.CELL_COMBOS[name]
        total = 0.0
        for t in cell["trucks"]:
            K.validate_events(inst, cfg, tuple(t["route"]), t["events"], F, E)
            total += cost_from_events(t["events"], cfg, inst)
        assert total == pytest.approx(cell["total"], abs=1e-6), name


def test_cost_components_close_and_metrics_match_the_events(res):
    cfg = LV.live_cfg(res["charge"], res["range_km"])
    for name, cell in res["cells"].items():
        comps = cell["comps"]
        assert set(comps) == set(C.COST_KEYS)
        assert sum(comps.values()) == pytest.approx(cell["total"], abs=1e-6), name        # die Zerlegung schließt
        assert comps["km"] == pytest.approx(cfg.c_km * cell["metrics"]["km"])
        stats = [plan_stats(t["events"], cfg) for t in cell["trucks"]]
        assert cell["metrics"]["breaks"] == sum(s["breaks"] for s in stats)
        assert cell["metrics"]["nights"] == sum(s["nights"] for s in stats)
        assert cell["metrics"]["charges"] == sum(s["charges"] for s in stats)
        assert comps["naechte"] == pytest.approx(cfg.c_night * cell["metrics"]["nights"])


def test_switches_bite_in_every_cell(res):
    """Schalter-greift-Test je Zelle auf der Live-Instanz: F erzeugt Pausen und Tagesruhen, E Ladestopps, ohne Regeln gibt es nichts
    davon, F+E ist nicht billiger als F oder E allein (Toleranz der eps-Dominanz)."""
    m = {c: res["cells"][c]["metrics"] for c in C.CELLS}
    base, f, e, fe = (m[c] for c in C.CELLS)
    assert (base["breaks"], base["nights"], base["charges"]) == (0, 0, 0) and base["late_min"] == 0.0     # Fenster um die Referenz
    assert f["breaks"] > 0 and f["nights"] >= 1 and f["charges"] == 0
    assert e["charges"] > 0 and e["breaks"] == 0 and e["nights"] == 0
    assert fe["breaks"] > 0 and fe["charges"] > 0
    t = {c: res["cells"][c]["total"] for c in C.CELLS}
    assert t[C.CELL_F] > t[C.CELL_BASE] and t[C.CELL_E] > t[C.CELL_BASE]
    assert t[C.CELL_FE] >= max(t[C.CELL_F], t[C.CELL_E]) - 3.0


def test_result_is_deterministic():
    a = LV.solve_live(6, 45, 400, "eng", 12)
    b = LV.solve_live(6, 45, 400, "eng", 12)
    for c in C.CELLS:
        assert a["cells"][c]["routes"] == b["cells"][c]["routes"] and a["cells"][c]["total"] == b["cells"][c]["total"]
        assert a["cells"][c]["trucks"] == b["cells"][c]["trucks"]


def test_cell_metrics_agree_with_the_sweep_tool():
    """fv_live.cell_metrics rechnet dieselben Formeln wie tools/sweep.py (Messreihe) - sonst wären Live-Instanz und Messreihe
    verschiedene Größen."""
    import pathlib
    import sys
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "tools"))
    import sweep
    from fv_search import make_instance, solve_all
    cfg = Cfg(max_rl=4)
    inst = make_instance(7, 7, 2, cfg, tw_share=0.6, tw_width_h=8.0)
    out, _ = solve_all(inst, cfg, [(0, 0, 0), (1, 0, 0), (0, 1, 0), (1, 1, 0)], 7, restarts=2)
    base_routes = out[(0, 0, 0)][0]
    for combo, (routes, _, ev) in out.items():
        mine = LV.cell_metrics(ev, cfg, routes)
        theirs = sweep.cell_metrics(ev, cfg, routes, base_routes)
        for key, value in mine.items():
            assert theirs[key] == pytest.approx(value), (combo, key)
        assert LV.cost_components(mine, cfg)["km"] == pytest.approx(cfg.c_km * theirs["km"])


# ---------------------------------------------------------------------------------------------------
# Randfälle
# ---------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("window", C.WINDOW_OPTIONS)
def test_all_window_levels_solve_with_six_customers(window):
    r = get_live(6, 45, 400, window, 20)
    assert all(c["feasible"] for c in r["cells"].values())
    late = {c: r["cells"][c]["metrics"]["late_min"] for c in C.CELLS}
    assert late[C.CELL_BASE] == 0.0
    if window == "keine":
        assert all(v == 0.0 for v in late.values())                         # ohne Fenster keine Verspätung (Konstruktion)
        assert all(r["cells"][c]["comps"]["verspaetung"] == 0.0 for c in C.CELLS)


def test_late_cost_appears_only_with_windows_across_instances():
    """Zweig-Test gegen die Null-Spalte: mit Zeitfenstern wird in F, E oder F+E irgendwo Verspätung gebucht."""
    late = [get_live(6, 45, 400, "eng", i)["cells"][c]["comps"]["verspaetung"] for i in (3, 9, 15, 21) for c in (C.CELL_F, C.CELL_FE)]
    assert any(v > 0.0 for v in late)


def test_branches_of_the_overlap_are_reached_across_instances():
    """Kein Ergebnisfeld ist über alle Instanzen exakt 0: Pausen am Lader, freie Lademinuten, Tagesruhen am Lader, Nächte, Kilometer."""
    seen = dict(breaks_at_charger=0, free_charge_min=0.0, rests_at_charger=0, nights=0, km=0.0)
    for i in (2, 8, 14, 20, 26):
        m = get_live(6, 45, 400, "mittel", i)["cells"][C.CELL_FE]["metrics"]
        for k in seen:
            seen[k] += m[k]
    assert all(v > 0 for v in seen.values()), seen


def test_waiting_for_a_window_to_open_occurs_with_rules():
    """Warten am Kunden (Zeitfenster noch zu) gibt es nur mit Regeln und nur auf einigen Instanzen; die regelfreie Zelle wartet
    nie (Fenster um die regelfreie Referenz, Konstruktion)."""
    waits = {c: sum(get_live(6, 45, 400, "mittel", i)["cells"][c]["metrics"]["wait_min"] for i in (0, 1, 3, 6)) for c in C.CELLS}
    assert waits[C.CELL_BASE] == 0.0 and waits[C.CELL_F] > 0 and waits[C.CELL_FE] > 0


@pytest.mark.parametrize("range_km", C.RANGE_OPTIONS)
def test_reach_levels_change_the_electric_cell(range_km):
    r = get_live(6, 45, range_km, "keine", 4)
    e = r["cells"][C.CELL_E]
    assert e["feasible"] and e["metrics"]["charges"] > 0
    assert e["metrics"]["charge_km"] > 0


def test_smaller_range_needs_more_charging_across_instances():
    charges = {R: sum(get_live(6, 45, R, "keine", i)["cells"][C.CELL_E]["metrics"]["charges"] for i in (4, 12, 16, 22)) for R in (300, 600)}
    assert charges[300] > charges[600]


def test_longer_charging_time_makes_the_electric_cell_more_expensive():
    cost = {t: sum(get_live(6, t, 400, "keine", i)["cells"][C.CELL_E]["total"] for i in (4, 10, 16)) for t in (20, 90)}
    assert cost[90] > cost[20]


def test_the_minimum_and_maximum_customer_counts_solve():
    six = get_live(6, 45, 400, "mittel", 5)
    assert six["n"] == 6 and all(c["feasible"] for c in six["cells"].values())
    twelve = LV.solve_live(12, 45, 600, "keine", 5)                         # der größte Fall (einige Sekunden)
    assert twelve["n"] == 12 and len(twelve["xy"]) == 1 + 12 + 12 + 4
    assert all(c["feasible"] for c in twelve["cells"].values())
    assert sorted(c for r in twelve["cells"][C.CELL_FE]["routes"] for c in r) == list(range(1, 13))


def test_a_real_layout_without_a_feasible_electric_solution_is_reported_not_crashed():
    """Bei 300 km Reichweite gibt es Lagen, in denen jeder Kunde einzeln erreichbar ist, die Suche aber keine zulässige Aufteilung auf
    2 Lkw findet (hier Instanz Nr. 10, Seed 18, 6 Kunden; die Messreihe schließt solche Lagen aus). Die Live-Rechnung meldet das
    ehrlich, ohne Absturz und ohne Fahrpläne in den betroffenen Zellen."""
    r = get_live(6, 45, 300, "keine", 10)
    assert r["seed"] == 18
    assert [c for c in C.CELLS if not r["cells"][c]["feasible"]] == [C.CELL_E, C.CELL_FE]
    for c in (C.CELL_E, C.CELL_FE):
        cell = r["cells"][c]
        assert cell["total"] is None and cell["trucks"] == [] and cell["metrics"] is None and cell["fix_total"] is None
    assert r["cells"][C.CELL_BASE]["feasible"] and r["cells"][C.CELL_F]["feasible"]


def test_an_infeasible_electric_cell_is_reported_honestly_not_crashed(monkeypatch):
    """Findet die Suche in einer Zelle keine zulässige Lösung, liefert solve_live feasible=False ohne Fahrpläne (kein Absturz)."""
    import fv_search
    real = fv_search.solve_all

    def broken(inst, cfg, combos, seed, restarts=6, **kw):
        out, pool = real(inst, cfg, combos, seed, restarts=restarts, **kw)
        e = out[(0, 1, 0)]
        out[(0, 1, 0)] = ([[c] for c in range(1, inst.n + 1)][:inst.K], 1e6 + 5.0, e[2])
        return out, pool

    monkeypatch.setattr(LV, "solve_all", broken)
    r = LV.solve_live(6, 45, 400, "keine", 3)
    e = r["cells"][C.CELL_E]
    assert e["feasible"] is False and e["total"] is None and e["trucks"] == [] and e["metrics"] is None and e["comps"] is None
    assert r["cells"][C.CELL_BASE]["feasible"] and r["cells"][C.CELL_F]["feasible"]


# ---------------------------------------------------------------------------------------------------
# Ergänzungen aus dem Fehler-Einbau-Test (tools/mutation_check.py)
# ---------------------------------------------------------------------------------------------------
def test_the_seed_lookup_scans_only_as_far_as_needed_and_keeps_ranges_apart():
    """Je (Kunden, Lkw, Reichweite) wird nur so weit gesucht wie nötig; verschiedene Reichweiten haben getrennte Listen."""
    LV._VALID.pop((7, 2, 350), None)
    seeds = LV.valid_seeds(5, 7, 2, 350)
    entry = LV._VALID[(7, 2, 350)]
    assert len(seeds) == 5 and len(entry[0]) == 5 and entry[1] == seeds[-1] + 1                 # genau 5 gefunden, danach nicht weitergesucht
    assert LV.valid_seeds(3, 7, 2, 350) == seeds[:3] and len(entry[0]) == 5
    assert (7, 2, 300) not in LV._VALID or LV._VALID[(7, 2, 300)] is not entry


def test_solve_live_uses_the_instance_seed_and_the_configured_restarts():
    """Live-Ergebnis == direkte Rechnung mit dem Seed der Instanz und C.LIVE_RESTARTS Neustarts (gleiche Suche wie die Messreihe).
    Gewählt ist eine Instanz (7 Kunden, Nr. 7), auf der ein anderer Such-Seed ein anderes Ergebnis liefert: nur so sieht der Test
    einen falschen Seed."""
    from fv_search import solve_all
    inst, cfg, seed = LV.build_instance(7, 45, 400, "mittel", 7)
    combos = [C.CELL_COMBOS[c] for c in C.CELLS]
    direct, _ = solve_all(inst, cfg, combos, seed, restarts=C.LIVE_RESTARTS)
    other, _ = solve_all(inst, cfg, combos, seed + 1, restarts=C.LIVE_RESTARTS)
    assert any(other[c][0] != direct[c][0] or other[c][1] != direct[c][1] for c in combos)          # der Test ist empfindlich
    res = LV.solve_live(7, 45, 400, "mittel", 7)
    assert res["seed"] == seed and C.LIVE_RESTARTS == 3
    for c in C.CELLS:
        assert res["cells"][c]["routes"] == [list(r) for r in direct[C.CELL_COMBOS[c]][0]]
        assert res["cells"][c]["total"] == direct[C.CELL_COMBOS[c]][1]


def test_fixed_totals_are_the_rule_free_routes_evaluated_under_the_cell_rules():
    from fv_evaluator import Ev
    from fv_search import total_cost
    res = get_live(6, 45, 400, "mittel", 20)
    inst, cfg, _ = LV.build_instance(6, 45, 400, "mittel", 20)
    base_routes = [tuple(r) for r in res["cells"][C.CELL_BASE]["routes"]]
    for c in C.CELLS:
        expected = total_cost(Ev(inst, cfg, *C.CELL_COMBOS[c]), base_routes)
        assert res["cells"][c]["fix_total"] == pytest.approx(expected, abs=1e-6), c
    assert res["cells"][C.CELL_BASE]["fix_total"] == res["cells"][C.CELL_BASE]["total"]
    assert res["cells"][C.CELL_F]["fix_total"] > res["cells"][C.CELL_F]["total"] - 1e-6


def test_cell_metrics_marks_an_undriveable_route_as_infeasible():
    """Eine Tour, die mit der Reichweite nicht fahrbar ist, macht die Zelle unzulässig (total None); die übrigen Touren zählen weiter."""
    from fv_evaluator import Ev
    inst = make_geometry(18, 6, 2)                                  # Lage mit Kunden, die einzeln erreichbar, aber nicht alle zusammen sind
    cfg = LV.live_cfg(45, 300)
    ev = Ev(inst, cfg, 0, 1, 0)
    ok = [c for c in range(1, 7) if is_feasible(ev.cost((c,)))]
    m = LV.cell_metrics(ev, cfg, [tuple(ok[:1]), tuple(range(1, 7))])
    assert m["feasible"] is False and m["total"] is None and m["oper"] is None and m["used"] == 1
    m2 = LV.cell_metrics(ev, cfg, [tuple(ok[:1]), ()])
    assert m2["feasible"] is True and m2["total"] == pytest.approx(ev.cost(tuple(ok[:1]))) and m2["used"] == 1


def test_cell_metrics_sums_over_all_routes_not_only_the_last():
    from fv_evaluator import Ev, plan_stats
    inst, cfg, _ = LV.build_instance(6, 45, 400, "mittel", 20)
    ev = Ev(inst, cfg, 1, 1, 0)
    routes = [(1, 2, 3), (4, 5, 6)]
    m = LV.cell_metrics(ev, cfg, routes)
    parts = [plan_stats(ev.plan(r)["events"], cfg) for r in routes]
    assert m["km"] == pytest.approx(sum(p["km"] for p in parts)) and m["span_min"] == pytest.approx(sum(p["t_end"] for p in parts))
    assert m["breaks"] == sum(p["breaks"] for p in parts) and m["used"] == 2
    assert m["driver_h"] == pytest.approx((m["span_min"] - m["rest_min"]) / 60.0)
    assert m["oper"] == pytest.approx(m["total"] - m["late_cost"])
    from dataclasses import replace
    unpaid_cfg = replace(cfg, pause_paid=False)
    unpaid = LV.cell_metrics(Ev(inst, unpaid_cfg, 1, 1, 0), unpaid_cfg, routes)
    assert unpaid["pause_min"] > 0 and unpaid["driver_h"] == pytest.approx(
        unpaid["span_min"] / 60.0 - unpaid["rest_min"] / 60.0 - unpaid["pause_min"] / 60.0)         # unbezahlte Pausen zählen nicht als Fahrerzeit


def test_late_windows_of_the_result_are_none_without_a_window_and_numbers_with_one():
    res = get_live()
    assert res["late"][0] is None and any(x is not None for x in res["late"][1:]) and any(x is None for x in res["late"][1:])
    assert all(res["early"][c] <= res["late"][c] for c in range(1, 7) if res["late"][c] is not None)
    assert len(res["late"]) == len(res["early"]) == len(res["svc"]) == len(res["dem"]) == 7
