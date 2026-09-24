"""Die Werkzeuge der Messreihe: tools/sweep.py (Konfigurationen, Seed-Konvention), tools/dump_sweep.py (Aggregation) und
tools/build_results.py (erzeugt data/fv_results.json). Die echte Messreihe (52 Minuten auf 16 Kernen) läuft nie in der CI; hier läuft
die ganze Kette auf SYNTHETISCHEN Rohdaten: Rohzeilen -> dump_sweep -> build_results -> fv_results.load_results -> Auswertung."""
import json
import math
import pathlib
import sys

import pytest

TOOLS = pathlib.Path(__file__).resolve().parent.parent / "tools"
sys.path.insert(0, str(TOOLS))

import build_results as B  # noqa: E402
import dump_sweep  # noqa: E402
import sweep  # noqa: E402

import fv_constants as C  # noqa: E402
import fv_results as R  # noqa: E402

CELLS = ("---", "F--", "-E-", "FE-")


# ---------------------------------------------------------------------------------------------------
# sweep.py: Konfigurationen und Seed-Konvention
# ---------------------------------------------------------------------------------------------------
def test_every_kept_series_is_a_sweep_configuration():
    assert set(B.KEEP) <= set(sweep.CONFIGS)
    stafette = [n for n in sweep.CONFIGS if "stafette" in n]
    assert len(stafette) == 4 and not set(stafette) & set(B.KEEP) and "gross" not in B.KEEP


def test_sweep_configurations_have_the_documented_sizes_and_windows():
    c = sweep.CONFIGS
    assert c["basis"][:2] == (18, 3) and c["basis"][2] == (0.6, 8.0, "plain") and c["basis"][5] == 60
    assert c["live10"][:2] == (10, 2) and c["live10"][5] == 60 and c["kein_fenster"][2][0] == 0.0
    assert c["reich300"][3] == {"R": 300.0} and c["lade90"][3] == {"t_typ": 90.0}
    assert c["unbezahlt_basis"][3] == {"pause_paid": False} and c["strafe80"][3] == {"c_late": 80.0}
    assert c["fenster_regelbewusst"][2][2] == "rules" and c["fahrzeuge2"][:2] == (12, 2) and c["fahrzeuge4"][:2] == (24, 4)
    assert all(len(v[4]) in (4, 6) for v in c.values())
    assert all(v[4][:4] == [(0, 0, 0), (1, 0, 0), (0, 1, 0), (1, 1, 0)] for v in c.values())


def test_valid_seeds_of_the_sweep_equal_the_live_seed_lookup():
    """Die Seed-Konvention der Messreihe (tools/sweep.py) und die Live-Instanz (fv_live) wählen dieselben gültigen Seeds."""
    import fv_live
    assert sweep.valid_seeds(10, 2, 8) == fv_live.valid_seeds(8, 10, 2, 300)
    assert sweep.valid_seeds(6, 2, 5) == fv_live.valid_seeds(5, 6, 2, 300)


# ---------------------------------------------------------------------------------------------------
# build_results.py: Bausteine
# ---------------------------------------------------------------------------------------------------
def test_rounding_and_stat_reduction():
    assert B.r(1.234567) == 1.2346 and B.r(3) == 3 and B.r("x") == "x"
    d = dict(n=5, mean=1.23456789, se=0.5, median=1.0, q1=0.5, q3=2.0, neg_share=0.2, pos_share=0.8, extra=1)
    assert B.stat(d) == dict(n=5, mean=1.2346, se=0.5, median=1.0, q1=0.5, q3=2.0, neg_share=0.2)
    assert B.mean_se(d) == dict(mean=1.2346, se=0.5)


def _row(base, f, e, fe, ok=True, re_total=1.0):
    def cell(t):
        return dict(total=t, feasible=ok, re_total=re_total)
    return dict(cells={"---": cell(base), "F--": cell(f), "-E-": cell(e), "FE-": cell(fe)})


def test_interaction_and_state_shares_at_the_two_percent_boundaries():
    assert B.interaction_pct(_row(1000.0, 1400.0, 1300.0, 1800.0)) == pytest.approx(10.0)
    assert B.interaction_pct(_row(1000.0, 1400.0, 1300.0, 1580.0)) == pytest.approx(-12.0)
    rows = [_row(1000.0, 1400.0, 1300.0, 1700.0 + d) for d in (-20.01, -20.0, 0.0, 20.0, 20.01)]       # I = -2,001 / -2 / 0 / 2 / 2,001 %
    s = B.state_shares(rows)
    assert s == dict(n=5, billiger=0.2, additiv=0.6, teurer=0.2)
    assert B.state_shares(rows, thr=1.0)["additiv"] == 0.2


def test_usable_drops_infeasible_cells_and_unevaluated_base_tours():
    rows = [_row(1000, 1400, 1300, 1700), _row(1000, 1400, 1300, 1700, ok=False), _row(1000, 1400, 1300, 1700, re_total=None)]
    assert len(B.usable(rows)) == 1


def test_parse_timing(tmp_path):
    p = tmp_path / "t.txt"
    p.write_text("n=8 seed=10 inst 0.0s solve 1.0s | F--=+38%\nn=8 seed=11 inst 0.0s solve 1.1s | x\nn=12 seed=10 inst 0.0s solve 9.0s | y\nrauschen\n",
                 encoding="utf-8")
    assert B.parse_timing(p) == {"8": [1.0, 1.1], "12": [9.0]}


# ---------------------------------------------------------------------------------------------------
# Ganze Kette auf synthetischen Rohdaten
# ---------------------------------------------------------------------------------------------------
def _synthetic_cell(rng_seed, kind, has_window):
    """Kosten und Kennzahlen einer Zelle, deterministisch aus (rng_seed, kind)."""
    base = 3000.0 + 37.0 * (rng_seed % 7)
    extra = {"---": 0.0, "F--": 0.25, "-E-": 0.18, "FE-": 0.40 + 0.02 * ((rng_seed % 5) - 2)}[kind]
    late = (0.0 if kind == "---" or not has_window else 40.0 * (1 + rng_seed % 3) * (2.0 if kind == "FE-" else 1.0))
    total = base * (1 + extra) + late
    ruled = kind in ("F--", "FE-")
    charged = kind in ("-E-", "FE-")
    return dict(total=total, oper=total - late, late_cost=late, late_min=late * 1.5, late_n=int(late > 0), km=3600.0 + 100 * (kind != "---"),
                span_min=3700.0 + 500 * ruled + 200 * charged, drive_min=2900.0, driver_h=60.0 + 5 * ruled, idle_min=100.0 + 900 * ruled + 300 * charged,
                wait_min=(20.0 if ruled and rng_seed % 2 else 0.0), nights=(3 + rng_seed % 2) if ruled else 0,
                breaks=(6 + rng_seed % 3) if ruled else 0, breaks_at_charger=(3 if kind == "FE-" else 0), charges=(9 if charged else 0),
                charge_km=(1500.0 if charged else 0.0), charge_min_plain=(120.0 if charged else 0.0),
                free_charge_min=(200.0 if kind == "FE-" else 0.0), rests_at_charger=(2 if kind == "FE-" else 0), swaps=0, used=2,
                n_eval=100, re_total=total * 1.05, feasible=True, routes=[[1, 2], [3]], rest_min=660.0 * ((3 + rng_seed % 2) if ruled else 0),
                pause_min=45.0 * ((6 + rng_seed % 3) if ruled else 0))


def _write_synthetic(tmp_path):
    seeds = list(range(12))
    for name in B.KEEP:
        share = sweep.CONFIGS[name][2][0]
        rows = []
        for s in seeds:
            cells = {k: _synthetic_cell(s + 3 * len(name), k, share > 0) for k in CELLS}
            if len(sweep.CONFIGS[name][4]) == 6:                    # Hauptreihen mit Stafette-Zellen: die App zeigt sie nicht
                cells["F-S"] = dict(cells["F--"], total=cells["F--"]["total"] * 0.95)
                cells["FES"] = dict(cells["FE-"], total=cells["FE-"]["total"] * 0.95)
            rows.append(dict(config=name, seed=s, tw_count=int(10 * share), pool=5, total_s=1.0, cells=cells))
        if name == "live10_reich300":                               # ausgeschlossene Lagen: zwei ohne zulässige Suche, eine mit unfahrbaren Basistouren
            for r in rows[:2]:
                r["cells"]["-E-"].update(feasible=False, total=None, oper=None, re_total=None)
            rows[2]["cells"]["---"]["re_total"] = None
        (tmp_path / f"raw_{name}.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    for fname, keys in (("raw_noise_live.jsonl", ("a", "b")), ("raw_noise_live_ext.jsonl", ("c", "d", "e", "f"))):
        rows = []
        for name in ("live10", "live10_kein_fenster"):
            for s in seeds:
                row = dict(config=name, seed=s)
                for j, k in enumerate(keys):
                    row[k] = {c: _synthetic_cell(s, c, name == "live10")["total"] * (1 + (0.01 * j if (c == "FE-" and s % 5 == 0) else 0.0)) for c in CELLS}
                    if s == 3 and k in ("a", "b"):                  # Seed 1 und 2 der Suche: I = +1,0 % gegen +2,5 % (Zustand kippt bei 2 %, nicht bei 3 %)
                        cost = row[k]
                        cost["FE-"] = cost["F--"] + cost["-E-"] - cost["---"] + (0.010 if k == "a" else 0.025) * cost["---"]
                rows.append(row)
        (tmp_path / fname).write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    (tmp_path / "timing_live.txt").write_text("n=8 seed=10 inst 0.0s solve 1.0s | a\nn=8 seed=11 inst 0.0s solve 1.1s | b\n", encoding="utf-8")


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("messreihe")
    _write_synthetic(tmp)
    old = (sweep.HERE, dump_sweep.HERE)
    sweep.HERE = dump_sweep.HERE = str(tmp)
    try:
        import contextlib
        import io
        with contextlib.redirect_stdout(io.StringIO()):
            dump_sweep.main()
    finally:
        sweep.HERE, dump_sweep.HERE = old
    out = tmp / "fv_results.json"
    sys.argv = ["build_results.py", "--sweep-data", str(tmp / "sweep_data.json"), "--out", str(out)]
    import contextlib
    import io
    with contextlib.redirect_stdout(io.StringIO()):
        B.main()
    return out


def test_build_results_writes_a_small_file_with_one_line_per_key(built):
    text = built.read_text(encoding="utf-8")
    lines = text.strip().splitlines()
    assert lines[0] == "{" and lines[-1] == "}" and len(lines) == len(B.KEEP) + 5 + 2
    assert len(text) < 120_000 and all(line.rstrip(",").startswith('"') for line in lines[1:-1])
    assert '"routes"' not in text and '"F-S"' not in text and '"FES"' not in text


def test_built_file_has_the_schema_the_app_reads(built):
    data = R.load_results(built)
    assert set(data) == set(B.KEEP) | {"_meta", "_ap0_c_unbezahlte_pausen", "_ap0_d_verspaetungsstrafe", "_ap0_b_suchrauschen", "_timings"}
    assert data["_meta"]["schwelle_pct"] == 2.0 and data["_meta"]["zellen"] == list(CELLS)
    assert data["_timings"]["live_suche_s"] == {"8": [1.0, 1.1]}
    for name in B.KEEP:
        s = data[name]
        assert s["used"] == (9 if name == "live10_reich300" else 12) and s["n"] == sweep.CONFIGS[name][0] and s["K"] == sweep.CONFIGS[name][1]
        for key in ("dF", "dE", "dFE", "I", "I_eur", "I_oper"):
            assert set(R.Stat.from_dict(s[key]).__dict__) == {"n", "mean", "se", "median", "q1", "q3", "neg_share"}
        assert s["states"]["n"] == s["used"] and sum(v for k, v in s["states"].items() if k != "n") == pytest.approx(1.0, abs=2e-4)
        assert set(s["comps_delta"]) == set(CELLS[1:]) and set(s["cells"]) == set(CELLS)


def test_built_file_is_consistent_with_the_raw_rows(built):
    data = R.load_results(built)
    rows = B.raw_rows(built.parent, "basis")
    vals = [B.interaction_pct(r) for r in rows]
    assert data["basis"]["I"]["mean"] == pytest.approx(sum(vals) / len(vals), abs=1e-3)
    assert data["basis"]["dFE"]["mean"] - data["basis"]["dF"]["mean"] - data["basis"]["dE"]["mean"] == pytest.approx(data["basis"]["I"]["mean"], abs=2e-3)


def test_excluded_instances_are_counted_by_reason_and_stafette_cells_are_dropped(built):
    data = R.load_results(built)
    s = data["live10_reich300"]
    assert (s["instances"], s["used"], s["excluded"]) == (12, 9, 3)
    assert s["excluded_reasons"] == dict(suche_ohne_loesung=2, basistouren_unter_E_nicht_fahrbar=1)
    assert s["states"]["n"] == 9
    assert "excluded_reasons" not in data["basis"]                                        # nur Reihen mit ausgeschlossenen Lagen
    assert set(data["basis"]["comps_delta"]) == {"F--", "-E-", "FE-"} and set(data["basis"]["cells"]) == set(CELLS)


def test_the_flip_count_of_the_message_at_two_percent_is_taken_from_the_noise_rows(built):
    """Zwei Such-Seeds ergeben I = +1,0 % und +2,5 %: bei 2 % kippt die Meldung (additiv -> teurer), bei 3 % nicht."""
    data = R.load_results(built)
    g = data["_ap0_b_suchrauschen"]["gepoolt"]
    assert g["kippen_bei_2_prozent"]["seed1_vs_seed2"] == 2                                # je eine Instanz in beiden Konfigurationen
    rows = [json.loads(line) for line in (built.parent / "raw_noise_live.jsonl").read_text(encoding="utf-8").splitlines()]

    def i_pct(c):
        return 100 * (c["FE-"] - c["F--"] - c["-E-"] + c["---"]) / c["---"]

    def state(v, thr):
        return -1 if v < -thr else (1 if v > thr else 0)

    for thr, expected in ((2.0, 2), (3.0, 0)):
        assert sum(state(i_pct(r["a"]), thr) != state(i_pct(r["b"]), thr) for r in rows) == expected, thr


def test_the_built_file_drives_the_evaluation_code(built):
    """Die Auswertung (Urteil, Achsen, Messreihen-Wahl, Stories-Struktur) läuft auf der synthetischen Datei wie auf der echten."""
    data = R.load_results(built)
    for axis in R.AXIS_NAMES:
        rows = R.axis_rows(data, axis)
        assert rows and all(r["stat"].n in (9, 12) for r in rows)
    assert R.find_series(data, 18, 3, "mittel", 45, 400) == "basis"
    assert len(R.sum_rows(data)) == 4
    import fv_stories as ST
    for name in C.PRESETS:
        assert ST.criteria(name, data)                                            # rechnet (die Werte sind synthetisch)


def test_unpaid_penalty_and_noise_sections_are_reduced(built):
    data = R.load_results(built)
    assert set(data["_ap0_c_unbezahlte_pausen"]) == {"basis_45min_mit_fenster", "kein_fenster_45min", "kein_fenster_20min", "kein_fenster_90min"}
    pen = data["_ap0_d_verspaetungsstrafe"]
    assert set(pen) == {"20", "40", "80"} and all(math.isfinite(v["I"]["mean"]) for v in pen.values())
    noise = data["_ap0_b_suchrauschen"]
    assert set(noise) == {"live10", "live10_kein_fenster", "gepoolt"} and noise["gepoolt"]["n"] == 24
    assert noise["live10"]["best_of_6"]["gap"]["max"] >= 0.0
