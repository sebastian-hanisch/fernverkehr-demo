"""Plotly-Figuren: Achsen fest (fixedrange), Inhalt gegen die Daten, Legenden, Farbkonsistenz, Randfälle (unzulässige Zelle,
eine Tour, keine Ladehalte)."""
import copy

import pytest

import fv_constants as C
import fv_results as R
import fv_schedule as S
import fv_visualization as V
from live_cache import fresh_copy, get_live

DATA = R.load_results()


def _locked(fig):
    xs = [v for k, v in fig.layout.to_plotly_json().items() if k.startswith("xaxis")]
    ys = [v for k, v in fig.layout.to_plotly_json().items() if k.startswith("yaxis")]
    return xs and ys and all(a.get("fixedrange") for a in xs + ys)


def _all_figures():
    res = get_live()
    figs = [("map", V.route_map_figure(res, C.CELL_FE)), ("timeline", V.timeline_figure(res, C.CELL_FE)),
            ("cost", V.cost_breakdown_figure(res)), ("fix", V.fix_vs_replanned_figure(res)), ("sum", V.sum_vs_combo_figure(DATA)),
            ("comp_mittel", V.components_figure(DATA, "mittel")), ("comp_keine", V.components_figure(DATA, "keine")),
            ("pause", V.assumption_figure(DATA, "pause")), ("strafe", V.assumption_figure(DATA, "strafe"))]
    figs += [(f"axis_{a}", V.axis_figure(R.axis_rows(DATA, a), a)) for a in R.AXIS_NAMES]
    figs += [(f"map_{c}", V.route_map_figure(res, c)) for c in C.CELLS]
    figs += [(f"timeline_{c}", V.timeline_figure(res, c)) for c in C.CELLS]
    return figs


@pytest.mark.parametrize("name,fig", _all_figures(), ids=lambda v: v if isinstance(v, str) else "")
def test_every_figure_locks_its_axes_for_touch_scrolling(name, fig):
    assert _locked(fig), name


@pytest.mark.parametrize("name,fig", _all_figures(), ids=lambda v: v if isinstance(v, str) else "")
def test_every_figure_has_a_horizontal_legend_at_the_bottom_and_a_white_template(name, fig):
    assert fig.layout.template.layout.plot_bgcolor == "white"                                # plotly_white
    legend = fig.layout.legend
    assert legend.orientation == "h" and legend.y == 0.0


def test_map_shows_depot_customers_stations_routes_and_charging_stops():
    res = get_live()
    fig = V.route_map_figure(res, C.CELL_FE)
    names = [t.name for t in fig.data]
    assert names[0] == "Ladesäule" and "Depot" in names and "Kunde (Ring = mit Zeitfenster)" in names
    assert [n for n in names if n and n.startswith("Lkw")] == [f"Lkw {t['truck']}" for t in res["cells"][C.CELL_FE]["trucks"]]
    stations = fig.data[0]
    assert len(stations.x) == 12 and list(stations.x) == [res["xy"][s][0] for s in res["stations"]]
    customers = next(t for t in fig.data if t.name.startswith("Kunde"))
    assert len(customers.x) == 6 and list(customers.text) == [str(c) for c in range(1, 7)]
    depot = next(t for t in fig.data if t.name == "Depot")
    assert (depot.x[0], depot.y[0]) == res["xy"][0]
    assert "Ladehalt" in names                                                            # F+E hat Ladehalte
    # jede Linie startet und endet im Depot und trifft alle Kunden der Tour
    for t, line in zip(res["cells"][C.CELL_FE]["trucks"], [d for d in fig.data if d.name and d.name.startswith("Lkw")]):
        assert (line.x[0], line.y[0]) == res["xy"][0] == (line.x[-1], line.y[-1])
        assert len(line.x) == len(S.route_nodes(t["events"]))


def test_map_marks_customers_with_time_windows_by_a_ring():
    res = get_live()
    fig = V.route_map_figure(res, C.CELL_F)
    customers = next(t for t in fig.data if t.name.startswith("Kunde"))
    rings = list(customers.marker.line.width)
    assert rings == [3 if res["late"][c] is not None else 0 for c in range(1, 7)] and 3 in rings
    none = get_live(6, 45, 400, "keine", 3)
    assert set(next(t for t in V.route_map_figure(none, C.CELL_F).data if t.name.startswith("Kunde")).marker.line.width) == {0}


def test_map_without_charging_has_no_charging_stop_trace_and_keeps_square_aspect():
    res = get_live()
    fig = V.route_map_figure(res, C.CELL_F)
    assert "Ladehalt" not in [t.name for t in fig.data]
    assert fig.layout.yaxis.scaleanchor == "x" and tuple(fig.layout.xaxis.range) == tuple(fig.layout.yaxis.range)


def test_timeline_has_one_row_per_truck_and_one_bar_per_event():
    res = get_live()
    for c in C.CELLS:
        fig = V.timeline_figure(res, c)
        n_events = sum(len(t["events"]) for t in res["cells"][c]["trucks"])
        assert sum(len(tr.x) for tr in fig.data) == n_events
        assert {y for tr in fig.data for y in tr.y} == {f"Lkw {t['truck']}" for t in res["cells"][c]["trucks"]}
        assert fig.layout.yaxis.autorange == "reversed" and fig.layout.barmode == "overlay"


def test_timeline_traces_use_the_legend_colors_and_names():
    fig = V.timeline_figure(get_live(), C.CELL_FE)
    for tr in fig.data:
        base = tr.name.replace(", verspätet", "")
        art = next(k for k, v in C.EVENT_NAMES.items() if v == base)
        assert tr.marker.color == C.EVENT_COLORS[art]
    names = {tr.name for tr in fig.data}
    assert {"Fahrt", "Service beim Kunden", "Laden in der Pause", "Tagesruhe"} <= names
    assert "Pflichtpause (45 min)" in {tr.name for tr in V.timeline_figure(get_live(), C.CELL_F).data}    # F allein: Pause auf der Straße


def test_timeline_marks_late_service_with_a_red_outline():
    res = fresh_copy(get_live())
    trucks = res["cells"][C.CELL_F]["trucks"]
    ev = trucks[0]["events"]
    i = next(i for i, e in enumerate(ev) if e[0] == "serve")
    ev[i] = ev[i][:4] + (25.0,)
    fig = V.timeline_figure(res, C.CELL_F)
    late = [t for t in fig.data if t.name == "Service beim Kunden, verspätet"]
    n_late = sum(1 for t in trucks for e in t["events"] if e[0] == "serve" and e[4] > 1e-9)
    assert len(late) == 1 and late[0].marker.line.color == "#c0392b" and len(late[0].x) == n_late >= 1
    assert n_late == sum(1 for t in get_live()["cells"][C.CELL_F]["trucks"] for e in t["events"] if e[0] == "serve" and e[4] > 1e-9) + 1


def test_timeline_draws_day_boundaries_for_multi_day_plans():
    res = get_live()
    fig = V.timeline_figure(res, C.CELL_FE)
    end_h = max(b["t1"] for t in res["cells"][C.CELL_FE]["trucks"] for b in S.bars(t["events"], res["n"]))
    assert len(fig.layout.shapes) == int(end_h // 24)


def test_cost_breakdown_stacks_the_five_cost_types_and_labels_the_totals():
    res = get_live()
    fig = V.cost_breakdown_figure(res)
    assert [t.name for t in fig.data] == [C.COST_LABELS[k] for k in C.COST_KEYS] and fig.layout.barmode == "stack"
    for j, cell in enumerate(C.CELLS):
        assert sum(t.y[j] for t in fig.data) == pytest.approx(res["cells"][cell]["total"])
    assert len(fig.layout.annotations) == 4
    assert [t.marker.color for t in fig.data] == [C.COST_COLORS[k] for k in C.COST_KEYS]


def test_cost_breakdown_and_fix_figure_skip_infeasible_cells():
    res = fresh_copy(get_live())
    e = res["cells"][C.CELL_E]
    e.update(feasible=False, total=None, metrics=None, comps=None, trucks=[], fix_total=None)
    assert list(V.cost_breakdown_figure(res).data[0].x) == ["ohne Regeln", "F", "F+E"]
    assert list(V.fix_vs_replanned_figure(res).data[0].x) == [C.CELL_LABELS[C.CELL_F], C.CELL_LABELS[C.CELL_FE]]
    assert V.route_map_figure(res, C.CELL_E) is not None and V.timeline_figure(res, C.CELL_E).data == ()


def test_fix_figure_shows_fixed_and_replanned_extra_costs_in_percent():
    res = get_live()
    fig = V.fix_vs_replanned_figure(res)
    base = res["cells"][C.CELL_BASE]["total"]
    assert [t.name for t in fig.data] == ["feste Touren nachbewertet", "neu geplant"]
    for j, cell in enumerate((C.CELL_F, C.CELL_E, C.CELL_FE)):
        assert fig.data[1].y[j] == pytest.approx(100 * (res["cells"][cell]["total"] - base) / base)
        assert fig.data[0].y[j] == pytest.approx(100 * (res["cells"][cell]["fix_total"] - base) / base)
        assert fig.data[0].y[j] >= fig.data[1].y[j] - 1e-9                                 # neu geplant nie schlechter


def test_fix_figure_labels_an_undriveable_fixed_plan():
    res = fresh_copy(get_live())
    res["cells"][C.CELL_E]["fix_total"] = None
    fig = V.fix_vs_replanned_figure(res)
    assert fig.data[0].y[1] is None and fig.data[0].text[1] == "nicht fahrbar"


def test_sum_figure_stacks_fahrer_and_elektro_next_to_the_measured_combination():
    fig = V.sum_vs_combo_figure(DATA)
    rows = R.sum_rows(DATA)
    assert [t.name for t in fig.data] == ["Fahrerregeln allein", "Elektro allein", "beides, gemessen"]
    assert list(fig.data[0].y) == pytest.approx([r["dF"].mean for r in rows])
    assert list(fig.data[1].y) == pytest.approx([r["dE"].mean for r in rows])
    assert list(fig.data[2].y) == pytest.approx([r["dFE"].mean for r in rows])
    assert fig.data[0].offsetgroup == fig.data[1].offsetgroup != fig.data[2].offsetgroup
    assert len(fig.layout.annotations) == 4 and "Summe" in fig.layout.annotations[0].text
    assert all(x.count("Kunden/Lkw") == 1 for x in fig.data[0].x)                          # Größe an jeder Zahl


@pytest.mark.parametrize("axis", R.AXIS_NAMES)
def test_axis_figure_shows_every_row_with_standard_error_bars(axis):
    rows = R.axis_rows(DATA, axis)
    fig = V.axis_figure(rows, axis)
    assert sum(len(t.y) for t in fig.data) == len(rows)
    assert sorted(y for t in fig.data for y in t.y) == pytest.approx(sorted(r["stat"].mean for r in rows))
    assert sorted(e for t in fig.data for e in t.error_y.array) == pytest.approx(sorted(r["stat"].se for r in rows))
    assert fig.layout.xaxis.title.text == axis and fig.layout.barmode == "group"
    assert any(s.y0 == 0 for s in fig.layout.shapes)                                       # Nulllinie


def test_axis_figure_uses_one_color_per_size_and_hatches_the_first_group():
    fig = V.axis_figure(R.axis_rows(DATA, "Ladezeit"), "Ladezeit")
    by_name = {t.name: t for t in fig.data}
    assert set(by_name) == {"ohne Zeitfenster, 10/2 (Kunden/Lkw)", "ohne Zeitfenster, 18/3 (Kunden/Lkw)",
                            "Zeitfenster mittel, 10/2 (Kunden/Lkw)", "Zeitfenster mittel, 18/3 (Kunden/Lkw)"}
    for name, tr in by_name.items():
        size = "10/2" if "10/2" in name else "18/3"
        assert tr.marker.color == C.SIZE_COLORS[size]                                      # eine Farbe je Reihe (Muster verträgt keine Farbliste)
        assert (tr.marker.pattern.shape == "/") == name.startswith("ohne")


def test_axis_figure_for_vehicles_is_one_series_with_its_own_size_per_level():
    fig = V.axis_figure(R.axis_rows(DATA, "Fahrzeuge"), "Fahrzeuge")
    assert len(fig.data) == 1 and list(fig.data[0].x) == ["2 Lkw", "3 Lkw", "4 Lkw"]
    assert [row[1] for row in fig.data[0].customdata] == ["12 Kunden, 2 Lkw", "18 Kunden, 3 Lkw", "24 Kunden, 4 Lkw"]


@pytest.mark.parametrize("window,names", [("mittel", ("live10", "basis")), ("keine", ("live10_kein_fenster", "kein_fenster"))])
def test_components_figure_is_normalised_by_the_rule_free_cost(window, names):
    fig = V.components_figure(DATA, window)
    assert len(fig.data) == 2
    for tr, name in zip(fig.data, names):
        s = DATA[name]
        assert list(tr.x) == [C.COST_LABELS[k] for k in C.COST_KEYS]
        assert list(tr.y) == pytest.approx([100 * s["comps_I"][k]["mean"] / s["base_eur"]["mean"] for k in C.COST_KEYS])
        assert f"{s['n']} Kunden, {s['K']} Lkw ({s['used']} Instanzen)" == tr.name
    with pytest.raises(KeyError):
        V.components_figure(DATA, "eng")


def test_assumption_figures_show_paid_against_unpaid_and_the_three_penalties():
    pause = V.assumption_figure(DATA, "pause")
    c = DATA["_ap0_c_unbezahlte_pausen"]
    assert [t.name for t in pause.data] == ["Pausen bezahlt (Grundannahme)", "Pausen unbezahlt"]
    assert list(pause.data[0].y) == pytest.approx([c["kein_fenster_45min"]["I_paid"]["mean"], c["basis_45min_mit_fenster"]["I_paid"]["mean"]])
    assert list(pause.data[1].y) == pytest.approx([c["kein_fenster_45min"]["I_unpaid"]["mean"], c["basis_45min_mit_fenster"]["I_unpaid"]["mean"]])
    strafe = V.assumption_figure(DATA, "strafe")
    p = DATA["_ap0_d_verspaetungsstrafe"]
    assert list(strafe.data[0].x) == ["20 EUR/h", "40 EUR/h", "80 EUR/h"]
    assert list(strafe.data[0].y) == pytest.approx([p[k]["I"]["mean"] for k in ("20", "40", "80")])
    assert list(strafe.data[1].y) == pytest.approx([p[k]["I_oper"]["mean"] for k in ("20", "40", "80")])


def test_figures_do_not_modify_their_inputs():
    res = get_live()
    before = copy.deepcopy(res)
    for c in C.CELLS:
        V.route_map_figure(res, c)
        V.timeline_figure(res, c)
    V.cost_breakdown_figure(res)
    V.fix_vs_replanned_figure(res)
    assert res == before


def test_hours_and_number_formats_use_the_decimal_comma():
    assert V._de(1.25) == "1,2" or V._de(1.25) == "1,3"
    assert V._de(-3.14159, 2) == "-3,14" and V._de(2.0, 1, True) == "+2,0" and V._hours(90) == "1,5"


def test_axis_figure_series_with_several_sizes_keep_one_color_per_bar_without_a_pattern():
    fig = V.axis_figure(R.axis_rows(DATA, "Fahrzeuge"), "Fahrzeuge")
    assert fig.data[0].marker.pattern.shape in (None, "")
    for tr in V.axis_figure(R.axis_rows(DATA, "Ladezeit"), "Ladezeit").data:
        assert isinstance(tr.marker.color, str)
