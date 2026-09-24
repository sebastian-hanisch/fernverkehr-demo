"""dump_sweep.py (aus messreihe_fernverkehr, unverändert) - aggregiert raw_<config>.jsonl -> sweep_data.json (+ Textbericht sweep_report.txt).

Alle Vergleiche gepaart je Instanz. Angaben: Mittel +- Standardfehler (SE), Median und Quartile, Anteil der Instanzen mit
Vorzeichen. Interaktionsterm I_FE = (C_FE - C_0) - (C_F - C_0) - (C_E - C_0) = C_FE - C_F - C_E + C_0 (I < 0: die Kombination
ist billiger als die Summe der Einzelkosten, also SUB-additiv). "fix" = dieselben regelfreien Basistouren unter den Regeln
nachbewertet (kein Neuplanen), "opt" = Tourensuche mit dem jeweiligen Evaluator (Touren passen sich an).
"""

from __future__ import annotations

import json
import math
import os
import statistics as st
import sys

sys.dont_write_bytecode = True
from dataclasses import replace  # noqa: E402
from sweep import BASE, CONFIGS, HERE, load_raw  # noqa: E402

CELLS8 = ["---", "F--", "-E-", "FE-", "--S", "F-S", "-ES", "FES"]


def ms(xs):
    n = len(xs)
    if n == 0:
        return dict(n=0)
    m = sum(xs) / n
    sd = st.stdev(xs) if n > 1 else 0.0
    q = st.quantiles(xs, n=4) if n >= 2 else [m, m, m]
    return dict(n=n, mean=m, se=sd / math.sqrt(n) if n > 1 else 0.0, median=st.median(xs), q1=q[0], q3=q[2],
                neg_share=sum(1 for x in xs if x < -1e-9) / n, pos_share=sum(1 for x in xs if x > 1e-9) / n)


def fmt(d, unit="", digits=1):
    if not d or d.get("n", 0) == 0:
        return "-"
    return f"{d['mean']:.{digits}f} +- {d['se']:.{digits}f}{unit}"


def alias(cells: dict, name: str):
    """S ohne F wirkt nicht -> --S == ---, -ES == -E-."""
    if name in cells:
        return cells[name]
    if name == "--S":
        return cells["---"]
    if name == "-ES":
        return cells["-E-"]
    return None


NEW_PREFIX = ("live10", "unbezahlt_", "strafe")          # AP 0 (2026-09-24): nur diese Konfigurationen bekommen die Zusatzfelder


def analyse(name: str, recs: list[dict], label: str | None = None) -> dict:
    n, K, tw, over, combos, _ = CONFIGS[name]
    have = [c for c in ("---", "F--", "-E-", "FE-", "F-S", "FES") if c in recs[0]["cells"]]
    ok = [r for r in recs if all(r["cells"][c]["feasible"] and r["cells"][c]["re_total"] is not None for c in have)]
    out = dict(config=label or name, n=n, K=K, tw_share=tw[0], tw_width_h=tw[1], overrides=over, instances=len(recs),
               used=len(ok), excluded=len(recs) - len(ok), cells={}, interaction={}, mechanism={})
    if name.startswith(NEW_PREFIX) and label is None:
        okset = {r["seed"] for r in ok}
        out["excluded_detail"] = [dict(seed=r["seed"],
                                       grund=("Suche fand keine zulaessige Loesung in mind. einer Zelle" if any(not r["cells"][c]["feasible"] for c in have)
                                              else "regelfreie Basistouren unter E nicht fahrbar (Nachbewertung), Zellen selbst zulaessig"))
                                  for r in recs if r["seed"] not in okset]
        out["seeds_used"] = sorted(okset)
    if not ok:
        return out
    base = [r["cells"]["---"]["total"] for r in ok]
    base_o = [r["cells"]["---"]["oper"] for r in ok]
    out["base_total"] = ms(base)
    out["base_oper"] = ms(base_o)
    out["tw_count"] = ms([r["tw_count"] for r in ok])
    for c in have:
        cell = {}
        for key in ("total", "oper", "late_cost", "late_min", "late_n", "km", "span_min", "driver_h", "idle_min", "wait_min",
                    "nights", "breaks", "breaks_at_charger", "charges", "charge_km", "charge_min_plain", "free_charge_min",
                    "rests_at_charger", "swaps", "used", "n_eval", "re_total"):
            cell[key] = ms([r["cells"][c][key] for r in ok])
        cell["extra_pct_total"] = ms([100.0 * (r["cells"][c]["total"] - r["cells"]["---"]["total"]) / r["cells"]["---"]["total"] for r in ok])
        cell["extra_pct_oper"] = ms([100.0 * (r["cells"][c]["oper"] - r["cells"]["---"]["oper"]) / r["cells"]["---"]["oper"] for r in ok])
        cell["extra_eur_total"] = ms([r["cells"][c]["total"] - r["cells"]["---"]["total"] for r in ok])
        cell["extra_pct_fix"] = ms([100.0 * (r["cells"][c]["re_total"] - r["cells"]["---"]["total"]) / r["cells"]["---"]["total"] for r in ok])
        out["cells"][c] = cell

    def inter(key, src="opt"):
        """Interaktion F x E (und S-Effekte) fuer Kennzahl key ('total' oder 'oper'); src 'opt' oder 'fix'."""
        def val(r, c):
            cc = r["cells"][c]
            return cc["re_total"] if (src == "fix" and key == "total") else cc[key]
        res = {}
        rows = []
        for r in ok:
            b0 = val(r, "---") if src == "opt" else r["cells"]["---"][key]
            F_, E_, FE_ = val(r, "F--"), val(r, "-E-"), val(r, "FE-")
            rows.append(dict(base=b0, dF=F_ - b0, dE=E_ - b0, dFE=FE_ - b0, I=FE_ - F_ - E_ + b0))
        for k in ("dF", "dE", "dFE", "I"):
            res[k + "_eur"] = ms([x[k] for x in rows])
            res[k + "_pct"] = ms([100.0 * x[k] / x["base"] for x in rows])
        sum_single = sum(x["dF"] + x["dE"] for x in rows)
        res["ratio_of_means"] = (sum(x["dFE"] for x in rows) / sum_single) if abs(sum_single) > 1e-9 else None
        return res

    out["interaction"]["opt_total"] = inter("total", "opt")
    out["interaction"]["opt_oper"] = inter("oper", "opt")
    # Nachbewertung fester Basistouren: F, E, FE mit re_total
    rows = []
    for r in ok:
        c = r["cells"]
        b0 = c["---"]["total"]
        rows.append(dict(base=b0, dF=c["F--"]["re_total"] - b0, dE=c["-E-"]["re_total"] - b0, dFE=c["FE-"]["re_total"] - b0))
        rows[-1]["I"] = rows[-1]["dFE"] - rows[-1]["dF"] - rows[-1]["dE"]
    fix = {}
    for k in ("dF", "dE", "dFE", "I"):
        fix[k + "_eur"] = ms([x[k] for x in rows])
        fix[k + "_pct"] = ms([100.0 * x[k] / x["base"] for x in rows])
    out["interaction"]["fix_total"] = fix
    # Anpassungsgewinn der Suche: Nachbewertung minus neu optimierte Kosten (in % der Basis)
    out["adapt_gain_pct"] = {c: ms([100.0 * (r["cells"][c]["re_total"] - r["cells"][c]["total"]) / r["cells"]["---"]["total"] for r in ok])
                             for c in have if c != "---"}

    # Stafette
    if "F-S" in have:
        s = {}
        rows = []
        for r in ok:
            c = r["cells"]
            row = dict(base=c["---"]["total"], dS_F=c["F-S"]["total"] - c["F--"]["total"])
            if "FES" in c:
                row["dS_FE"] = c["FES"]["total"] - c["FE-"]["total"]
                row["I_SE"] = row["dS_FE"] - row["dS_F"]
            rows.append(row)
        for k in rows[0]:
            if k == "base":
                continue
            s[k + "_eur"] = ms([x[k] for x in rows])
            s[k + "_pct"] = ms([100.0 * x[k] / x["base"] for x in rows])
        s["used_F"] = sum(1 for r in ok if r["cells"]["F-S"]["swaps"] > 0) / len(ok)
        if "FES" in have:
            s["used_FE"] = sum(1 for r in ok if r["cells"]["FES"]["swaps"] > 0) / len(ok)
        s["nights_saved_F"] = ms([r["cells"]["F--"]["nights"] - r["cells"]["F-S"]["nights"] for r in ok])
        if "FES" in have:
            s["nights_saved_FE"] = ms([r["cells"]["FE-"]["nights"] - r["cells"]["FES"]["nights"] for r in ok])
        out["interaction"]["stafette"] = s

    # Kostenkomponenten: Interaktion je Komponente (neu geplant). total = km + Fahrer + Fahrzeug + Naechte + Verspaetung + Rest(Stafette)
    cfgc = replace(BASE, **over)

    def comps(cell):
        km = cfgc.c_km * cell["km"]
        drv = cfgc.c_drv * cell["driver_h"]
        veh = cfgc.c_veh * cell["span_min"] / 60.0
        ngt = cfgc.c_night * cell["nights"]
        late = cell["late_cost"]
        other = cell["total"] - km - drv - veh - ngt - late
        return dict(km=km, fahrer=drv, fahrzeug=veh, naechte=ngt, verspaetung=late, stafette=other)

    cmp_i = {}
    rows = []
    for r in ok:
        c0, cF, cE, cFE = (comps(r["cells"][x]) for x in ("---", "F--", "-E-", "FE-"))
        rows.append({k: cFE[k] - cF[k] - cE[k] + c0[k] for k in c0})
    for k in rows[0]:
        cmp_i[k] = ms([x[k] for x in rows])
    out["interaction"]["components_FE"] = cmp_i
    cmp_d = {}
    for cell_name in ("F--", "-E-", "FE-") + (("F-S", "FES") if "F-S" in have else ()):
        rows = []
        for r in ok:
            c0, cc = comps(r["cells"]["---"]), comps(r["cells"][cell_name])
            rows.append({k: cc[k] - c0[k] for k in c0})
        cmp_d[cell_name] = {k: ms([x[k] for x in rows]) for k in rows[0]}
    out["interaction"]["components_delta"] = cmp_d

    # Mechanismus in der FE-Zelle
    fe = [r["cells"]["FE-"] for r in ok]
    e_only = [r["cells"]["-E-"] for r in ok]
    f_only = [r["cells"]["F--"] for r in ok]
    mech = dict(
        breaks_total=ms([c["breaks"] for c in fe]),
        breaks_at_charger=ms([c["breaks_at_charger"] for c in fe]),
        share_breaks_at_charger=ms([100.0 * c["breaks_at_charger"] / c["breaks"] for c in fe if c["breaks"] > 0]),
        charges_FE=ms([c["charges"] for c in fe]),
        charges_E=ms([c["charges"] for c in e_only]),
        free_charge_min_FE=ms([c["free_charge_min"] for c in fe]),
        rests_at_charger_FE=ms([c["rests_at_charger"] for c in fe]),
        nights_FE=ms([c["nights"] for c in fe]),
        nights_F=ms([c["nights"] for c in f_only]),
        km_FE_minus_F=ms([a["km"] - b["km"] for a, b in zip(fe, f_only)]),
        km_E_minus_base=ms([a["km"] - r["cells"]["---"]["km"] for a, r in zip(e_only, ok)]),
        idle_h_F=ms([c["idle_min"] / 60.0 for c in f_only]),
        idle_h_E=ms([c["idle_min"] / 60.0 for c in e_only]),
        idle_h_FE=ms([c["idle_min"] / 60.0 for c in fe]),
        idle_h_base=ms([r["cells"]["---"]["idle_min"] / 60.0 for r in ok]),
    )
    out["mechanism"] = mech
    return out


def report_lines(a: dict) -> list[str]:
    L = []
    if not a.get("used"):
        return [f"== {a['config']}: keine auswertbaren Instanzen"]
    L.append(f"== {a['config']}: n={a['n']} K={a['K']} Fenster={a['tw_share']:.0%}/{a['tw_width_h']:.0f} h {a['overrides'] or ''} "
             f"Instanzen {a['used']} (ausgeschlossen {a['excluded']}), Basiskosten {fmt(a['base_total'], ' EUR', 0)}")
    L.append("  Zelle | Mehrkosten % (gesamt) | Median [Q1;Q3] | Mehrkosten % (Betrieb ohne Verspaetung) | Verspaetung h | "
             "Stillstand h | Naechte | Pausen | Ladestopps | km | fix-Nachbew. %")
    for c, cell in a["cells"].items():
        e = cell["extra_pct_total"]
        L.append(f"  {c} | {fmt(e, ' %')} | {e['median']:.1f} [{e['q1']:.1f};{e['q3']:.1f}] | {fmt(cell['extra_pct_oper'], ' %')} | "
                 f"{cell['late_min']['mean'] / 60:.1f} | {cell['idle_min']['mean'] / 60:.1f} | {cell['nights']['mean']:.2f} | "
                 f"{cell['breaks']['mean']:.2f} | {cell['charges']['mean']:.2f} | {cell['km']['mean']:.0f} | {fmt(cell['extra_pct_fix'], ' %')}")
    for key, title in (("opt_total", "Interaktion F x E (neu geplant, Gesamtkosten)"),
                       ("opt_oper", "Interaktion F x E (neu geplant, Betrieb ohne Verspaetung)"),
                       ("fix_total", "Interaktion F x E (feste Basistouren nachbewertet)")):
        i = a["interaction"][key]
        L.append(f"  {title}: dF {fmt(i['dF_pct'], ' %')}, dE {fmt(i['dE_pct'], ' %')}, dFE {fmt(i['dFE_pct'], ' %')}, "
                 f"I = {fmt(i['I_pct'], ' %')} ({fmt(i['I_eur'], ' EUR', 0)}), Median I {i['I_pct']['median']:.2f} %, "
                 f"I<0 in {100 * i['I_pct']['neg_share']:.0f} % der Instanzen")
    if "stafette" in a["interaction"]:
        s = a["interaction"]["stafette"]
        L.append(f"  Stafette: dS|F {fmt(s['dS_F_eur'], ' EUR', 0)} ({fmt(s['dS_F_pct'], ' %')}), genutzt in {100 * s['used_F']:.0f} % "
                 f"(Naechte gespart {fmt(s['nights_saved_F'], '', 2)})"
                 + (f"; dS|FE {fmt(s['dS_FE_eur'], ' EUR', 0)} ({fmt(s['dS_FE_pct'], ' %')}), genutzt {100 * s['used_FE']:.0f} %, "
                    f"I_SE {fmt(s['I_SE_eur'], ' EUR', 0)}" if "dS_FE_eur" in s else ""))
    ci = a["interaction"]["components_FE"]
    L.append("  Interaktion F x E je Kostenkomponente (EUR, neu geplant): "
             + ", ".join(f"{k} {fmt(v, '', 0)}" for k, v in ci.items()))
    cd = a["interaction"]["components_delta"]
    L.append("  Mehrkosten je Komponente gegen ---  (EUR): "
             + " | ".join(f"{c}: " + ", ".join(f"{k} {v['mean']:.0f}" for k, v in d.items()) for c, d in cd.items()))
    m = a["mechanism"]
    L.append(f"  Mechanismus FE: Pausen {m['breaks_total']['mean']:.2f}, davon an Ladesaeule {m['breaks_at_charger']['mean']:.2f} "
             f"({m['share_breaks_at_charger'].get('mean', float('nan')):.0f} %), Ladestopps FE {m['charges_FE']['mean']:.2f} vs E {m['charges_E']['mean']:.2f}, "
             f"freie Lademinuten {m['free_charge_min_FE']['mean']:.0f}, Tagesruhen an Saeule {m['rests_at_charger_FE']['mean']:.2f}, "
             f"Naechte FE {m['nights_FE']['mean']:.2f} vs F {m['nights_F']['mean']:.2f}")
    return L


def _rows(recs, have=("---", "F--", "-E-", "FE-")):
    """Je Instanz: dF, dE, dFE, I in % der Basis (neu geplant, Gesamtkosten) und Betriebs-I; nur Instanzen mit allen Zellen zulaessig."""
    out = {}
    for r in recs:
        c = r["cells"]
        if not all(c[x]["feasible"] and c[x]["re_total"] is not None for x in have):
            continue
        b0 = c["---"]["total"]
        F_, E_, FE_ = c["F--"]["total"], c["-E-"]["total"], c["FE-"]["total"]
        bo = c["---"]["oper"]
        out[r["seed"]] = dict(dF=100 * (F_ - b0) / b0, dE=100 * (E_ - b0) / b0, dFE=100 * (FE_ - b0) / b0,
                              I=100 * (FE_ - F_ - E_ + b0) / b0, base=b0,
                              Io=100 * (c["FE-"]["oper"] - c["F--"]["oper"] - c["-E-"]["oper"] + bo) / bo,
                              I_eur=FE_ - F_ - E_ + b0)
    return out


def paired(a_rows, b_rows, keys=("dF", "dE", "dFE", "I", "Io")):
    """Gepaarte Differenz b - a je Instanz (gemeinsame Seeds)."""
    common = sorted(set(a_rows) & set(b_rows))
    return dict(n=len(common), **{k: ms([b_rows[x][k] - a_rows[x][k] for x in common]) for k in keys})


def pct(xs, q):
    xs = sorted(xs)
    if not xs:
        return float("nan")
    k = (len(xs) - 1) * q
    lo, hi = int(math.floor(k)), int(math.ceil(k))
    return xs[lo] + (xs[hi] - xs[lo]) * (k - lo)


def dist(xs):
    return dict(n=len(xs), mean=sum(xs) / len(xs), median=pct(xs, 0.5), p90=pct(xs, 0.9), p95=pct(xs, 0.95), max=max(xs))


def ap0_extras(data: dict) -> dict:
    ex = {}
    # (c) bezahlt vs. unbezahlt, gepaart auf denselben Instanzen
    cmp_c = {}
    for tag, paid, unp in (("basis_45min_mit_fenster", "basis", "unbezahlt_basis"),
                           ("kein_fenster_45min", "kein_fenster", "unbezahlt_kein_fenster"),
                           ("kein_fenster_20min", "kein_fenster_lade20", "unbezahlt_kein_fenster_lade20"),
                           ("kein_fenster_90min", "kein_fenster_lade90", "unbezahlt_kein_fenster_lade90")):
        rp, ru = load_raw(paid), load_raw(unp)
        if not rp or not ru:
            continue
        A, B = _rows(rp), _rows(ru)
        pr = paired(A, B)
        common = sorted(set(A) & set(B))
        cmp_c[tag] = dict(paid=paid, unpaid=unp, n=pr["n"], diff_unpaid_minus_paid=pr,
                          I_paid=ms([A[x]["I"] for x in common]), I_unpaid=ms([B[x]["I"] for x in common]),
                          dF_paid=ms([A[x]["dF"] for x in common]), dF_unpaid=ms([B[x]["dF"] for x in common]),
                          dE_paid=ms([A[x]["dE"] for x in common]), dE_unpaid=ms([B[x]["dE"] for x in common]),
                          dFE_paid=ms([A[x]["dFE"] for x in common]), dFE_unpaid=ms([B[x]["dFE"] for x in common]),
                          neg_share_paid=sum(1 for x in common if A[x]["I"] < 0) / max(1, len(common)),
                          neg_share_unpaid=sum(1 for x in common if B[x]["I"] < 0) / max(1, len(common)),
                          sign_flip_share=sum(1 for x in common if (A[x]["I"] < 0) != (B[x]["I"] < 0)) / max(1, len(common)))
    ex["_ap0_c_unbezahlte_pausen"] = cmp_c
    # (d) Verspaetungsstrafe 20/40/80 auf denselben Instanzen; 40 EUR = Konfiguration basis, eingeschraenkt auf die Seeds von strafe20/80
    cmp_d = {}
    r20, r80, rb = load_raw("strafe20"), load_raw("strafe80"), load_raw("basis")
    if r20 and r80 and rb:
        seeds = {r["seed"] for r in r20} & {r["seed"] for r in r80}
        for tag, recs, cname in (("20", r20, "strafe20"), ("40", rb, "basis"), ("80", r80, "strafe80")):
            sub = [r for r in recs if r["seed"] in seeds]
            rows = _rows(sub)
            a = analyse(cname, sub, label=f"strafe{tag}_gleiche_instanzen")
            cmp_d[tag] = dict(n=len(rows), dF=ms([x["dF"] for x in rows.values()]), dE=ms([x["dE"] for x in rows.values()]),
                              dFE=ms([x["dFE"] for x in rows.values()]), I=ms([x["I"] for x in rows.values()]),
                              I_eur=ms([x["I_eur"] for x in rows.values()]), I_betrieb=ms([x["Io"] for x in rows.values()]),
                              neg_share=sum(1 for x in rows.values() if x["I"] < 0) / len(rows),
                              I_komponenten_eur=a["interaction"]["components_FE"], late_h_F=a["cells"]["F--"]["late_min"]["mean"] / 60,
                              late_h_FE=a["cells"]["FE-"]["late_min"]["mean"] / 60, base_total=a["base_total"])
    ex["_ap0_d_verspaetungsstrafe"] = cmp_d
    # (b) Suchrauschen auf Live-Groesse
    path = os.path.join(HERE, "raw_noise_live.jsonl")
    noise = {}
    if os.path.exists(path):
        recs = [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]
        for name in ("live10", "live10_kein_fenster"):
            rr = [r for r in recs if r["config"] == name]
            if not rr:
                continue
            cells = ["---", "F--", "-E-", "FE-"]
            d = {"n_instanzen": len(rr), "zellen": {}}
            for c in cells:
                xs = [100 * abs(r["a"][c] - r["b"][c]) / r["a"]["---"] for r in rr]
                d["zellen"][c] = dict(abs_diff_pct_der_basis=dist(xs), identisch=sum(1 for x in xs if x < 1e-9))

            def I(r, t):
                v = r[t]
                return 100 * (v["FE-"] - v["F--"] - v["-E-"] + v["---"]) / r["a"]["---"]

            dI = [abs(I(r, "a") - I(r, "b")) for r in rr]
            d["abs_dI_pct_der_basis"] = dist(dI)
            d["abs_dI_identisch"] = sum(1 for x in dI if x < 1e-9)
            pooled = [I(r, "a") for r in rr] + [I(r, "b") for r in rr]
            d["I_pooled"] = ms(pooled)
            d["I_pooled_dist"] = dist(pooled)
            p95 = d["abs_dI_pct_der_basis"]["p95"]
            # Schwellenvorschlaege: p95 der Rausch-Differenz zweier Laeufe, p95/sqrt(2) (Rauschen EINES Laufs, Normalannahme), Max
            cand = {"p95_dI": p95, "p95_dI_durch_wurzel2": p95 / math.sqrt(2), "max_dI": d["abs_dI_pct_der_basis"]["max"],
                    "fix_0.5": 0.5, "fix_1.0": 1.0, "fix_2.0": 2.0}
            d["schwellen"] = {}
            big = _rows(load_raw(name))                        # Einzelinstanz-I aus der grossen Messreihe (60 Inst., ein Lauf je Instanz)
            for k, thr in cand.items():
                d["schwellen"][k] = dict(
                    schwelle_pct=thr,
                    rausch_set=dict(billiger=sum(1 for x in pooled if x < -thr) / len(pooled), additiv=sum(1 for x in pooled if abs(x) <= thr) / len(pooled),
                                    teurer=sum(1 for x in pooled if x > thr) / len(pooled)),
                    messreihe=dict(n=len(big), billiger=sum(1 for v in big.values() if v["I"] < -thr) / max(1, len(big)),
                                   additiv=sum(1 for v in big.values() if abs(v["I"]) <= thr) / max(1, len(big)),
                                   teurer=sum(1 for v in big.values() if v["I"] > thr) / max(1, len(big))))
            # Klassifikations-Kippen: wie oft haengt die Meldung (billiger / additiv / teurer) vom Such-Seed ab?
            def state(v, thr):
                return -1 if v < -thr else (1 if v > thr else 0)
            d["flip_rate"] = {str(t): sum(1 for r in rr if state(I(r, "a"), t) != state(I(r, "b"), t)) / len(rr)
                              for t in (0.25, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0)}
            # Best-of-6-Seeds (a, b und vier weitere): Abstand der Standardsuche zum besten gefundenen Wert
            extp = os.path.join(HERE, "raw_noise_live_ext.jsonl")
            if os.path.exists(extp):
                E = {(r["config"], r["seed"]): r for r in (json.loads(l) for l in open(extp, encoding="utf-8") if l.strip())}
                gaps, dIs, shifted, ib = [], [], 0, []
                for r in rr:
                    e = E.get((name, r["seed"]))
                    if e is None:
                        continue
                    runs = [r["a"], r["b"], e["c"], e["d"], e["e"], e["f"]]
                    best = {c: min(x[c] for x in runs) for c in cells}
                    base = r["a"]["---"]
                    Ibest = 100 * (best["FE-"] - best["F--"] - best["-E-"] + best["---"]) / base
                    ib.append(Ibest)
                    gaps.append(100 * (r["a"]["FE-"] - best["FE-"]) / base)
                    dIs.append(I(r, "a") - Ibest)
                    shifted += 1 if abs(dIs[-1]) > 1e-9 else 0
                if gaps:
                    d["best_of_6"] = dict(n=len(gaps), gap_FE_standard_gegen_best_pct_der_basis=dist(gaps), I_standard_minus_I_best=dist(dIs),
                                          I_standard_ueberschaetzt_bei=shifted, I_best=ms(ib), I_standard=ms([I(r, "a") for r in rr]),
                                          flip_standard_vs_best={str(t): sum(1 for x, y in zip([I(r, "a") for r in rr if (name, r["seed"]) in E], ib) if state(x, t) != state(y, t)) / len(ib)
                                                                 for t in (0.5, 1.0, 2.0, 3.0)})
            noise[name] = d
    # Gepoolt ueber beide Konfigurationen (mittlere Fenster und ohne Fenster, zusammen 60 Instanzen): Schwellenvorschlag
    if noise and os.path.exists(os.path.join(HERE, "raw_noise_live_ext.jsonl")):
        ext = {(r["config"], r["seed"]): r for r in (json.loads(l) for l in open(os.path.join(HERE, "raw_noise_live_ext.jsonl"), encoding="utf-8") if l.strip())}
        allr = [r for r in recs if r["config"] in noise and (r["config"], r["seed"]) in ext]

        def Ic(v, base):
            return 100 * (v["FE-"] - v["F--"] - v["-E-"] + v["---"]) / base

        def stt(v, t):
            return -1 if v < -t else (1 if v > t else 0)

        dd, fl = [], {t: [0, 0, 0] for t in (1.0, 1.5, 2.0, 2.5, 3.0, 4.0)}
        for r in allr:
            e, b = ext[(r["config"], r["seed"])], r["a"]["---"]
            runs = [r["a"], r["b"], e["c"], e["d"], e["e"], e["f"]]
            Is = [Ic(x, b) for x in runs]
            best = {c: min(x[c] for x in runs) for c in r["a"]}
            Ib = Ic(best, b)
            dd.append(abs(Is[0] - Is[1]))
            for t in fl:
                fl[t][0] += stt(Is[0], t) != stt(Is[1], t)
                fl[t][1] += stt(Is[0], t) != stt(Ib, t)
                fl[t][2] += len({stt(v, t) for v in Is}) > 1
        noise["gepoolt_beide_konfigurationen"] = dict(
            n=len(allr), abs_dI_pct_der_basis=dist(dd), nicht_null=sum(1 for x in dd if x > 1e-9),
            kippen_von_n={str(t): dict(seed1_vs_seed2=v[0], standard_vs_best_von_6=v[1], irgendein_paar_von_6=v[2]) for t, v in fl.items()})
    ex["_ap0_b_suchrauschen_live10"] = noise
    return ex


def extra_lines(ex: dict) -> list[str]:
    L = ["", "== AP 0 (2026-09-24) Zusatzauswertungen"]
    for tag, d in ex.get("_ap0_c_unbezahlte_pausen", {}).items():
        df = d["diff_unpaid_minus_paid"]
        L.append(f"  (c) {tag}: n={d['n']}, F {fmt(d['dF_paid'], ' %')} -> {fmt(d['dF_unpaid'], ' %')}, E {fmt(d['dE_paid'], ' %')} -> {fmt(d['dE_unpaid'], ' %')}, "
                 f"FE {fmt(d['dFE_paid'], ' %')} -> {fmt(d['dFE_unpaid'], ' %')}, "
                 f"I {fmt(d['I_paid'], ' %', 2)} -> {fmt(d['I_unpaid'], ' %', 2)} (gepaarte Differenz {fmt(df['I'], ' %', 2)}), "
                 f"I<0: {100 * d['neg_share_paid']:.0f} % -> {100 * d['neg_share_unpaid']:.0f} % der Instanzen, Vorzeichen je Instanz gekippt bei {100 * d['sign_flip_share']:.0f} %")
    for tag, d in ex.get("_ap0_d_verspaetungsstrafe", {}).items():
        L.append(f"  (d) Strafe {tag} EUR/h: n={d['n']}, Basis {fmt(d['base_total'], ' EUR', 0)}, F {fmt(d['dF'], ' %')}, E {fmt(d['dE'], ' %')}, FE {fmt(d['dFE'], ' %')}, "
                 f"I {fmt(d['I'], ' %', 2)} ({fmt(d['I_eur'], ' EUR', 0)}), I Betrieb {fmt(d['I_betrieb'], ' %', 2)}, I<0 {100 * d['neg_share']:.0f} %, "
                 f"Verspaetung F {d['late_h_F']:.1f} h / FE {d['late_h_FE']:.1f} h")
    for name, d in ex.get("_ap0_b_suchrauschen_live10", {}).items():
        if name == "gepoolt_beide_konfigurationen":
            x = d["abs_dI_pct_der_basis"]
            L.append(f"  (b) gepoolt beide Konfigurationen (n={d['n']}): |I1 - I2| in % der Basis: von 0 verschieden bei {d['nicht_null']}, Median {x['median']:.3f}, P90 {x['p90']:.3f}, "
                     f"P95 {x['p95']:.3f}, Max {x['max']:.2f}; Kippen der Meldung (Anzahl von {d['n']}) je Schwelle: "
                     + "; ".join(f"{t} %: Seed1/Seed2 {v['seed1_vs_seed2']}, Standard/Best-von-6 {v['standard_vs_best_von_6']}, irgendein Paar {v['irgendein_paar_von_6']}" for t, v in d["kippen_von_n"].items()))
            continue
        L.append(f"  (b) Suchrauschen {name}: {d['n_instanzen']} Instanzen x 2 Such-Seeds")
        for c, z in d["zellen"].items():
            x = z["abs_diff_pct_der_basis"]
            L.append(f"      Zelle {c}: |Kosten1-Kosten2| in % der Basis: identisch {z['identisch']}/{x['n']}, Median {x['median']:.3f}, P90 {x['p90']:.3f}, P95 {x['p95']:.3f}, Max {x['max']:.2f}")
        x = d["abs_dI_pct_der_basis"]
        L.append(f"      |I1 - I2| in % der Basis: identisch {d['abs_dI_identisch']}/{x['n']}, Median {x['median']:.3f}, P90 {x['p90']:.3f}, P95 {x['p95']:.3f}, Max {x['max']:.2f}; "
                 f"I ({2 * d['n_instanzen']} Werte) {fmt(d['I_pooled'], ' %', 2)}")
        L.append("      Kippen der Meldung zwischen Seed 1 und 2 (Anteil der Instanzen) je Schwelle: "
                 + ", ".join(f"{k} %: {100 * v:.0f} %" for k, v in d["flip_rate"].items()))
        if "best_of_6" in d:
            b = d["best_of_6"]
            g, di = b["gap_FE_standard_gegen_best_pct_der_basis"], b["I_standard_minus_I_best"]
            L.append(f"      Best-of-6-Seeds (n={b['n']}): FE-Kosten Standard minus Best in % der Basis: Mittel {g['mean']:.3f}, Median {g['median']:.3f}, P90 {g['p90']:.3f}, P95 {g['p95']:.3f}, Max {g['max']:.2f}; "
                     f"I Standard {fmt(b['I_standard'], ' %', 2)} gegen I Best {fmt(b['I_best'], ' %', 2)}; Standard zu hoch bei {b['I_standard_ueberschaetzt_bei']} Instanzen; "
                     f"Kippen Standard vs Best: " + ", ".join(f"{k} %: {100 * v:.0f} %" for k, v in b["flip_standard_vs_best"].items()))
        for k, v in d["schwellen"].items():
            rs, mr = v["rausch_set"], v["messreihe"]
            L.append(f"      Schwelle {k} = {v['schwelle_pct']:.2f} %: Rausch-Set billiger {100 * rs['billiger']:.0f} % / additiv {100 * rs['additiv']:.0f} % / teurer {100 * rs['teurer']:.0f} %; "
                     f"Messreihe (n={mr['n']}) billiger {100 * mr['billiger']:.0f} % / additiv {100 * mr['additiv']:.0f} % / teurer {100 * mr['teurer']:.0f} %")
    return L


def main():
    data = {}
    lines = []
    for name in CONFIGS:
        recs = load_raw(name)
        if not recs:
            continue
        a = analyse(name, recs)
        data[name] = a
        lines += report_lines(a) + [""]
    # Querschnitt: Interaktion je Konfiguration
    lines.append("== Querschnitt F x E (neu geplant, Gesamtkosten in % der Basiskosten; I<0 = sub-additiv)")
    lines.append("  Konfiguration | n | dF | dE | dFE | I +- SE | Median I | Anteil I<0 | I Betrieb (ohne Verspaetung) | I fix")
    for name, a in data.items():
        if not a.get("used"):
            continue
        i = a["interaction"]["opt_total"]
        io = a["interaction"]["opt_oper"]
        ifx = a["interaction"]["fix_total"]
        lines.append(f"  {name} | {a['used']} | {i['dF_pct']['mean']:.1f} | {i['dE_pct']['mean']:.1f} | {i['dFE_pct']['mean']:.1f} | "
                     f"{fmt(i['I_pct'], '', 2)} | {i['I_pct']['median']:.2f} | {100 * i['I_pct']['neg_share']:.0f} % | "
                     f"{fmt(io['I_pct'], '', 2)} | {fmt(ifx['I_pct'], '', 2)}")
    extra = ap0_extras(data)
    lines += extra_lines(extra)
    data.update(extra)
    with open(os.path.join(HERE, "sweep_data.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1)
    with open(os.path.join(HERE, "sweep_report.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
