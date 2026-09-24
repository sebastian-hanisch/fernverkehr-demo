"""sweep.py (aus messreihe_fernverkehr, nur die Importe auf die fv_-Module umgestellt) - gepaarte Messreihen ueber die Schalter F (Fahrerregeln), E (Elektro), S (Stafette).

Aufruf:  python sweep.py <config|all|list> [N]      (schreibt raw_<config>.jsonl, setzt unterbrochene Laeufe fort)

Seed-Konvention (alles deterministisch, Wiederholungslauf == gleiche Zahlen):
  Instanz i einer Messreihe = i-ter GUELTIGER Seed s (aufsteigend ab 0; gueltig = jeder Kunde per Rundfahrt mit R=300
  erreichbar (ca. 20 % der Zufallslagen; R=250 ist mit 12 Saeulen auf 800x800 km praktisch nie machbar), also fuer alle Reichweiten der Sweeps loesbar). Geometrie/Bedarf: Random(s*1000+n); Fensterlage:
  Random(s*77+3); Referenztour fuer die Fenster: Suche mit Seed s*31+7; Tourensuche jeder Zelle: Seed s.
  Dieselben Instanzen (und dieselben Fensterziehungen) in allen Schalterkombinationen und ueber Sweeps hinweg.
"""

from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import replace
from multiprocessing import Pool

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))       # Projektwurzel mit den fv_-Modulen
from fv_evaluator import Ev, plan_stats  # noqa: E402
from fv_model import Cfg, INF, combo_name, is_feasible  # noqa: E402
from fv_search import make_geometry, make_instance, solve_all, total_cost  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = Cfg(max_rl=4)
RMIN = 300.0

C6 = [(0, 0, 0), (1, 0, 0), (0, 1, 0), (1, 1, 0), (1, 0, 1), (1, 1, 1)]     # 8 Kombinationen minus 2 Alias (S ohne F)
C4 = [(0, 0, 0), (1, 0, 0), (0, 1, 0), (1, 1, 0)]
C5S = C6                                                                      # Stafette-Konfigurationen: alle Zellen

CONFIGS = {
    # name: (n, K, (tw_share, tw_width_h, tw_ref), Cfg-Overrides, Kombinationen, Standard-N)
    "basis":               (18, 3, (0.6, 8.0, "plain"), {}, C6, 60),
    "kein_fenster":        (18, 3, (0.0, 8.0, "plain"), {}, C6, 60),
    "lade20":              (18, 3, (0.6, 8.0, "plain"), dict(t_typ=20.0), C4, 40),
    "lade90":              (18, 3, (0.6, 8.0, "plain"), dict(t_typ=90.0), C4, 40),
    "kein_fenster_lade20": (18, 3, (0.0, 8.0, "plain"), dict(t_typ=20.0), C4, 40),
    "kein_fenster_lade90": (18, 3, (0.0, 8.0, "plain"), dict(t_typ=90.0), C4, 40),
    "reich300":            (18, 3, (0.6, 8.0, "plain"), dict(R=300.0), C4, 40),
    "reich600":            (18, 3, (0.6, 8.0, "plain"), dict(R=600.0), C4, 40),
    "fenster_locker":      (18, 3, (0.4, 12.0, "plain"), {}, C4, 40),
    "fenster_eng":         (18, 3, (0.8, 4.0, "plain"), {}, C4, 40),
    "fenster_regelbewusst": (18, 3, (0.6, 8.0, "rules"), {}, C4, 40),
    "fahrzeuge2":          (12, 2, (0.6, 8.0, "plain"), {}, C4, 40),
    "fahrzeuge4":          (24, 4, (0.6, 8.0, "plain"), {}, C4, 30),
    "gross":               (30, 5, (0.6, 8.0, "plain"), {}, C4, 20),
    "stafette_guenstig":   (18, 3, (0.6, 8.0, "plain"), dict(c_ret=0.1, c_swap=40.0), C5S, 40),
    "stafette_teuer":      (18, 3, (0.6, 8.0, "plain"), dict(c_ret=0.6, c_swap=120.0), C5S, 40),
    "kein_fenster_stafette_guenstig": (18, 3, (0.0, 8.0, "plain"), dict(c_ret=0.1, c_swap=40.0), C5S, 40),
    "kein_fenster_stafette_teuer":    (18, 3, (0.0, 8.0, "plain"), dict(c_ret=0.6, c_swap=120.0), C5S, 40),
    # ---- AP 0 (2026-09-24), Restmessung vor dem Bau der Demo; alle ohne S (Kombinationen C4) ----
    # (a) Live-Groesse: 10 Kunden, 2 Lkw
    "live10":                (10, 2, (0.6, 8.0, "plain"), {}, C4, 60),
    "live10_kein_fenster":   (10, 2, (0.0, 8.0, "plain"), {}, C4, 60),
    "live10_kein_fenster_lade20": (10, 2, (0.0, 8.0, "plain"), dict(t_typ=20.0), C4, 40),
    "live10_kein_fenster_lade90": (10, 2, (0.0, 8.0, "plain"), dict(t_typ=90.0), C4, 40),
    "live10_reich300":       (10, 2, (0.6, 8.0, "plain"), dict(R=300.0), C4, 40),
    "live10_reich400":       (10, 2, (0.6, 8.0, "plain"), dict(R=400.0), C4, 40),
    "live10_reich600":       (10, 2, (0.6, 8.0, "plain"), dict(R=600.0), C4, 40),
    # (c) unbezahlte Pflichtpausen (Cfg.pause_paid=False), gleiche Seeds/Instanzen wie basis/kein_fenster/kein_fenster_lade*
    "unbezahlt_basis":               (18, 3, (0.6, 8.0, "plain"), dict(pause_paid=False), C4, 60),
    "unbezahlt_kein_fenster":        (18, 3, (0.0, 8.0, "plain"), dict(pause_paid=False), C4, 60),
    "unbezahlt_kein_fenster_lade20": (18, 3, (0.0, 8.0, "plain"), dict(pause_paid=False, t_typ=20.0), C4, 40),
    "unbezahlt_kein_fenster_lade90": (18, 3, (0.0, 8.0, "plain"), dict(pause_paid=False, t_typ=90.0), C4, 40),
    # (d) Verspaetungsstrafe 20 / 80 EUR/h (Standard 40 = Konfiguration basis)
    "strafe20": (18, 3, (0.6, 8.0, "plain"), dict(c_late=20.0), C4, 40),
    "strafe80": (18, 3, (0.6, 8.0, "plain"), dict(c_late=80.0), C4, 40),
}


def valid_seeds(n: int, K: int, N: int) -> list[int]:
    """Erste N Seeds, deren Instanz fuer R=RMIN loesbar ist (jeder Kunde per Rundfahrt erreichbar)."""
    cfg = replace(BASE, R=RMIN)
    out = []
    s = 0
    while len(out) < N:
        inst = make_geometry(s, n, K)
        ev = Ev(inst, cfg, 0, 1, 0)
        if all(is_feasible(ev.cost((c,))) for c in range(1, n + 1)):
            out.append(s)
        s += 1
    return out


def cell_metrics(ev: Ev, cfg: Cfg, routes, base_routes) -> dict:
    inst = ev.inst
    m = dict(km=0.0, span_min=0.0, drive_min=0.0, nights=0, rest_min=0.0, breaks=0, breaks_at_charger=0, charges=0,
             charge_km=0.0, charge_min_plain=0.0, free_charge_min=0.0, rests_at_charger=0, swaps=0, wait_min=0.0,
             late_min=0.0, late_n=0, idle_min=0.0, used=0, pause_min=0.0)
    total = 0.0
    feasible = True
    for r in routes:
        if not r:
            continue
        p = ev.plan(r)
        if p is None:
            feasible = False
            continue
        st = plan_stats(p["events"], cfg)
        total += p["cost"]
        m["used"] += 1
        m["span_min"] += st["t_end"]
        for k in ("km", "drive_min", "nights", "rest_min", "breaks", "breaks_at_charger", "charges", "charge_km",
                  "charge_min_plain", "free_charge_min", "rests_at_charger", "swaps", "wait_min", "late_min", "late_n",
                  "idle_min", "pause_min"):
            m[k] += st[k]
    m["feasible"] = feasible
    m["total"] = total if feasible else None
    m["late_cost"] = cfg.c_late * m["late_min"] / 60.0
    m["oper"] = (total - m["late_cost"]) if feasible else None
    m["driver_h"] = (m["span_min"] - m["rest_min"]) / 60.0 + m["swaps"] * cfg.t_swap / 60.0
    if not cfg.pause_paid:
        m["driver_h"] -= m["pause_min"] / 60.0                   # unbezahlte Pflichtpausen zaehlen nicht als Fahrerzeit
    re = total_cost(ev, base_routes)                          # Nachbewertung der regelfreien Basistouren
    m["re_total"] = re if is_feasible(re) else None
    m["routes"] = [list(r) for r in routes]
    return m


def run_task(args):
    name, seed = args
    n, K, (share, width, ref), over, combos, _ = CONFIGS[name]
    cfg = replace(BASE, **over)
    t0 = time.time()
    inst = make_instance(seed, n, K, cfg, tw_share=share, tw_width_h=width, tw_ref=ref)
    res: dict = {}
    out, pool = solve_all(inst, cfg, combos, seed)
    base_routes = out[(0, 0, 0)][0]
    for combo in combos:
        routes, c, ev = out[combo]
        m = cell_metrics(ev, cfg, routes, base_routes)
        m["n_eval"] = ev.n_eval
        res[combo_name(combo)] = m
    return dict(config=name, seed=seed, tw_count=inst.tw_count, pool=len(pool), cells=res, total_s=round(time.time() - t0, 1))


def raw_path(name: str) -> str:
    return os.path.join(HERE, f"raw_{name}.jsonl")


def load_raw(name: str) -> list[dict]:
    p = raw_path(name)
    if not os.path.exists(p):
        return []
    out = []
    with open(p, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def run_config(name: str, N: int | None, procs: int) -> None:
    n, K, tw, over, combos, N0 = CONFIGS[name]
    N = N or N0
    seeds = valid_seeds(n, K, N)
    done = {r["seed"] for r in load_raw(name)}
    todo = [(name, s) for s in seeds if s not in done]
    print(f"[{name}] n={n} K={K} tw={tw} {over or ''} Kombinationen={[combo_name(c) for c in combos]} "
          f"Instanzen={N} (schon fertig: {len(done)})", flush=True)
    if not todo:
        return
    t0 = time.time()
    with Pool(processes=procs) as pool, open(raw_path(name), "a", encoding="utf-8") as f:
        for i, r in enumerate(pool.imap_unordered(run_task, todo, chunksize=1), 1):
            f.write(json.dumps(r) + "\n")
            f.flush()
            print(f"  [{name}] {i}/{len(todo)} seed {r['seed']}  {r['total_s']} s  ({time.time() - t0:.0f} s gesamt)", flush=True)
    print(f"[{name}] fertig in {time.time() - t0:.0f} s Wanduhrzeit", flush=True)


NL = chr(10)


def noise_task(seed: int) -> dict:
    """Suchrauschen: dieselbe Instanz, zwei verschiedene Such-Seeds (Startpool, Neustarts, ILS) -> Kosten je Zelle."""
    n, K, (share, width, ref), over, combos, _ = CONFIGS["basis"]
    cfg = replace(BASE, **over)
    inst = make_instance(seed, n, K, cfg, tw_share=share, tw_width_h=width, tw_ref=ref)
    res = {}
    for tag, sd in (("a", seed), ("b", seed + 7777)):
        out, pool = solve_all(inst, cfg, combos, sd)
        res[tag] = {combo_name(c): out[c][1] for c in combos}
    return dict(seed=seed, a=res["a"], b=res["b"])


def run_noise(N: int, procs: int) -> None:
    seeds = valid_seeds(18, 3, N)
    t0 = time.time()
    with Pool(processes=procs) as pool:
        rows = pool.map(noise_task, seeds, chunksize=1)
    lines = [f"Suchrauschen (Konfiguration basis, {N} Instanzen, zwei Such-Seeds; Differenz = b - a in % der Kosten a)"]
    for c in combos_of("basis"):
        nm = combo_name(c)
        d = [100.0 * (r["b"][nm] - r["a"][nm]) / r["a"][nm] for r in rows]
        same = sum(1 for x in d if abs(x) < 1e-9)
        lines.append(f"  {nm}: identisch in {same}/{N}, mittlere |Diff| {sum(abs(x) for x in d) / N:.3f} %, "
                     f"max |Diff| {max(abs(x) for x in d):.2f} %, mittlere Diff {sum(d) / N:+.3f} %")
    lines.append(f"  Laufzeit {time.time() - t0:.0f} s")
    with open(os.path.join(HERE, "noise_report.txt"), "w", encoding="utf-8") as f:
        f.write(NL.join(lines) + NL)
    print(NL.join(lines))


def noise_live_task(args):
    """Suchrauschen auf Live-Groesse: dieselbe Instanz, zwei Such-Seeds (s und s+7777), alle Zellen der Konfiguration."""
    name, seed = args
    n, K, (share, width, ref), over, combos, _ = CONFIGS[name]
    cfg = replace(BASE, **over)
    inst = make_instance(seed, n, K, cfg, tw_share=share, tw_width_h=width, tw_ref=ref)
    res = {}
    for tag, sd in (("a", seed), ("b", seed + 7777)):
        out, pool = solve_all(inst, cfg, combos, sd)
        res[tag] = {combo_name(c): out[c][1] for c in combos}
    return dict(config=name, seed=seed, a=res["a"], b=res["b"])


def run_noise_live(N: int, procs: int) -> None:
    """Schreibt raw_noise_live.jsonl (setzt fort). Konfigurationen live10 (mittlere Fenster) und live10_kein_fenster."""
    path = os.path.join(HERE, "raw_noise_live.jsonl")
    done = set()
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            if line.strip():
                r = json.loads(line)
                done.add((r["config"], r["seed"]))
    tasks = []
    for name in ("live10", "live10_kein_fenster"):
        n, K = CONFIGS[name][0], CONFIGS[name][1]
        for sd in valid_seeds(n, K, N):
            if (name, sd) not in done:
                tasks.append((name, sd))
    print(f"[noise_live] {len(tasks)} Aufgaben (schon fertig: {len(done)})", flush=True)
    if not tasks:
        return
    t0 = time.time()
    with Pool(processes=procs) as pool, open(path, "a", encoding="utf-8") as f:
        for i, r in enumerate(pool.imap_unordered(noise_live_task, tasks, chunksize=1), 1):
            f.write(json.dumps(r) + NL)
            f.flush()
            print(f"  [noise_live] {i}/{len(tasks)} {r['config']} seed {r['seed']} ({time.time() - t0:.0f} s)", flush=True)
    print(f"[noise_live] fertig in {time.time() - t0:.0f} s Wanduhrzeit", flush=True)


def noise_ext_task(args):
    """Vier weitere Such-Seeds (s+15555, s+23333, s+31111, s+38889) zu den zwei aus noise_live: Best-of-6 je Zelle."""
    name, seed = args
    n, K, (share, width, ref), over, combos, _ = CONFIGS[name]
    cfg = replace(BASE, **over)
    inst = make_instance(seed, n, K, cfg, tw_share=share, tw_width_h=width, tw_ref=ref)
    res = {}
    for tag, off in (("c", 15555), ("d", 23333), ("e", 31111), ("f", 38889)):
        out, pool = solve_all(inst, cfg, combos, seed + off)
        res[tag] = {combo_name(c): out[c][1] for c in combos}
    return dict(config=name, seed=seed, **res)


def run_noise_ext(procs: int) -> None:
    src = os.path.join(HERE, "raw_noise_live.jsonl")
    path = os.path.join(HERE, "raw_noise_live_ext.jsonl")
    tasks_all = [(r["config"], r["seed"]) for r in (json.loads(l) for l in open(src, encoding="utf-8") if l.strip())]
    done = set()
    if os.path.exists(path):
        done = {(r["config"], r["seed"]) for r in (json.loads(l) for l in open(path, encoding="utf-8") if l.strip())}
    tasks = [t for t in tasks_all if t not in done]
    print(f"[noise_ext] {len(tasks)} Aufgaben", flush=True)
    t0 = time.time()
    with Pool(processes=procs) as pool, open(path, "a", encoding="utf-8") as f:
        for i, r in enumerate(pool.imap_unordered(noise_ext_task, tasks, chunksize=1), 1):
            f.write(json.dumps(r) + NL)
            f.flush()
            print(f"  [noise_ext] {i}/{len(tasks)} ({time.time() - t0:.0f} s)", flush=True)
    print(f"[noise_ext] fertig in {time.time() - t0:.0f} s Wanduhrzeit", flush=True)


def combos_of(name: str):
    return CONFIGS[name][4]


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else "list"
    N = int(sys.argv[2]) if len(sys.argv) > 2 else None
    procs = int(os.environ.get("PROCS", "14"))
    if arg == "noise":
        run_noise(N or 12, procs)
    elif arg == "noise_ext":
        run_noise_ext(procs)
    elif arg == "noise_live":
        run_noise_live(N or 30, procs)
    elif arg == "list":
        for k, v in CONFIGS.items():
            print(k, v[:3], v[3], [combo_name(c) for c in v[4]], v[5])
    else:
        for name in (CONFIGS if arg == "all" else arg.split(",")):
            run_config(name, N, procs)
