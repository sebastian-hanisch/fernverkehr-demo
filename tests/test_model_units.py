"""Bausteine des Fahrplan-Modells einzeln: Parameter, Geometrie, Zeitfenster-Kalibrierung, Evaluator an Handrechnungen,
Kennzahlen aus Ereignissen, Konstruktionsheuristiken und Lokalsuche. Ergänzt tests/test_checks.py (Korrektheit gegen Brute-Force
und vrp_demo) und tests/test_frozen_reference.py (Bitgleichheit zum Original)."""
import math
import random
from dataclasses import replace

import pytest

from fv_evaluator import Ev, cost_from_events, plan_stats
from fv_model import BIG, COMBOS, INF, Cfg, Inst, _route_len, combo_name, is_feasible, make_geometry
from fv_search import (_fit_K, _norm, ffd_routes, insertion_routes, local_search, make_instance, perturb, reference_windows,
                       savings_routes, solve, solve_all, total_cost)

CFG = Cfg(max_rl=4)
EXACT = dict(eps_g=0.0, eps_t=0.0, eps_c=0.0, eps_b=0.0)


def _partition_ok(inst, routes):
    return sorted(c for r in routes for c in r) == list(range(1, inst.n + 1))


def _capacity_ok(inst, routes):
    return all(sum(inst.dem[c] for c in r) <= inst.Q + 1e-9 for r in routes)


# ---------------------------------------------------------------------------------------------------
# Parameter
# ---------------------------------------------------------------------------------------------------
def test_default_parameters_are_the_documented_ones():
    c = Cfg()
    assert (c.speed, c.c_km, c.c_drv, c.c_veh, c.c_night, c.c_late) == (75.0, 0.70, 32.0, 15.0, 100.0, 40.0)
    assert (c.brk, c.blk, c.day, c.rest) == (45.0, 270.0, 540.0, 660.0)
    assert (c.R, c.t_typ, c.typ_share) == (400.0, 45.0, 0.6)
    assert c.pause_paid is True and c.vol_c == 0.0 and c.vol_d == 0.0
    assert (c.eps_g, c.eps_t, c.eps_c, c.eps_b) == (0.5, 2.0, 2.0, 3.0)


def test_cfg_is_frozen():
    with pytest.raises(Exception):
        Cfg().R = 1.0


def test_feasibility_threshold_and_combo_names():
    assert is_feasible(0.0) and is_feasible(BIG / 2 - 1) and not is_feasible(BIG / 2) and not is_feasible(BIG + 5)
    assert combo_name((0, 0, 0)) == "---" and combo_name((1, 0, 0)) == "F--" and combo_name((0, 1, 0)) == "-E-"
    assert combo_name((1, 1, 0)) == "FE-" and combo_name((1, 1, 1)) == "FES" and combo_name((0, 0, 1)) == "--S"
    assert len(COMBOS) == 8 and len(set(COMBOS)) == 8


# ---------------------------------------------------------------------------------------------------
# Geometrie und Instanz
# ---------------------------------------------------------------------------------------------------
def test_geometry_layout_and_ranges():
    inst = make_geometry(3, n=10, K=2)
    assert (inst.n, inst.K, inst.ns, inst.nr) == (10, 2, 12, 4)
    assert len(inst.xy) == 1 + 10 + 12 + 4 == len(inst.D) == len(inst.dem) == len(inst.svc) == len(inst.e) == len(inst.l)
    assert inst.xy[0] == (400.0, 400.0)                                    # Depot in der Mitte von 800 x 800 km
    assert all(0.0 <= x <= 800.0 and 0.0 <= y <= 800.0 for x, y in inst.xy)
    assert inst.stations == list(range(11, 23)) and inst.relays == list(range(23, 27))
    assert all(1 <= inst.dem[c] <= 10 for c in range(1, 11)) and all(inst.dem[c] == 0 for c in [0] + inst.stations)
    assert all(30.0 <= inst.svc[c] <= 60.0 for c in range(1, 11)) and inst.svc[0] == 0.0
    assert all(inst.e[c] == 0.0 and inst.l[c] == INF for c in range(len(inst.xy)))     # ohne Zeitfenster
    assert inst.tw_count == 0


def test_geometry_capacity_gives_80_percent_fill_and_a_feasible_packing():
    for seed in range(8):
        inst = make_geometry(seed, n=12, K=2)
        total = sum(inst.dem)
        assert inst.Q >= max(inst.dem) and total <= 0.8 * inst.K * inst.Q + inst.K * 10       # etwa 80 % Füllgrad
        assert _partition_ok(inst, ffd_routes(inst)) and _capacity_ok(inst, ffd_routes(inst))


def test_distance_matrix_is_euclidean_symmetric_and_has_zero_diagonal():
    inst = make_geometry(1, n=7, K=2)
    m = len(inst.xy)
    for i in range(m):
        assert inst.D[i][i] == 0.0
        for j in range(m):
            assert inst.D[i][j] == inst.D[j][i]
            assert inst.D[i][j] == pytest.approx(math.hypot(inst.xy[i][0] - inst.xy[j][0], inst.xy[i][1] - inst.xy[j][1]))


def test_stations_form_a_jittered_grid_of_4_by_3_cells():
    inst = make_geometry(5, n=6, K=2)
    cells = {(int(inst.xy[s][0] // 200), int(inst.xy[s][1] // (800 / 3))) for s in inst.stations}
    assert len(inst.stations) == 12 and len(cells) >= 9                   # jede Säule liegt nahe ihrer Rasterzelle


def test_geometry_is_deterministic_and_depends_on_seed_and_customer_count():
    a, b, c, d = make_geometry(4, 9, 2), make_geometry(4, 9, 2), make_geometry(5, 9, 2), make_geometry(4, 10, 2)
    assert a.xy == b.xy and a.dem == b.dem and a.svc == b.svc and a.Q == b.Q
    assert a.xy != c.xy and a.xy[:10] != d.xy[:10]


def test_route_length_helper():
    inst = make_geometry(0, 6, 2)
    assert _route_len(inst.D, []) == 0.0
    assert _route_len(inst.D, [2]) == pytest.approx(2 * inst.D[0][2])
    assert _route_len(inst.D, [1, 2]) == pytest.approx(inst.D[0][1] + inst.D[1][2] + inst.D[2][0])


# ---------------------------------------------------------------------------------------------------
# Zeitfenster-Kalibrierung
# ---------------------------------------------------------------------------------------------------
def test_windows_follow_share_and_width():
    inst = make_instance(2, 12, 2, CFG, tw_share=0.6, tw_width_h=8.0)
    with_tw = [c for c in range(1, 13) if inst.l[c] < INF]
    assert len(with_tw) == inst.tw_count > 0
    assert all(inst.l[c] - inst.e[c] == pytest.approx(480.0) and inst.e[c] >= 0.0 for c in with_tw)
    assert all(inst.e[c] == 0.0 and inst.l[c] == INF for c in range(1, 13) if c not in with_tw)


def test_no_windows_at_share_zero_and_all_windows_at_share_one():
    assert make_instance(2, 8, 2, CFG, tw_share=0.0).tw_count == 0
    inst = make_instance(2, 8, 2, CFG, tw_share=1.0, tw_width_h=4.0)
    assert inst.tw_count == 8 and all(inst.l[c] - inst.e[c] == pytest.approx(240.0) for c in range(1, 9))


def test_window_draws_are_paired_across_shares():
    """Ziehungen (Auswahl, Lage) sind unabhängig von share und Breite: wer bei 40 % ein Fenster hat, hat es auch bei 60 %."""
    lo = make_instance(3, 12, 2, CFG, tw_share=0.4, tw_width_h=8.0)
    hi = make_instance(3, 12, 2, CFG, tw_share=0.6, tw_width_h=8.0)
    assert {c for c in range(1, 13) if lo.l[c] < INF} <= {c for c in range(1, 13) if hi.l[c] < INF}
    assert lo.tw_count <= hi.tw_count


def test_windows_are_built_around_a_rule_free_reference_tour_so_the_base_is_never_late():
    inst = make_instance(4, 10, 2, CFG, tw_share=0.6, tw_width_h=8.0)
    ev0 = Ev(inst, CFG)
    routes, _ = solve(ev0, seed=4 * 31 + 7, ils=1)                        # dieselbe Referenztour wie in reference_windows
    late = sum(plan_stats(ev0.plan(r)["events"], CFG)["late_min"] for r in routes if r)
    assert late == 0.0 and inst.tw_count > 0


def test_reference_windows_only_change_the_time_windows():
    inst = make_geometry(4, 10, 2)
    windowed = reference_windows(inst, CFG, 4, 0.6, 4.0)
    assert windowed.tw_count == make_instance(4, 10, 2, CFG, tw_share=0.6, tw_width_h=4.0).tw_count
    assert windowed.xy == inst.xy and windowed.dem == inst.dem                                # nur e/l ändern sich


# ---------------------------------------------------------------------------------------------------
# Evaluator an Handrechnungen
# ---------------------------------------------------------------------------------------------------
def _line(dist, svc=30.0, stations=None):
    """Depot (0,0), ein Kunde in `dist` km Entfernung, optionale Ladesäulen."""
    stations = list(stations or [])
    xy = [(0.0, 0.0), (dist, 0.0)] + stations
    m = len(xy)
    D = [[math.hypot(xy[i][0] - xy[j][0], xy[i][1] - xy[j][1]) for j in range(m)] for i in range(m)]
    return Inst(n=1, K=1, Q=10.0, xy=xy, ns=len(stations), nr=0, dem=[0, 1] + [0] * len(stations),
                e=[0.0] * m, l=[INF] * m, svc=[0.0, svc] + [0.0] * len(stations), D=D)


def test_rule_free_cost_by_hand():
    cfg = replace(CFG, **EXACT)
    inst = _line(300.0)
    rate = (32.0 + 15.0) / 60.0
    expected = 0.70 * 600.0 + rate * (600.0 / 75.0 * 60.0 + 30.0)
    assert Ev(inst, cfg).cost((1,)) == pytest.approx(expected, abs=1e-9)
    assert Ev(inst, cfg).cost(()) == 0.0


def test_driver_rules_cost_by_hand_one_break_and_no_rest():
    """300 km hin und zurück: 240 min Fahrt, 30 min Service, 240 min Fahrt. Die Lenkzeit 270 min ist nach 30 min der Rückfahrt
    erreicht: genau eine Pflichtpause (45 min, bezahlt), keine Tagesruhe (480 min Lenkzeit)."""
    cfg = replace(CFG, **EXACT)
    inst = _line(300.0)
    rate = (32.0 + 15.0) / 60.0
    base = Ev(inst, cfg).cost((1,))
    ev = Ev(inst, cfg, 1, 0, 0)
    stats = plan_stats(ev.plan((1,))["events"], cfg)
    assert stats["breaks"] == 1 and stats["nights"] == 0
    assert ev.cost((1,)) == pytest.approx(base + rate * 45.0, abs=1e-9)


def test_driver_rules_cost_by_hand_one_rest():
    """400 km hin und zurück = 640 min Lenkzeit > 540 min: eine Tagesruhe (660 min Fahrzeugzeit + 100 EUR, Fahrer unbezahlt)."""
    cfg = replace(CFG, **EXACT)
    inst = _line(400.0)
    p = Ev(inst, cfg, 1, 0, 0).plan((1,))
    st = plan_stats(p["events"], cfg)
    assert st["nights"] == 1 and st["rest_min"] == 660.0 and st["breaks"] >= 1
    rate, rveh = (32.0 + 15.0) / 60.0, 15.0 / 60.0
    drive_min = 2 * 400.0 / 75.0 * 60.0
    expected = 0.70 * 800.0 + rate * (drive_min + 30.0 + 45.0 * st["breaks"]) + rveh * 660.0 + 100.0
    assert p["cost"] == pytest.approx(expected, abs=1e-6)
    assert cost_from_events(p["events"], cfg, inst) == pytest.approx(p["cost"], abs=1e-9)


def test_electric_route_needs_charging_and_is_infeasible_without_stations():
    cfg = replace(CFG, **EXACT)
    inst = _line(300.0)                                                     # 600 km Rundfahrt > 400 km Reichweite, keine Säule
    ev = Ev(inst, cfg, 0, 1, 0)
    assert not is_feasible(ev.cost((1,)))
    assert ev.cost((1,)) == pytest.approx(BIG + 600.0)                       # Strafkosten plus Tourlänge (Gradient für die Suche)
    assert ev.plan((1,)) is None
    with_station = _line(300.0, stations=[(300.0, 5.0)])                     # Säule am Kunden: laden während des Halts
    ev2 = Ev(with_station, cfg, 0, 1, 0)
    assert is_feasible(ev2.cost((1,))) and ev2.cost((1,)) > Ev(with_station, cfg).cost((1,))


def test_charging_time_is_proportional_to_the_energy():
    cfg = replace(CFG, **EXACT)
    inst = _line(300.0, stations=[(300.0, 5.0)])
    p = Ev(inst, cfg, 0, 1, 0).plan((1,))
    charges = [e for e in p["events"] if e[0] == "charge"]
    assert charges and all(e[2] - e[1] == pytest.approx(e[4] * 45.0 / 0.6 / 400.0) for e in charges)


def test_infinite_range_is_the_same_as_no_electric_switch():
    cfg = replace(CFG, **EXACT)
    inst = make_instance(0, 6, 2, CFG, tw_share=0.6)
    r = (1, 3, 5)
    assert Ev(inst, replace(cfg, R=1e7), 0, 1, 0).cost(r) == pytest.approx(Ev(inst, cfg).cost(r), abs=1e-6)


def test_cost_is_cached_and_counts_evaluations_once():
    inst = make_instance(0, 6, 2, CFG, tw_share=0.0)
    ev = Ev(inst, CFG, 1, 0, 0)
    a = ev.cost((1, 2, 3))
    assert ev.n_eval == 1 and ev.cost((1, 2, 3)) == a and ev.n_eval == 1
    ev.cost([1, 2, 3])                                                       # Liste und Tupel sind derselbe Schlüssel
    assert ev.n_eval == 1


def test_plan_of_an_empty_route_and_event_bookkeeping():
    inst = make_instance(0, 6, 2, CFG, tw_share=0.0)
    ev = Ev(inst, CFG, 1, 0, 0)
    assert ev.plan(()) == dict(cost=0.0, events=[], route=())
    p = ev.plan((2, 4))
    assert p["route"] == (2, 4) and p["cost"] == pytest.approx(ev.cost((2, 4)))
    assert [e[3] for e in p["events"] if e[0] == "serve"] == [2, 4]


def test_unpaid_pause_costs_only_vehicle_time():
    cfg = replace(CFG, **EXACT)
    inst = _line(300.0)
    paid = Ev(inst, cfg, 1, 0, 0)
    unpaid = Ev(inst, replace(cfg, pause_paid=False), 1, 0, 0)
    assert paid.cost((1,)) - unpaid.cost((1,)) == pytest.approx(45.0 * 32.0 / 60.0, abs=1e-9)


# ---------------------------------------------------------------------------------------------------
# Kennzahlen aus Ereignissen
# ---------------------------------------------------------------------------------------------------
EVENTS = [("drive", 0.0, 100.0, 125.0), ("break", 100.0, 145.0, "road"), ("serve", 145.0, 195.0, 3, 0.0),
          ("charge", 195.0, 240.0, 12, 100.0, "break"), ("charge", 240.0, 250.0, 13, 20.0, "plain"),
          ("wait", 250.0, 270.0, 5), ("serve", 270.0, 300.0, 5, 12.0), ("rest", 300.0, 960.0, "cust"),
          ("charge", 960.0, 1620.0, 14, 400.0, "rest"), ("drive", 1620.0, 1700.0, 100.0)]


def test_plan_stats_on_hand_events():
    st = plan_stats(EVENTS, CFG)
    assert st["km"] == 225.0 and st["drive_min"] == 180.0 and st["t_end"] == 1700.0
    assert st["nights"] == 2 and st["rests_at_charger"] == 1 and st["rest_min"] == 660.0 + 660.0
    assert st["breaks"] == 2 and st["breaks_at_charger"] == 1 and st["charges"] == 3
    assert st["charge_km"] == 520.0 and st["charge_min_plain"] == 10.0
    assert st["wait_min"] == 20.0 and st["late_min"] == 12.0 and st["late_n"] == 1
    assert st["pause_min"] == 45.0 + 45.0 and st["free_charge_min"] == min(45.0, 100.0 * 45.0 / 0.6 / 400.0)
    assert st["idle_min"] == 1700.0 - 180.0 - 80.0 and st["swaps"] == 0


def test_cost_from_events_by_hand_paid_and_unpaid():
    inst = _line(300.0)
    rate, rveh = 47.0 / 60.0, 15.0 / 60.0
    ev = [("drive", 0.0, 60.0, 75.0), ("break", 60.0, 105.0, "road"), ("serve", 105.0, 135.0, 1, 30.0),
          ("charge", 135.0, 200.0, 2, 50.0, "break"), ("rest", 200.0, 860.0, "road")]
    common = 0.70 * 75.0 + rate * 60.0 + rate * 30.0 + 40.0 * 30.0 / 60.0 + rveh * 660.0 + 100.0
    assert cost_from_events(ev, CFG, inst) == pytest.approx(common + rate * 45.0 + rate * 65.0)
    unpaid = common + rveh * 45.0 + (rveh * 45.0 + rate * 20.0)
    assert cost_from_events(ev, replace(CFG, pause_paid=False), inst) == pytest.approx(unpaid)


# ---------------------------------------------------------------------------------------------------
# Konstruktion und Suche
# ---------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("seed", [0, 1, 2, 3])
def test_construction_heuristics_return_valid_partitions(seed):
    inst = make_instance(seed, 12, 2, CFG, tw_share=0.0)
    for routes in (savings_routes(inst), insertion_routes(inst, random.Random(seed)), ffd_routes(inst)):
        assert len(routes) == inst.K and _partition_ok(inst, routes) and _capacity_ok(inst, routes)


def test_ffd_routes_are_sorted_by_angle_around_the_depot():
    inst = make_geometry(1, 10, 2)
    x0, y0 = inst.xy[0]
    for r in ffd_routes(inst):
        angles = [math.atan2(inst.xy[c][1] - y0, inst.xy[c][0] - x0) for c in r]
        assert angles == sorted(angles)


def test_fit_k_merges_the_smallest_routes_until_k_remain():
    inst = make_geometry(1, 8, 2)
    singles = [[c] for c in range(1, 9)]
    fitted = _fit_K(inst, singles)
    assert len(fitted) == inst.K and _partition_ok(inst, fitted) and _capacity_ok(inst, fitted)
    assert len(_fit_K(inst, [[1, 2, 3]])) == inst.K                            # zu wenige Touren: leere ergänzen


def test_perturb_keeps_the_partition_and_the_capacity():
    inst = make_geometry(2, 10, 2)
    routes = ffd_routes(inst)
    changed = False
    for s in range(6):
        new = perturb(routes, random.Random(s), inst, k=3)
        assert _partition_ok(inst, new) and _capacity_ok(inst, new)
        changed |= new != routes
    assert changed and routes == ffd_routes(inst)                              # Eingabe bleibt unverändert


def test_local_search_never_worsens_and_keeps_a_valid_partition():
    inst = make_instance(1, 9, 2, CFG, tw_share=0.6)
    for combo in [(0, 0, 0), (1, 0, 0), (0, 1, 0)]:
        ev = Ev(inst, CFG, *combo)
        start = ffd_routes(inst)
        routes, cost = local_search(ev, start, random.Random(1))
        assert cost <= total_cost(ev, start) + 1e-9 and cost == pytest.approx(total_cost(ev, routes))
        assert _partition_ok(inst, routes) and _capacity_ok(inst, routes)


def test_solve_is_deterministic_and_better_than_the_construction():
    inst = make_instance(2, 9, 2, CFG, tw_share=0.0)
    ev = Ev(inst, CFG)
    a, ca = solve(ev, 5)
    b, cb = solve(Ev(inst, CFG), 5)
    assert a == b and ca == cb and ca <= total_cost(ev, savings_routes(inst)) + 1e-9


def test_solve_all_returns_every_requested_cell_with_consistent_costs():
    inst = make_instance(1, 7, 2, CFG, tw_share=0.6)
    combos = [(0, 0, 0), (1, 0, 0), (0, 1, 0), (1, 1, 0)]
    out, pool = solve_all(inst, CFG, combos, 1, restarts=2)
    assert set(out) == set(combos) and pool
    for c, (routes, cost, ev) in out.items():
        assert _partition_ok(inst, routes) and cost == pytest.approx(total_cost(ev, routes))
        assert all(cost <= total_cost(ev, s) + 1e-9 for s in pool.values())    # Pool-Konsistenz
    assert _norm([[2, 1], [], [3]]) == ((2, 1), (3,)) and _norm([[3], [1, 2]]) == _norm([[1, 2], [3]])


# ---------------------------------------------------------------------------------------------------
# Ergänzungen aus dem Fehler-Einbau-Test (tools/mutation_check.py)
# ---------------------------------------------------------------------------------------------------
def test_a_tiny_lateness_still_counts_as_a_late_stop():
    """late_n zählt jede Verspätung über 1e-9 Minuten (nicht erst ab einer Millisekunde)."""
    st = plan_stats([("serve", 0.0, 10.0, 1, 5e-4), ("serve", 10.0, 20.0, 2, 0.0)], CFG)
    assert st["late_n"] == 1 and st["late_min"] == pytest.approx(5e-4)


def test_search_parameter_defaults_are_the_ones_of_the_measurement_series():
    """Die Suchparameter (Defaults) sind die der Messreihe fern.py: nur dann rechnen Live-Instanz und Messreihe dasselbe Verfahren."""
    import inspect
    d = lambda f: {k: v.default for k, v in inspect.signature(f).parameters.items() if v.default is not inspect.Parameter.empty}  # noqa: E731
    assert d(local_search) == dict(nn_k=6, max_pass=30, screen=None)
    assert d(solve) == dict(starts=None, ils=2, n_ls=3, screen=None)
    assert d(solve_all) == dict(restarts=6, margin=150.0, reps_exp=(2, 3, 3))
    assert d(perturb) == dict(k=3)
    assert d(make_instance)["tw_share"] == 0.6 and d(make_instance)["tw_width_h"] == 8.0 and d(make_instance)["tw_ref"] == "plain"
    assert d(make_geometry) == dict(n=18, K=3, area=800.0, ns=12, nr=4, depot=(0.5, 0.5), fill=0.8)


def test_first_fit_decreasing_balances_the_loads_like_a_reference_implementation():
    inst = make_geometry(3, 12, 3)
    loads = [0] * inst.K
    for d in sorted(inst.dem[1:13], reverse=True):
        j = min(range(inst.K), key=lambda x: loads[x])
        loads[j] += d
    got = sorted(sum(inst.dem[c] for c in r) for r in ffd_routes(inst))
    assert got == sorted(loads)
    asc = [0] * inst.K
    for d in sorted(inst.dem[1:13]):
        j = min(range(inst.K), key=lambda x: asc[x])
        asc[j] += d
    assert sorted(asc) != sorted(loads)                                    # absteigend sortiert packt anders als aufsteigend (Sanity der Referenz)


def test_windows_with_the_rule_reference_differ_from_the_rule_free_ones_and_are_on_time_for_f():
    plain = make_instance(1, 8, 2, CFG, tw_share=0.8, tw_width_h=4.0, tw_ref="plain")
    rules = make_instance(1, 8, 2, CFG, tw_share=0.8, tw_width_h=4.0, tw_ref="rules")
    assert plain.e != rules.e and plain.tw_count == rules.tw_count                          # gleiche Auswahl, andere Lage
    evF = Ev(rules, CFG, 1, 0, 0)
    routes, _ = solve(evF, seed=1 * 31 + 7, ils=1)                                          # dieselbe Referenztour wie in reference_windows
    assert sum(plan_stats(evF.plan(r)["events"], CFG)["late_min"] for r in routes if r) == 0.0


def test_no_reference_tour_is_computed_when_there_are_no_windows(monkeypatch):
    """Ohne Zeitfenster (Anteil 0) entfällt die Referenztour ganz: das spart die Hälfte der Rechenzeit der Live-Instanz."""
    import fv_search

    def boom(*a, **k):
        raise AssertionError("reference_windows darf ohne Fenster nicht laufen")

    monkeypatch.setattr(fv_search, "reference_windows", boom)
    assert make_instance(1, 8, 2, CFG, tw_share=0.0).tw_count == 0
