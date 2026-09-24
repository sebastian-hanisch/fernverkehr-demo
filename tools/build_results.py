"""Erzeugt data/fv_results.json aus den Ausgaben der Messreihe (tools/sweep.py, tools/dump_sweep.py).

Aufruf:
    python tools/build_results.py [--sweep-data PFAD/sweep_data.json] [--raw-dir ORDNER] [--timing PFAD/timing_live.txt]

Standard: sweep_data.json und raw_*.jsonl liegen neben diesem Skript (dorthin schreiben sweep.py und dump_sweep.py). Die Datei
data/fv_results.json enthält nur Aggregate (Mittel, Standardfehler, Median, Quartile, Anteil I < 0, Kostenzerlegung, Mechanismus,
Anteile der Meldungszustände), keine Roh-Instanzdaten; die App liest sie zur Laufzeit und rechnet die Messreihe NIE live.

Schlüssel: dieselben Konfigurationsnamen wie in sweep.py (basis, kein_fenster, live10, unbezahlt_*, strafe*, ...), dazu
`_ap0_c_unbezahlte_pausen`, `_ap0_d_verspaetungsstrafe`, `_ap0_b_suchrauschen` (Zusammenfassung), `_timings` und `_meta`. Die Stafette-Konfigurationen und
`gross` sind nicht enthalten (die App zeigt sie nicht)."""
import argparse
import json
import math
import pathlib
import re
import sys

sys.dont_write_bytecode = True
HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT))

from sweep import CONFIGS  # noqa: E402

KEEP = ["basis", "kein_fenster", "lade20", "lade90", "kein_fenster_lade20", "kein_fenster_lade90", "reich300", "reich600",
        "fenster_locker", "fenster_eng", "fenster_regelbewusst", "fahrzeuge2", "fahrzeuge4",
        "live10", "live10_kein_fenster", "live10_kein_fenster_lade20", "live10_kein_fenster_lade90",
        "live10_reich300", "live10_reich400", "live10_reich600",
        "unbezahlt_basis", "unbezahlt_kein_fenster", "unbezahlt_kein_fenster_lade20", "unbezahlt_kein_fenster_lade90",
        "strafe20", "strafe80"]
CELLS = ("---", "F--", "-E-", "FE-")
THRESHOLD_PCT = 2.0
DIGITS = 4


def r(x):
    return round(x, DIGITS) if isinstance(x, float) else x


def stat(d):
    """Kennzahlen einer Stichprobe (ms() aus dump_sweep.py) in kompakter Form."""
    return {k: r(d[k]) for k in ("n", "mean", "se", "median", "q1", "q3", "neg_share")}


def mean_se(d):
    return {"mean": r(d["mean"]), "se": r(d["se"])}


def raw_rows(raw_dir, name):
    path = raw_dir / f"raw_{name}.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def usable(rows):
    """Instanzen, die in allen vier Zellen zulässig sind und deren Basistouren nachbewertbar waren (wie dump_sweep.analyse)."""
    return [x for x in rows if all(x["cells"][c]["feasible"] and x["cells"][c]["re_total"] is not None for c in CELLS)]


def interaction_pct(row):
    c = row["cells"]
    return 100.0 * (c["FE-"]["total"] - c["F--"]["total"] - c["-E-"]["total"] + c["---"]["total"]) / c["---"]["total"]


def state_shares(rows, thr=THRESHOLD_PCT):
    v = [interaction_pct(x) for x in rows]
    n = len(v)
    return dict(n=n, billiger=r(sum(x < -thr for x in v) / n), additiv=r(sum(abs(x) <= thr for x in v) / n),
                teurer=r(sum(x > thr for x in v) / n))


def reduce_series(name, a, raw_dir):
    n, K, (share, width, ref), over, combos, _ = CONFIGS[name]
    it = a["interaction"]
    out = dict(
        name=name, n=n, K=K, tw_share=share, tw_width_h=width, tw_ref=ref, overrides=over,
        instances=a["instances"], used=a["used"], excluded=a["excluded"], base_eur=mean_se(a["base_total"]),
        dF=stat(it["opt_total"]["dF_pct"]), dE=stat(it["opt_total"]["dE_pct"]), dFE=stat(it["opt_total"]["dFE_pct"]),
        I=stat(it["opt_total"]["I_pct"]), I_eur=stat(it["opt_total"]["I_eur"]),
        I_oper=stat(it["opt_oper"]["I_pct"]),
        fix={k: stat(it["fix_total"][k + "_pct"]) for k in ("dF", "dE", "dFE", "I")},
        comps_I={k: mean_se(v) for k, v in it["components_FE"].items() if k != "stafette"},
        comps_delta={cell: {k: r(v["mean"]) for k, v in d.items() if k != "stafette"} for cell, d in it["components_delta"].items()
                     if cell in CELLS},
        cells={c: dict(late_h=r(a["cells"][c]["late_min"]["mean"] / 60.0), nights=r(a["cells"][c]["nights"]["mean"]),
                       breaks=r(a["cells"][c]["breaks"]["mean"]), charges=r(a["cells"][c]["charges"]["mean"]),
                       km=r(a["cells"][c]["km"]["mean"]), idle_h=r(a["cells"][c]["idle_min"]["mean"] / 60.0))
               for c in CELLS},
        mechanism={k: mean_se(v) for k, v in a["mechanism"].items()
                   if k in ("share_breaks_at_charger", "breaks_total", "breaks_at_charger", "free_charge_min_FE",
                            "rests_at_charger_FE", "nights_FE", "nights_F", "charges_FE", "charges_E")},
    )
    if a.get("excluded_detail"):
        out["excluded_reasons"] = dict(
            suche_ohne_loesung=sum(1 for e in a["excluded_detail"] if e["grund"].startswith("Suche")),
            basistouren_unter_E_nicht_fahrbar=sum(1 for e in a["excluded_detail"] if e["grund"].startswith("regelfreie")))
    out["states"] = state_shares(usable(raw_rows(raw_dir, name)))
    return out


def reduce_penalty(d):
    return {k: dict(n=v["n"], dF=stat(v["dF"]), dE=stat(v["dE"]), dFE=stat(v["dFE"]), I=stat(v["I"]), I_eur=stat(v["I_eur"]),
                    I_oper=stat(v["I_betrieb"]), neg_share=r(v["neg_share"]), late_h_F=r(v["late_h_F"]), late_h_FE=r(v["late_h_FE"]))
            for k, v in d.items()}


def reduce_unpaid(d):
    return {k: dict(n=v["n"], paid=v["paid"], unpaid=v["unpaid"], I_paid=stat(v["I_paid"]), I_unpaid=stat(v["I_unpaid"]),
                    I_diff=stat(v["diff_unpaid_minus_paid"]["I"]), dF_paid=stat(v["dF_paid"]), dF_unpaid=stat(v["dF_unpaid"]),
                    dFE_paid=stat(v["dFE_paid"]), dFE_unpaid=stat(v["dFE_unpaid"]),
                    neg_share_paid=r(v["neg_share_paid"]), neg_share_unpaid=r(v["neg_share_unpaid"]))
            for k, v in d.items()}


def dist(d):
    return {k: r(d[k]) for k in ("n", "mean", "median", "p90", "p95", "max")}


def reduce_noise(d):
    out = {}
    for name in ("live10", "live10_kein_fenster"):
        z = d[name]
        b = z["best_of_6"]
        out[name] = dict(n=z["n_instanzen"], fe_identisch=z["zellen"]["FE-"]["identisch"],
                         andere_zellen_identisch={c: z["zellen"][c]["identisch"] for c in ("---", "F--", "-E-")},
                         abs_dI=dist(z["abs_dI_pct_der_basis"]), best_of_6=dict(
                             n=b["n"], gap=dist(b["gap_FE_standard_gegen_best_pct_der_basis"]),
                             standard_zu_hoch_bei=b["I_standard_ueberschaetzt_bei"], I_standard=stat(b["I_standard"]),
                             I_best=stat(b["I_best"])))
    g = d["gepoolt_beide_konfigurationen"]
    out["gepoolt"] = dict(n=g["n"], nicht_null=g["nicht_null"], abs_dI=dist(g["abs_dI_pct_der_basis"]),
                          kippen_bei_2_prozent=g["kippen_von_n"]["2.0"])
    return out


def parse_timing(path):
    """timing_live.txt: 'n=8 seed=10 inst 0.0s solve 1.0s | ...' -> {'8': [1.0, 1.1]} (Sekunden je Lauf)."""
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"n=(\d+) seed=(\d+) inst [\d.]+s solve ([\d.]+)s", line)
        if m:
            out.setdefault(m.group(1), []).append(float(m.group(3)))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sweep-data", default=str(HERE / "sweep_data.json"))
    ap.add_argument("--raw-dir", default=None)
    ap.add_argument("--timing", default=None)
    ap.add_argument("--out", default=str(ROOT / "data" / "fv_results.json"))
    args = ap.parse_args()
    sweep_data = pathlib.Path(args.sweep_data)
    raw_dir = pathlib.Path(args.raw_dir) if args.raw_dir else sweep_data.parent
    timing = pathlib.Path(args.timing) if args.timing else sweep_data.parent / "timing_live.txt"
    D = json.loads(sweep_data.read_text(encoding="utf-8"))

    out = {"_meta": dict(quelle="messreihe_fernverkehr (tools/sweep.py, tools/dump_sweep.py)", schwelle_pct=THRESHOLD_PCT,
                         se_faktor=2.0, zellen=list(CELLS),
                         hinweis="Aggregate der gepaarten Messreihen; I = C(F+E) - C(F) - C(E) + C(ohne) in % der regelfreien Kosten")}
    for name in KEEP:
        out[name] = reduce_series(name, D[name], raw_dir)
    out["_ap0_c_unbezahlte_pausen"] = reduce_unpaid(D["_ap0_c_unbezahlte_pausen"])
    out["_ap0_d_verspaetungsstrafe"] = reduce_penalty(D["_ap0_d_verspaetungsstrafe"])
    out["_ap0_b_suchrauschen"] = reduce_noise(D["_ap0_b_suchrauschen_live10"])
    out["_timings"] = dict(
        live_suche_s=parse_timing(timing) if timing.exists() else {},
        evaluator_ms_je_6_stopp_route=dict(aus=0.1, F=0.1, E=5.9, FE=186.0),
        messreihe_wanduhr_min=52, messreihe_kerne=16)
    # ein Schlüssel je Zeile, Werte kompakt: klein (Dateigröße) und trotzdem zeilenweise diff-bar
    NL = chr(10)
    body = f",{NL}".join(f"{json.dumps(k, ensure_ascii=False)}: {json.dumps(v, ensure_ascii=False, separators=(',', ':'))}"
                         for k, v in out.items())
    text = "{" + NL + body + NL + "}"
    pathlib.Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(f"geschrieben: {args.out} ({len(text) / 1024:.0f} KB, {len(KEEP)} Konfigurationen)")
    for name in KEEP[:3]:
        print(name, out[name]["I"], out[name]["states"])
    if not all(math.isfinite(x) for x in (out["basis"]["I"]["mean"],)):
        raise SystemExit("unerwartete Werte")


if __name__ == "__main__":
    main()
