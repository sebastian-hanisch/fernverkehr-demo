"""AppTest OHNE Ersatz der Live-Rechnung: die App rechnet wirklich (nur mit 6 bis 8 Kunden, damit es schnell bleibt; 10 und 12 Kunden
stehen in tests/test_live.py und in der Browser-Verifikation). Keine Wall-Clock-Assertions."""
import pathlib

import pytest
from streamlit.testing.v1 import AppTest

import fv_constants as C
import fv_live as LV
import fv_results as R

APP = str(pathlib.Path(__file__).resolve().parent.parent / "app.py")
DATA = R.load_results()


@pytest.fixture(autouse=True)
def clean_state():
    import streamlit as st
    st.cache_data.clear()
    yield


def fresh(**query):
    at = AppTest.from_file(APP, default_timeout=180)
    for k, v in query.items():
        at.query_params[k] = v
    at.run()
    assert not at.exception, at.exception
    return at


def metrics(at):
    return [(m.label, m.value) for m in at.metric[:4]]


def test_the_app_really_computes_the_live_instance_for_the_slider_values():
    at = fresh(n="7", lt="90", r="600", w="keine", seed="5")
    cap = next(c.value for c in at.caption if c.value.startswith("Live-Instanz:"))
    assert cap.startswith("Live-Instanz: 7 Kunden, 2 Lkw, davon 0 mit Zeitfenster (Zeitfenster keine), Ladezeit 90 min, Reichweite 600 km, Instanz Nr. 5")
    assert f"Seed {LV.nth_valid_seed(5, 7, 2, 600)}" in cap
    res = LV.solve_live(7, 90, 600, "keine", 5)
    x = R.interaction_from_costs({c: res["cells"][c]["total"] for c in C.CELLS})
    assert dict(metrics(at))["Wechselwirkung I"] == f"{x['I_pct']:+.1f} %".replace(".", ",")


def test_customer_count_is_not_a_dead_control():
    a, b = metrics(fresh(n="6")), metrics(fresh(n="7"))
    assert a != b


def test_the_number_of_customers_is_shown_in_the_map_and_the_halteliste():
    at = fresh(n="8")
    frames = [d.value for d in at.dataframe if "Ereignis" in d.value.columns]
    assert frames
    services = {o for f in frames for o in f[f["Ereignis"] == "Service"]["Ort"]}
    assert services and services <= {f"Kunde {c}" for c in range(1, 9)}
    assert any(c.value.startswith("Live-Instanz: 8 Kunden") for c in at.caption)


def test_a_real_layout_without_a_feasible_electric_solution_shows_the_explanation():
    at = fresh(n="6", r="300", w="keine", seed="10")
    warn = [w.value for w in at.warning if "keine zulässige Lösung" in w.value]
    assert warn and "Elektro (E), beides (F+E)" in warn[0] and "3 von 40 Lagen" in warn[0]
    assert [m[1] for m in metrics(at)] == ["–"] * 4 and at.get("download_button")


def test_cached_results_are_reused_for_the_same_setting():
    calls = []
    real = LV.solve_live
    LV.solve_live = lambda *a, **k: calls.append(a) or real(*a, **k)
    try:
        at = fresh(n="6")
        at.run()
        assert len(calls) == 1                                                             # zweiter Lauf: aus dem Zwischenspeicher
        at.select_slider(key="charge_slider").set_value(90).run()
        assert len(calls) == 2
        at.select_slider(key="charge_slider").set_value(45).run()
        assert len(calls) == 2                                                             # zurück: wieder aus dem Zwischenspeicher
    finally:
        LV.solve_live = real


def test_the_app_source_never_runs_the_measurement_series():
    src = pathlib.Path(APP).read_text(encoding="utf-8")
    for forbidden in ("sweep", "multiprocessing", "solve_all", "dump_sweep"):
        assert forbidden not in src, forbidden
