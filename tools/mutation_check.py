"""Fehler-Einbau-Test: baut einzelne Fehler in die Module ein und prüft, ob die Tests (ohne AppTests, die sind zu langsam für viele
Mutanten) sie finden.

Aufruf (im Projektordner): ./venv/Scripts/python.exe tools/mutation_check.py [Teilstring des Dateinamens] [--jobs N]
Jeder Mutant ersetzt genau eine Stelle; Überlebende sind entweder gleichwertig (kein sichtbarer Unterschied) oder eine Lücke der
Tests. Jeder Mutant läuft in einer eigenen temporären Kopie (deshalb parallel möglich, Standard 6 Jobs); PYTHONDONTWRITEBYTECODE=1,
damit veralteter Bytecode keine Überlebenden vortäuscht; Quelltexte als LF (Windows-Python schreibt sonst CRLF und die Zeichenketten
unten finden nichts).

Selbstprüfung (Baseline): VOR den Mutanten läuft eine UNVERÄNDERTE Kopie gegen die Tests, für ein Kernmodul und für ein
Randmodul. Besteht sie nicht, bricht das Werkzeug ab: sonst wäre jeder "gefundene" Mutant vorgetäuscht (in wellenfreigabe-demo
fehlte der Kopie zuerst das README, das test_claims.py liest, und alle Läufe waren ungültig). Die Kopie enthält deshalb das ganze
Projekt: alle *.py, README.md, data/, tests/ (mit tests/data) und tools/.

Bewusst NICHT als Mutanten geführt (gleichwertig, kein sichtbarer Unterschied): (1) das Beschneiden der Koordinaten auf das Gebiet in
make_geometry (die Streuung der Ladesäulen und Relais liegt immer innerhalb, die Klammer wird nie erreicht); (2) `self.S = bool(S) and self.F`
(S ohne F erzeugt nur zusätzliche Wegpunkte ohne Wirkung, gleiche Kosten); (3) `waits or dc >= vol_c * blk` -> `and` (freiwillige Pause am Kunden
ohne Warten nur mit vol_c > 0 wirksam; mit dem Standard vol_c = 0 ändert sich das Minimum nie); (4) `start > l_c` -> `>=` (bei Gleichheit ist die
Verspätung ohnehin 0); (5) `<` -> `<=` bei der Wegpunkt-Reihenfolge mit 1e-9 km Abstand; (6) die Seitenumbruch-Prüfung im PDF ist entfallen
(der automatische Umbruch von fpdf2 genügt, getestet mit einem Fahrplan über mehrere Seiten).

Reihenfolge: die Tests des Moduls laufen zuerst, damit ein gefundener Mutant schnell scheitert; die langsamen Modelltests
(test_checks.py, test_frozen_reference.py) laufen nur für die Modelldateien."""
import concurrent.futures as cf
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")                # die Mutanten enthalten Emoji und Umlaute

ROOT = pathlib.Path(__file__).resolve().parent.parent
PY = sys.executable
TIMEOUT = 420
CORE = ("fv_model.py", "fv_evaluator.py", "fv_search.py")
APP_TESTS = ("tests/test_app.py", "tests/test_app_real.py")
SLOW_CORE_TESTS = ("tests/test_checks.py", "tests/test_frozen_reference.py")
# Testdateien, die ein Modul zuerst prüfen (schnelles Scheitern); der Rest folgt in Dateireihenfolge
FIRST = {
    "fv_model.py": ["test_model_units.py", "test_frozen_reference.py"], "fv_evaluator.py": ["test_model_units.py", "test_frozen_reference.py"],
    "fv_search.py": ["test_model_units.py", "test_frozen_reference.py"], "fv_live.py": ["test_live.py"], "fv_results.py": ["test_results.py"],
    "fv_stories.py": ["test_stories.py"], "fv_presets.py": ["test_presets.py"], "fv_schedule.py": ["test_schedule.py"],
    "fv_visualization.py": ["test_visualization.py"], "fv_pdf_export.py": ["test_pdf_export.py"], "fv_ui_panel.py": ["test_ui_panel.py"],
    "fv_constants.py": ["test_presets.py", "test_results.py"], "tools/build_results.py": ["test_tools.py"],
}

MUTANTS = [
    # fv_model.py: Parameter, Geometrie, Hilfen
    ("fv_model.py", "return c < BIG / 2", "return c <= BIG / 2"),
    ("fv_model.py", "return c < BIG / 2", "return c < BIG"),
    ("fv_model.py", "c_km: float = 0.70 ", "c_km: float = 0.75 "),
    ("fv_model.py", "c_drv: float = 32.0 ", "c_drv: float = 30.0 "),
    ("fv_model.py", "c_veh: float = 15.0 ", "c_veh: float = 16.0 "),
    ("fv_model.py", "c_night: float = 100.0 ", "c_night: float = 90.0 "),
    ("fv_model.py", "c_late: float = 40.0 ", "c_late: float = 45.0 "),
    ("fv_model.py", "blk: float = 270.0 ", "blk: float = 260.0 "),
    ("fv_model.py", "day: float = 540.0 ", "day: float = 530.0 "),
    ("fv_model.py", "rest: float = 660.0 ", "rest: float = 600.0 "),
    ("fv_model.py", "R: float = 400.0 ", "R: float = 410.0 "),
    ("fv_model.py", "typ_share: float = 0.6 ", "typ_share: float = 0.7 "),
    ("fv_model.py", "pause_paid: bool = True ", "pause_paid: bool = False "),
    ("fv_model.py", "max_st: int = 5 ", "max_st: int = 4 "),
    ("fv_model.py", "rng = random.Random(seed * 1000 + n)", "rng = random.Random(seed * 1000 + n + 1)"),
    ("fv_model.py", "area * (i + 0.5) / 4 + rng.uniform(-0.07, 0.07) * area", "area * (i + 0.5) / 4 + rng.uniform(-0.05, 0.07) * area"),
    ("fv_model.py", "dem = [0] + [rng.randint(1, 10) for _ in range(n)]", "dem = [0] + [rng.randint(1, 9) for _ in range(n)]"),
    ("fv_model.py", "Q = max(max(dem), math.ceil(total / (fill * K)))", "Q = max(max(dem), math.floor(total / (fill * K)))"),
    ("fv_model.py", "svc = [0.0] + [float(rng.randint(30, 60)) for _ in range(n)]", "svc = [0.0] + [float(rng.randint(30, 50)) for _ in range(n)]"),
    ("fv_model.py", "if loads[j] + d > Q:", "if loads[j] + d >= Q:"),
    ("fv_model.py", "return sum(D[p[i]][p[i + 1]] for i in range(len(p) - 1))", "return sum(D[p[i]][p[i + 1]] for i in range(len(p) - 2))"),
    ("fv_model.py", "return \"\".join(ch if v else \"-\" for ch, v in zip(\"FES\", c))", "return \"\".join(ch if not v else \"-\" for ch, v in zip(\"FES\", c))"),
    # fv_evaluator.py: Fahrplan-DP
    ("fv_evaluator.py", "self.rate = (cfg.c_drv + cfg.c_veh) / 60.0", "self.rate = (cfg.c_drv - cfg.c_veh) / 60.0"),
    ("fv_evaluator.py", "self.brk_cost = self.rate * cfg.brk if cfg.pause_paid else self.rveh * cfg.brk", "self.brk_cost = self.rveh * cfg.brk if cfg.pause_paid else self.rate * cfg.brk"),
    ("fv_evaluator.py", "self.tk = cfg.t_typ / cfg.typ_share / cfg.R ", "self.tk = cfg.t_typ * cfg.typ_share / cfg.R "),
    ("fv_evaluator.py", "room = min(cfg.blk - dc, cfg.day - dd)", "room = min(cfg.blk - dc, cfg.day - dd + 30.0)"),
    ("fv_evaluator.py", "cost += cfg.c_km * dist", "cost += cfg.c_km * dist * 1.01"),
    ("fv_evaluator.py", "t += cfg.rest\n                    cost += self.rveh * cfg.rest + cfg.c_night", "t += cfg.rest\n                    cost += self.rate * cfg.rest + cfg.c_night"),
    ("fv_evaluator.py", "cost += self.rveh * cfg.rest + cfg.c_night\n                    dc = dd = 0.0", "cost += self.rveh * cfg.rest\n                    dc = dd = 0.0"),
    ("fv_evaluator.py", "t += cfg.brk\n                    cost += self.brk_cost\n                    dc = 0.0", "t += cfg.brk\n                    cost += self.brk_cost\n                    dc = dc"),
    ("fv_evaluator.py", "if b < -1e-7:\n                return None", "if b < 1e-7:\n                return None"),
    ("fv_evaluator.py", "cost3 = cost2 + rate * ((start - t2) + sv) + cfg.c_late * late / 60.0", "cost3 = cost2 + rate * ((start - t2) + sv) + cfg.c_late * late / 30.0"),
    ("fv_evaluator.py", "cost3 = cost2 + rate * ((start - t2) + sv) + cfg.c_late * late / 60.0", "cost3 = cost2 + rate * (start - t2) + cfg.c_late * late / 60.0"),
    ("fv_evaluator.py", "if dd > 1e-9 and (waits or dd >= cfg.vol_d * cfg.day):", "if dd > 1e-9 and (not waits and dd >= cfg.vol_d * cfg.day):"),
    ("fv_evaluator.py", "variants.append((t + cfg.brk, 0.0, dd, cost + self.brk_cost,", "variants.append((t + cfg.brk, 0.0, dd, cost,"),
    ("fv_evaluator.py", "dur = max(cfg.brk, (B - b_in) * tk)", "dur = min(cfg.brk, (B - b_in) * tk)"),
    ("fv_evaluator.py", "cost2 = cost + self.rveh * dur + cfg.c_night\n                    evs = [(\"charge\", t, t2, w, R - b_in, \"rest\")]", "cost2 = cost + self.rate * dur + cfg.c_night\n                    evs = [(\"charge\", t, t2, w, R - b_in, \"rest\")]"),
    ("fv_evaluator.py", "_insert(out, mk(cost2, t2, 0.0, 0.0, -R, lab if track else None, evs), tol)", "_insert(out, mk(cost2, t2, 0.0, 0.0, -b_in, lab if track else None, evs), tol)"),
    ("fv_evaluator.py", "tc = (B - b_in) * tk", "tc = (B - b_in) * tk * 1.1"),
    ("fv_evaluator.py", "b0 = cfg.R if self.E else 0.0", "b0 = cfg.R * 0.5 if self.E else 0.0"),
    ("fv_evaluator.py", "c = BIG + _route_len(self.inst.D, route)", "c = BIG"),
    ("fv_evaluator.py", "km = sum(e[3] for e in events if e[0] == \"drive\")", "km = sum(e[3] for e in events if e[0] != \"drive\")"),
    ("fv_evaluator.py", "pause_min = sum(e[2] - e[1] for e in events if e[0] == \"break\") + cfg.brk * len(brk_charge)", "pause_min = sum(e[2] - e[1] for e in events if e[0] == \"break\")"),
    ("fv_evaluator.py", "late_n = sum(1 for e in events if e[0] == \"serve\" and e[4] > 1e-9)", "late_n = sum(1 for e in events if e[0] == \"serve\" and e[4] > 1e-3)"),
    ("fv_evaluator.py", "rest_ev = [e for e in events if e[0] == \"rest\" or (e[0] == \"charge\" and e[5] == \"rest\")]", "rest_ev = [e for e in events if e[0] == \"rest\"]"),
    ("fv_evaluator.py", "idle = t_end - drive_min - serve_min", "idle = t_end - drive_min"),
    ("fv_evaluator.py", "free_charge_min += min(cfg.brk, e[4] * cfg.t_typ / cfg.typ_share / cfg.R)", "free_charge_min += cfg.brk"),
    ("fv_evaluator.py", "breaks_at_charger=len(brk_charge)", "breaks_at_charger=len(charges)"),
    ("fv_evaluator.py", "elif not cfg.pause_paid and kind == \"break\":\n            total += rveh * dur", "elif not cfg.pause_paid and kind == \"break\":\n            total += rate * dur"),
    ("fv_evaluator.py", "total += rveh * dur + cfg.c_night", "total += rveh * dur"),
    ("fv_evaluator.py", "total += cfg.c_late * e[4] / 60.0", "total += cfg.c_late * e[4] / 30.0"),
    # fv_search.py: Konstruktion, Lokalsuche, Pool, Zeitfenster
    ("fv_search.py", "if sum(dem[x] for x in a) + sum(dem[x] for x in b) > Q:", "if sum(dem[x] for x in a) + sum(dem[x] for x in b) >= Q:"),
    ("fv_search.py", "sav = sorted(((D[0][i] + D[0][j] - D[i][j], i, j)", "sav = sorted(((D[0][i] - D[0][j] + D[i][j], i, j)"),
    ("fv_search.py", "for _ in range(50):\n        order = list(range(1, inst.n + 1))\n        rng.shuffle(order)", "for _ in range(50):\n        order = list(range(1, inst.n + 1))"),
    ("fv_search.py", "while len(routes) > K:\n        routes.sort(key=lambda r: sum(dem[x] for x in r))", "while len(routes) > K + 1:\n        routes.sort(key=lambda r: sum(dem[x] for x in r))"),
    ("fv_search.py", "for c in sorted(range(1, inst.n + 1), key=lambda x: -inst.dem[x]):", "for c in sorted(range(1, inst.n + 1), key=lambda x: inst.dem[x]):"),
    ("fv_search.py", "r.sort(key=lambda c: math.atan2(inst.xy[c][1] - y0, inst.xy[c][0] - x0))", "r.sort(key=lambda c: -math.atan2(inst.xy[c][1] - y0, inst.xy[c][0] - x0))"),
    ("fv_search.py", "def local_search(ev: Ev, routes, rng: random.Random, nn_k: int = 6, max_pass: int = 30, screen=None):", "def local_search(ev: Ev, routes, rng: random.Random, nn_k: int = 3, max_pass: int = 30, screen=None):"),
    ("fv_search.py", "if best is None or best[0][0] >= -1e-6:", "if best is None or best[0][0] >= 1e-6:"),
    ("fv_search.py", "if ev.cost(tuple(nr)) - cur[ri] >= -1e-6:", "if ev.cost(tuple(nr)) - cur[ri] >= 1e-6:"),
    ("fv_search.py", "if load[ri] - dem[u] + dem[v] > Q or load[rj] - dem[v] + dem[u] > Q:", "if load[ri] - dem[u] + dem[v] > Q + 5 or load[rj] - dem[v] + dem[u] > Q:"),
    ("fv_search.py", "return routes, sum(cur)", "return routes, sum(cur) + 1.0"),
    ("fv_search.py", "cand = [j for j in range(len(routes)) if sum(inst.dem[x] for x in routes[j]) + inst.dem[c] <= inst.Q]", "cand = [j for j in range(len(routes)) if sum(inst.dem[x] for x in routes[j]) + inst.dem[c] <= inst.Q + 3]"),
    ("fv_search.py", "def perturb(routes, rng, inst, k=3):", "def perturb(routes, rng, inst, k=1):"),
    ("fv_search.py", "def solve(ev: Ev, seed: int, starts=None, ils: int = 2, n_ls: int = 3, screen=None):", "def solve(ev: Ev, seed: int, starts=None, ils: int = 1, n_ls: int = 3, screen=None):"),
    ("fv_search.py", "        if c < best_c - 1e-9:\n            best, best_c = r, c\n    for _ in range(ils):", "        if c < best_c + 1e-9:\n            best, best_c = r, c\n    for _ in range(ils):"),
    ("fv_search.py", "def solve_all(inst: Inst, cfg: Cfg, combos, seed: int, restarts: int = 6, margin: float = 150.0, reps_exp=(2, 3, 3)):", "def solve_all(inst: Inst, cfg: Cfg, combos, seed: int, restarts: int = 6, margin: float = 150.0, reps_exp=(1, 3, 3)):"),
    ("fv_search.py", "f = lambda t: evF.cost(t) + evE.cost(t) - ev0.cost(t)          # noqa: E731  additive Naeherung", "f = lambda t: evF.cost(t) + evE.cost(t) + ev0.cost(t)          # noqa: E731  additive Naeherung"),
    ("fv_search.py", "best = min(pool.values(), key=lambda s: total_cost(ev, s))", "best = max(pool.values(), key=lambda s: total_cost(ev, s))"),
    ("fv_search.py", "return tuple(sorted(tuple(r) for r in routes if r))", "return tuple(tuple(r) for r in routes if r)"),
    ("fv_search.py", "routes, _ = solve(ev0, seed=seed * 31 + 7, ils=1)", "routes, _ = solve(ev0, seed=seed * 31 + 8, ils=1)"),
    ("fv_search.py", "rng = random.Random(seed * 77 + 3)", "rng = random.Random(seed * 77 + 4)"),
    ("fv_search.py", "pick, u = rng.random(), rng.uniform(0.2, 0.8)", "pick, u = rng.random(), rng.uniform(0.2, 0.7)"),
    ("fv_search.py", "if pick < share:", "if pick < share * 0.9:"),
    ("fv_search.py", "e[c] = max(0.0, arrive[c] - u * w)", "e[c] = arrive[c] - u * w"),
    ("fv_search.py", "l[c] = e[c] + w", "l[c] = e[c] + w + 1.0"),
    ("fv_search.py", "w = width_h * 60.0", "w = width_h * 50.0"),
    ("fv_search.py", "ev0 = Ev(inst, cfg, 1 if ref == \"rules\" else 0, 0, 0)", "ev0 = Ev(inst, cfg, 0, 0, 0)"),
    ("fv_search.py", "if tw_share > 0:\n        inst = reference_windows", "if tw_share >= 0:\n        inst = reference_windows"),
    # fv_live.py: Seeds, Instanz, Zellen
    ("fv_live.py", "return replace(Cfg(max_rl=4), t_typ=float(charge), R=float(range_km))", "return replace(Cfg(max_rl=4), t_typ=float(range_km), R=float(charge))"),
    ("fv_live.py", "return all(is_feasible(ev.cost((c,))) for c in range(1, n + 1))", "return any(is_feasible(ev.cost((c,))) for c in range(1, n + 1))"),
    ("fv_live.py", "ev = Ev(inst, live_cfg(C.CHARGE_DEFAULT, range_km), 0, 1, 0)", "ev = Ev(inst, live_cfg(C.CHARGE_DEFAULT, range_km), 0, 0, 0)"),
    ("fv_live.py", "while len(seeds) < count:", "while len(seeds) <= count:"),
    ("fv_live.py", "        entry[1] = nxt\n        return list(seeds[:count])", "        entry[1] = nxt\n        return list(seeds[:count + 1])"),
    ("fv_live.py", "key = (int(n), int(K), int(range_km))", "key = (int(n), int(K))"),
    ("fv_live.py", "return valid_seeds(int(index) + 1, n, K, range_km)[int(index)]", "return valid_seeds(int(index) + 2, n, K, range_km)[int(index) + 1]"),
    ("fv_live.py", "share, width = C.WINDOW_PARAMS[window]\n    seed = nth_valid_seed", "width, share = C.WINDOW_PARAMS[window]\n    seed = nth_valid_seed"),
    ("fv_live.py", "inst = make_instance(seed, n, K, cfg, tw_share=share, tw_width_h=width, tw_ref=\"plain\")", "inst = make_instance(seed, n, K, cfg, tw_share=share, tw_width_h=width, tw_ref=\"rules\")"),
    ("fv_live.py", "out, _pool = solve_all(inst, cfg, combos, seed, restarts=C.LIVE_RESTARTS)", "out, _pool = solve_all(inst, cfg, combos, seed + 1, restarts=C.LIVE_RESTARTS)"),
    ("fv_live.py", "base_routes = out[C.CELL_COMBOS[C.CELL_BASE]][0]", "base_routes = out[C.CELL_COMBOS[C.CELL_F]][0]"),
    ("fv_live.py", "cell[\"fix_total\"] = fixed if is_feasible(fixed) else None", "cell[\"fix_total\"] = fixed"),
    ("fv_live.py", "cell = dict(feasible=feasible, total=cost if feasible else None, routes=[list(r) for r in routes])", "cell = dict(feasible=True, total=cost if feasible else None, routes=[list(r) for r in routes])"),
    ("fv_live.py", "if not cfg.pause_paid:\n        m[\"driver_h\"] -= m[\"pause_min\"] / 60.0", "if cfg.pause_paid:\n        m[\"driver_h\"] -= m[\"pause_min\"] / 60.0"),
    ("fv_live.py", "m[\"driver_h\"] = (m[\"span_min\"] - m[\"rest_min\"]) / 60.0 + m[\"swaps\"] * cfg.t_swap / 60.0", "m[\"driver_h\"] = m[\"span_min\"] / 60.0 + m[\"swaps\"] * cfg.t_swap / 60.0"),
    ("fv_live.py", "m[\"oper\"] = (total - m[\"late_cost\"]) if feasible else None", "m[\"oper\"] = total if feasible else None"),
    ("fv_live.py", "return dict(km=cfg.c_km * m[\"km\"], fahrer=cfg.c_drv * m[\"driver_h\"], fahrzeug=cfg.c_veh * m[\"span_min\"] / 60.0,", "return dict(km=cfg.c_km * m[\"km\"], fahrer=cfg.c_drv * m[\"driver_h\"], fahrzeug=cfg.c_veh * m[\"span_min\"] / 30.0,"),
    ("fv_live.py", "late=[None if x == INF else x for x in inst.l[:n + 1]]", "late=[None if x == INF else x for x in inst.l[1:n + 2]]"),
    ("fv_live.py", "for k in _SUM_KEYS:\n            m[k] += st[k]", "for k in _SUM_KEYS:\n            m[k] = st[k]"),
    ("fv_live.py", "m[\"span_min\"] += st[\"t_end\"]", "m[\"span_min\"] = st[\"t_end\"]"),
    ("fv_live.py", "if p is None:\n            feasible = False\n            continue", "if p is None:\n            continue"),
    # fv_results.py: Urteil, Meldung, Zuordnung
    ("fv_results.py", "    if mean > factor * se:\n        return \"pos\"", "    if mean >= factor * se:\n        return \"pos\""),
    ("fv_results.py", "    if mean < -factor * se:\n        return \"neg\"", "    if mean <= -factor * se:\n        return \"neg\""),
    ("fv_results.py", "    if mean > factor * se:\n        return \"pos\"", "    if mean > se:\n        return \"pos\""),
    ("fv_results.py", "out = dict(base=base, dF_eur=f - base, dE_eur=e - base, dFE_eur=fe - base, I_eur=fe - f - e + base)", "out = dict(base=base, dF_eur=f - base, dE_eur=e - base, dFE_eur=fe - base, I_eur=fe - f - e - base)"),
    ("fv_results.py", "out[k + \"_pct\"] = 100.0 * out[k + \"_eur\"] / base", "out[k + \"_pct\"] = 100.0 * out[k + \"_eur\"] / out[\"dFE_eur\"]"),
    ("fv_results.py", "out[\"sum_eur\"] = out[\"dF_eur\"] + out[\"dE_eur\"]", "out[\"sum_eur\"] = out[\"dF_eur\"] - out[\"dE_eur\"]"),
    ("fv_results.py", "    if I_pct < -threshold:\n        return \"billiger\"", "    if I_pct <= -threshold:\n        return \"billiger\""),
    ("fv_results.py", "    if I_pct > threshold:\n        return \"teurer\"", "    if I_pct >= threshold:\n        return \"teurer\""),
    ("fv_results.py", "if s[\"n\"] != n or s[\"K\"] != K or s[\"tw_ref\"] != \"plain\" or set(o) - {\"t_typ\", \"R\"}:", "if s[\"n\"] != n or s[\"K\"] != K or set(o) - {\"t_typ\", \"R\"}:"),
    ("fv_results.py", "if s[\"n\"] != n or s[\"K\"] != K or s[\"tw_ref\"] != \"plain\" or set(o) - {\"t_typ\", \"R\"}:", "if s[\"n\"] != n or s[\"K\"] != K or s[\"tw_ref\"] != \"plain\":"),
    ("fv_results.py", "if abs(s[\"tw_share\"] - share) > 1e-9 or (share > 0 and abs(s[\"tw_width_h\"] - width) > 1e-9):", "if abs(s[\"tw_share\"] - share) > 1e-9:"),
    ("fv_results.py", "if o.get(\"t_typ\", 45.0) != charge or o.get(\"R\", 400.0) != range_km:", "if o.get(\"t_typ\", 45.0) != charge:"),
    ("fv_results.py", "if best is None or s[\"used\"] > data[best][\"used\"]:", "if best is None or s[\"used\"] < data[best][\"used\"]:"),
    ("fv_results.py", "return f\"{s['used']} Instanzen\" if not s[\"excluded\"] else f\"{s['used']} von {s['instances']} Instanzen\"", "return f\"{s['used']} Instanzen\""),
    ("fv_results.py", "(\"20 min\", [\"live10_kein_fenster_lade20\", \"kein_fenster_lade20\"])", "(\"20 min\", [\"kein_fenster_lade20\"])"),
    ("fv_results.py", "(\"400 km\", [\"live10_reich400\", \"basis\"])", "(\"400 km\", [\"live10\", \"basis\"])"),
    ("fv_results.py", "(\"2 Lkw\", [\"fahrzeuge2\"]), (\"3 Lkw\", [\"basis\"]), (\"4 Lkw\", [\"fahrzeuge4\"])", "(\"2 Lkw\", [\"fahrzeuge2\"]), (\"3 Lkw\", [\"basis\"]), (\"4 Lkw\", [\"fahrzeuge2\"])"),
    ("fv_results.py", "SUM_SERIES = ((\"live10_kein_fenster\", \"ohne Zeitfenster\"), (\"live10\", \"Zeitfenster mittel\"),", "SUM_SERIES = ((\"live10\", \"ohne Zeitfenster\"), (\"live10_kein_fenster\", \"Zeitfenster mittel\"),"),
    ("fv_results.py", "if s[\"excluded\"]:\n            out.append(", "if not s[\"excluded\"]:\n            out.append("),
    ("fv_results.py", "return [k for k in data if not k.startswith(\"_\")]", "return [k for k in data if not k.startswith(\"__\")]"),
    # fv_stories.py: Schwellen
    ("fv_stories.py", "STANDARD_OPER_MAX_SHARE = 0.40", "STANDARD_OPER_MAX_SHARE = 0.45"),
    ("fv_stories.py", "NO_WINDOW_MAX_ABS_I = 2.0", "NO_WINDOW_MAX_ABS_I = 2.5"),
    ("fv_stories.py", "NO_WINDOW_NEG_SHARE = (0.55, 0.75)", "NO_WINDOW_NEG_SHARE = (0.50, 0.75)"),
    ("fv_stories.py", "LONG_CHARGE_MAX_I = -3.0", "LONG_CHARGE_MAX_I = -2.0"),
    ("fv_stories.py", "LONG_CHARGE_MIN_NEG_SHARE = 0.90", "LONG_CHARGE_MIN_NEG_SHARE = 0.80"),
    ("fv_stories.py", "TIGHT_RANGE_MIN_I = 10.0", "TIGHT_RANGE_MIN_I = 8.0"),
    ("fv_stories.py", "return s.mean > FACTOR * s.se if sign > 0 else s.mean < -FACTOR * s.se", "return s.mean >= FACTOR * s.se if sign > 0 else s.mean <= -FACTOR * s.se"),
    ("fv_stories.py", "return s.mean > FACTOR * s.se if sign > 0 else s.mean < -FACTOR * s.se", "return s.mean > 0 if sign > 0 else s.mean < 0"),
    ("fv_stories.py", "(f18.mean > e18.mean,", "(f18.mean >= e18.mean - 30,"),
    ("fv_stories.py", "(lo <= s.neg_share <= hi,", "(lo <= s.neg_share,"),
    ("fv_stories.py", "(abs(s.mean) < NO_WINDOW_MAX_ABS_I,", "(abs(s.mean) <= NO_WINDOW_MAX_ABS_I,"),
    ("fv_stories.py", "(o18.mean <= STANDARD_OPER_MAX_SHARE * i18.mean and i18.mean > 0,", "(o18.mean <= STANDARD_OPER_MAX_SHARE * i18.mean,"),
    # fv_presets.py: Permalink
    ("fv_presets.py", "return min(spec.options, key=lambda o: (abs(o - value), o))", "return min(spec.options, key=lambda o: (abs(o - value), -o))"),
    ("fv_presets.py", "return min(spec.options, key=lambda o: (abs(o - value), o))", "return min(spec.options, key=lambda o: o)"),
    ("fv_presets.py", "value = max(spec.lo, min(spec.hi, value))", "value = max(spec.lo, value)"),
    ("fv_presets.py", "value = max(spec.lo, min(spec.hi, value))", "value = min(spec.hi, value)"),
    ("fv_presets.py", "return int(round(value))", "return int(value)"),
    ("fv_presets.py", "if not math.isfinite(value):\n        return None", "if False:\n        return None"),
    ("fv_presets.py", "text = str(raw).strip().lower()", "text = str(raw)"),
    ("fv_presets.py", "return text if spec.options and text in spec.options else None", "return text"),
    ("fv_presets.py", "st.session_state[state_key] = C.PRESETS[name][field]", "st.session_state[state_key] = C.PRESETS[\"Standard\"][field]"),
    ("fv_presets.py", "st.session_state[\"seed_input\"] = random.randint(*C.SEED_RANGE)", "st.session_state[\"seed_input\"] = random.randint(C.SEED_RANGE[0], C.SEED_RANGE[1] + 1)"),
    ("fv_presets.py", "\"customers_slider\": SettingSpec(\"n\", int, C.CUSTOMERS_DEFAULT, *C.CUSTOMERS_RANGE),", "\"customers_slider\": SettingSpec(\"n\", int, C.CUSTOMERS_DEFAULT + 1, *C.CUSTOMERS_RANGE),"),
    # fv_schedule.py: Halteliste, Balken, Zeitformat
    ("fv_schedule.py", "return f\"Tag {m // 1440 + 1}, {(m % 1440) // 60:02d}:{m % 60:02d}\"", "return f\"Tag {m // 1440}, {(m % 1440) // 60:02d}:{m % 60:02d}\""),
    ("fv_schedule.py", "return f\"Tag {m // 1440 + 1}, {(m % 1440) // 60:02d}:{m % 60:02d}\"", "return f\"Tag {m // 1440 + 1}, {(m % 1440) // 60:02d}:{m % 59:02d}\""),
    ("fv_schedule.py", "m = int(round(minutes))\n    return f\"Tag", "m = int(minutes)\n    return f\"Tag"),
    ("fv_schedule.py", "return f\"{m // 60} h {m % 60:02d} min\" if m >= 60 else f\"{m} min\"", "return f\"{m // 60} h {m % 60:02d} min\" if m > 60 else f\"{m} min\""),
    ("fv_schedule.py", "if node <= n_customers:\n        return f\"Kunde {node}\"", "if node < n_customers:\n        return f\"Kunde {node}\""),
    ("fv_schedule.py", "return f\"Ladesäule {node - n_customers}\"", "return f\"Ladesäule {node - n_customers - 1}\""),
    ("fv_schedule.py", "        if events[i][0] in (\"serve\", \"charge\"):\n            nxt = events[i][3]", "        if events[i][0] in (\"serve\",):\n            nxt = events[i][3]"),
    ("fv_schedule.py", "return {\"plain\": \"charge\", \"break\": \"charge_break\", \"rest\": \"rest\"}[event[5]]", "return {\"plain\": \"charge\", \"break\": \"charge\", \"rest\": \"rest\"}[event[5]]"),
    ("fv_schedule.py", "detail = \"pünktlich\" if e[4] <= 1e-9 else f\"{e[4]:.0f} min verspätet\"", "detail = \"pünktlich\" if e[4] <= 1.0 else f\"{e[4]:.0f} min verspätet\""),
    ("fv_schedule.py", "at_cust = e[3] == \"cust\"\n            ort = place_name(d, n_customers) if at_cust else f\"unterwegs nach {place_name(d, n_customers)}\"\n            name, detail = \"Pflichtpause\"", "at_cust = e[3] != \"cust\"\n            ort = place_name(d, n_customers) if at_cust else f\"unterwegs nach {place_name(d, n_customers)}\"\n            name, detail = \"Pflichtpause\""),
    ("fv_schedule.py", "late = e[4] if e[0] == \"serve\" else 0.0", "late = 0.0"),
    ("fv_schedule.py", "out.append(dict(art=row[\"art\"], t0=e[1] / 60.0, t1=e[2] / 60.0,", "out.append(dict(art=row[\"art\"], t0=e[1] / 60.0, t1=e[2] / 30.0,"),
    ("fv_schedule.py", "        if e[0] in (\"serve\", \"charge\"):\n            nodes.append(e[3])\n    nodes.append(0)", "        if e[0] in (\"serve\", \"charge\"):\n            nodes.append(e[3])"),
    ("fv_schedule.py", "breaks = sum(1 for e in events if e[0] == \"break\" or (e[0] == \"charge\" and e[5] == \"break\"))", "breaks = sum(1 for e in events if e[0] == \"break\")"),
    ("fv_schedule.py", "rests = sum(1 for e in events if e[0] == \"rest\" or (e[0] == \"charge\" and e[5] == \"rest\"))", "rests = sum(1 for e in events if e[0] == \"rest\")"),
    # fv_visualization.py: Konsistenz der Grafiken
    ("fv_visualization.py", "    fig.update_xaxes(fixedrange=True)\n    fig.update_yaxes(fixedrange=True)", "    fig.update_xaxes(fixedrange=True)"),
    ("fv_visualization.py", "    fig.update_xaxes(fixedrange=True)\n    fig.update_yaxes(fixedrange=True)", "    fig.update_yaxes(fixedrange=True)"),
    ("fv_visualization.py", "LEGEND_BOTTOM = dict(orientation=\"h\", yref=\"container\", yanchor=\"bottom\", y=0.0, x=0)", "LEGEND_BOTTOM = dict(orientation=\"v\", yref=\"container\", yanchor=\"bottom\", y=0.0, x=0)"),
    ("fv_visualization.py", "width=[3 if w else 0 for w in has_tw]", "width=[0 if w else 3 for w in has_tw]"),
    ("fv_visualization.py", "for day in range(1, int(total_h // 24) + 1):", "for day in range(1, int(total_h // 12) + 1):"),
    ("fv_visualization.py", "marker=dict(color=C.EVENT_COLORS[art], line=dict(color=\"#c0392b\" if late else \"white\", width=2.5 if late else 0.5))", "marker=dict(color=C.EVENT_COLORS[art], line=dict(color=\"white\", width=0.5))"),
    ("fv_visualization.py", "d[\"x\"].append(b[\"t1\"] - b[\"t0\"])", "d[\"x\"].append(b[\"t1\"])"),
    ("fv_visualization.py", "fig.update_yaxes(autorange=\"reversed\")\n    fig.update_xaxes(rangemode=\"tozero\")\n    return _lock_axes(fig)\n\n\n# ---------------------------------------------------------------------------------------------------\n# Kostenzerlegung", "fig.update_xaxes(rangemode=\"tozero\")\n    return _lock_axes(fig)\n\n\n# ---------------------------------------------------------------------------------------------------\n# Kostenzerlegung"),
    ("fv_visualization.py", "cells = [c for c in C.CELLS if res[\"cells\"][c][\"feasible\"]]\n    xs = [C.CELL_SHORT[c] for c in cells]\n    fig = go.Figure()\n    for key in C.COST_KEYS:", "cells = [c for c in C.CELLS]\n    xs = [C.CELL_SHORT[c] for c in cells]\n    fig = go.Figure()\n    for key in C.COST_KEYS:"),
    ("fv_visualization.py", "fixed = [None if res[\"cells\"][c][\"fix_total\"] is None else 100.0 * (res[\"cells\"][c][\"fix_total\"] - base) / base for c in cells]", "fixed = [None if res[\"cells\"][c][\"fix_total\"] is None else 100.0 * (res[\"cells\"][c][\"fix_total\"] - base) / res[\"cells\"][c][\"fix_total\"] for c in cells]"),
    ("fv_visualization.py", "replanned = [100.0 * (res[\"cells\"][c][\"total\"] - base) / base for c in cells]", "replanned = [100.0 * (res[\"cells\"][c][\"total\"] - base) / res[\"cells\"][c][\"total\"] for c in cells]"),
    ("fv_visualization.py", "y=[r[\"dFE\"].mean for r in rows], name=\"beides, gemessen\", marker_color=C.COMBO_COLOR, offsetgroup=\"beides\",", "y=[r[\"dFE\"].mean for r in rows], name=\"beides, gemessen\", marker_color=C.COMBO_COLOR, offsetgroup=\"summe\","),
    ("fv_visualization.py", "hatched = len(groups) > 1 and group == groups[0]", "hatched = len(groups) > 1 and group == groups[-1]"),
    ("fv_visualization.py", "one_per_level = len({r[\"level\"] for r in in_group}) == len(in_group)", "one_per_level = False"),
    ("fv_visualization.py", "y=[100.0 * s[\"comps_I\"][k][\"mean\"] / base for k in C.COST_KEYS]", "y=[s[\"comps_I\"][k][\"mean\"] for k in C.COST_KEYS]"),
    ("fv_visualization.py", "names = {\"keine\": ((\"live10_kein_fenster\", \"10/2\"), (\"kein_fenster\", \"18/3\")), \"mittel\": ((\"live10\", \"10/2\"), (\"basis\", \"18/3\"))}[window]", "names = {\"keine\": ((\"live10\", \"10/2\"), (\"basis\", \"18/3\")), \"mittel\": ((\"live10_kein_fenster\", \"10/2\"), (\"kein_fenster\", \"18/3\"))}[window]"),
    ("fv_visualization.py", "groups = ((\"kein_fenster_45min\", \"ohne Zeitfenster\"), (\"basis_45min_mit_fenster\", \"Zeitfenster mittel\"))", "groups = ((\"basis_45min_mit_fenster\", \"ohne Zeitfenster\"), (\"kein_fenster_45min\", \"Zeitfenster mittel\"))"),
    ("fv_visualization.py", "y=[pen[lv][\"I_oper\"][\"mean\"] for lv in levels], name=\"nur Betriebskosten (ohne Verspätung)\"", "y=[pen[lv][\"I\"][\"mean\"] for lv in levels], name=\"nur Betriebskosten (ohne Verspätung)\""),
    ("fv_visualization.py", "if late[c] is not None:\n            text += f\"<br>Zeitfenster", "if late[c] is None:\n            text += f\"<br>Zeitfenster"),
    ("fv_visualization.py", "nodes = S.route_nodes(t[\"events\"])\n        color =", "nodes = S.route_nodes(t[\"events\"])[1:]\n        color ="),
    # fv_pdf_export.py: Sonderzeichen und Inhalt
    ("fv_pdf_export.py", "\"−\": \"-\"", "\"−\": \"~\""),
    ("fv_pdf_export.py", "\"€\": \"EUR\"", "\"€\": \"E\""),
    ("fv_pdf_export.py", "\"–\": \"-\"", "\"–\": \"~\""),
    ("fv_pdf_export.py", "\"≥\": \">=\"", "\"≥\": \">\""),
    ("fv_pdf_export.py", "\"±\": \"+-\"", "\"±\": \"+\""),
    ("fv_pdf_export.py", "return text.encode(\"latin-1\", \"replace\").decode(\"latin-1\")", "return text"),
    ("fv_pdf_export.py", "extra = \"-\" if c == C.CELL_BASE or base is None else f\"{_de(100 * (cell_data['total'] - base) / base, 1, True)} %\"", "extra = \"-\" if c == C.CELL_BASE or base is None else f\"{_de(100 * (cell_data['total'] - base) / cell_data['total'], 1, True)} %\""),
    ("fv_pdf_export.py", "f\"{m['breaks']}/{m['nights']}/{m['charges']}\"", "f\"{m['breaks']}/{m['charges']}/{m['nights']}\""),
    ("fv_pdf_export.py", "(\"Summe der Einzel-Mehrkosten\", f\"{_de(x['dF_pct'] + x['dE_pct'], 1, True)} % ({_eur(x['sum_eur'], True)})\"),", "(\"Summe der Einzel-Mehrkosten\", f\"{_de(x['dF_pct'] - x['dE_pct'], 1, True)} % ({_eur(x['sum_eur'], True)})\"),"),
    ("fv_pdf_export.py", "for t in cell_data[\"trucks\"]:\n            keep_together(30)", "for t in cell_data[\"trucks\"][:1]:\n            keep_together(30)"),
    # fv_ui_panel.py: Formate, Meldungen, Tabellen
    ("fv_ui_panel.py", "text = f\"{v:+,.0f}\" if signed else f\"{v:,.0f}\"\n    return text.replace(\",\", \".\") + \" EUR\"", "text = f\"{v:+,.0f}\" if signed else f\"{v:,.0f}\"\n    return text + \" EUR\""),
    ("fv_ui_panel.py", "return f\"{100.0 * v:.0f} %\"", "return f\"{v:.0f} %\""),
    ("fv_ui_panel.py", "return f\"{fmt_num(s.mean, digits, True)} ± {fmt_num(s.se, digits)} %\"", "return f\"{fmt_num(s.mean, digits, True)} ± {fmt_num(s.mean, digits)} %\""),
    ("fv_ui_panel.py", "if not all(res[\"cells\"][c][\"feasible\"] for c in C.CELLS):\n        return None", "if not any(res[\"cells\"][c][\"feasible\"] for c in C.CELLS):\n        return None"),
    ("fv_ui_panel.py", "state = R.message_state(x[\"I_pct\"])\n    ctx", "state = R.message_state(-x[\"I_pct\"])\n    ctx"),
    ("fv_ui_panel.py", "billiger als die Summe der Einzelkosten. Das ist belastbar, weil die Tourensuche eine Lösung nur zu \"\n            f\"teuer finden kann, nie zu billig", "billiger als die Summe der Einzelkosten. Das ist belastbar, weil die Tourensuche eine Lösung nur zu \"\n            f\"billig finden kann, nie zu teuer"),
    ("fv_ui_panel.py", "f\"✅ Hier sparen Pause und Laden zusammen: die Kombination ist um {fmt_eur(-x['I_eur'])}", "f\"✅ Hier sparen Pause und Laden zusammen: die Kombination ist um {fmt_eur(x['I_eur'])}"),
    ("fv_ui_panel.py", "noise = data[\"_ap0_b_suchrauschen\"][\"live10\"][\"best_of_6\"][\"gap\"]", "noise = data[\"_ap0_b_suchrauschen\"][\"live10_kein_fenster\"][\"best_of_6\"][\"gap\"]"),
    ("fv_ui_panel.py", "n_none = s.get(\"excluded_reasons\", {}).get(\"suche_ohne_loesung\", 0)", "n_none = s.get(\"excluded_reasons\", {}).get(\"basistouren_unter_E_nicht_fahrbar\", 0)"),
    ("fv_ui_panel.py", "for n, K in ((res[\"n\"], res[\"K\"]), C.SIZE_LIVE, C.SIZE_MAIN):", "for n, K in ((res[\"n\"], res[\"K\"]), C.SIZE_MAIN):"),
    ("fv_ui_panel.py", "if name and name not in out:", "if name:"),
    ("fv_ui_panel.py", "\"Summe der Einzelnen\": fmt_pct(r[\"dF\"].mean + r[\"dE\"].mean, signed=True),", "\"Summe der Einzelnen\": fmt_pct(r[\"dF\"].mean, signed=True),"),
    ("fv_ui_panel.py", "\"F fest / neu\": f\"{fmt_pct(fx['dF'].mean, 1, True)} / {fmt_pct(s['dF']['mean'], 1, True)}\",", "\"F fest / neu\": f\"{fmt_pct(s['dF']['mean'], 1, True)} / {fmt_pct(fx['dF'].mean, 1, True)}\","),
    ("fv_ui_panel.py", "v[C.CELL_FE] - v[C.CELL_F] - v[C.CELL_E] + v[C.CELL_BASE], signed=True)", "v[C.CELL_FE] - v[C.CELL_F] - v[C.CELL_E] - v[C.CELL_BASE], signed=True)"),
    ("fv_ui_panel.py", "lead = next((n for n in names if data[n][\"n\"] == C.SIZE_LIVE[0] and data[n][\"K\"] == C.SIZE_LIVE[1]), names[0])", "lead = names[-1]"),
    ("fv_ui_panel.py", "{\"neg\": st.success, \"pos\": st.warning, \"none\": st.info}[verdicts[lead]](text)", "{\"neg\": st.warning, \"pos\": st.success, \"none\": st.info}[verdicts[lead]](text)"),
    # tools/build_results.py: Reduktion der Messreihe
    ("tools/build_results.py", "THRESHOLD_PCT = 2.0", "THRESHOLD_PCT = 3.0"),
    ("tools/build_results.py", "DIGITS = 4", "DIGITS = 1"),
    ("tools/build_results.py", "return dict(n=n, billiger=r(sum(x < -thr for x in v) / n), additiv=r(sum(abs(x) <= thr for x in v) / n),\n                teurer=r(sum(x > thr for x in v) / n))", "return dict(n=n, billiger=r(sum(x < -thr for x in v) / n), additiv=r(sum(abs(x) < thr for x in v) / n),\n                teurer=r(sum(x > thr for x in v) / n))"),
    ("tools/build_results.py", "return [x for x in rows if all(x[\"cells\"][c][\"feasible\"] and x[\"cells\"][c][\"re_total\"] is not None for c in CELLS)]", "return [x for x in rows if all(x[\"cells\"][c][\"feasible\"] for c in CELLS)]"),
    ("tools/build_results.py", "return 100.0 * (c[\"FE-\"][\"total\"] - c[\"F--\"][\"total\"] - c[\"-E-\"][\"total\"] + c[\"---\"][\"total\"]) / c[\"---\"][\"total\"]", "return 100.0 * (c[\"FE-\"][\"total\"] - c[\"F--\"][\"total\"] - c[\"-E-\"][\"total\"] - c[\"---\"][\"total\"]) / c[\"---\"][\"total\"]"),
    ("tools/build_results.py", "m = re.match(r\"n=(\\d+) seed=(\\d+) inst [\\d.]+s solve ([\\d.]+)s\", line)", "m = re.match(r\"n=(\\d+) seed=(\\d+) inst [\\d.]+s solve ([\\d.]+)s\", line[1:])"),
    ("tools/build_results.py", "if cell in CELLS},", "},"),
    ("tools/build_results.py", "suche_ohne_loesung=sum(1 for e in a[\"excluded_detail\"] if e[\"grund\"].startswith(\"Suche\")),", "suche_ohne_loesung=sum(1 for e in a[\"excluded_detail\"] if e[\"grund\"].startswith(\"regelfreie\")),"),
    ("tools/build_results.py", "kippen_bei_2_prozent=g[\"kippen_von_n\"][\"2.0\"])", "kippen_bei_2_prozent=g[\"kippen_von_n\"][\"3.0\"])"),
    # fv_constants.py: feste Stufen und Meldungsschwelle
    ("fv_constants.py", "THRESHOLD_PCT = 2.0 ", "THRESHOLD_PCT = 2.5 "),
    ("fv_constants.py", "SE_FACTOR = 2.0 ", "SE_FACTOR = 1.5 "),
    ("fv_constants.py", "WINDOW_PARAMS = {\"keine\": (0.0, 8.0), \"locker\": (0.4, 12.0), \"mittel\": (0.6, 8.0), \"eng\": (0.8, 4.0)}", "WINDOW_PARAMS = {\"keine\": (0.0, 8.0), \"locker\": (0.4, 12.0), \"mittel\": (0.6, 8.0), \"eng\": (0.8, 6.0)}"),
    ("fv_constants.py", "CHARGE_OPTIONS, CHARGE_DEFAULT = (20, 45, 90), 45", "CHARGE_OPTIONS, CHARGE_DEFAULT = (20, 45, 90), 90"),
    ("fv_constants.py", "LIVE_RESTARTS = 3 ", "LIVE_RESTARTS = 2 "),
    ("fv_constants.py", "CELL_COMBOS = {CELL_BASE: (0, 0, 0), CELL_F: (1, 0, 0), CELL_E: (0, 1, 0), CELL_FE: (1, 1, 0)}", "CELL_COMBOS = {CELL_BASE: (0, 0, 0), CELL_F: (0, 1, 0), CELL_E: (1, 0, 0), CELL_FE: (1, 1, 0)}"),
    ("fv_constants.py", "SEED_RANGE, SEED_DEFAULT = (0, 299), 211", "SEED_RANGE, SEED_DEFAULT = (0, 299), 250"),
    ("fv_constants.py", "\"Standard\": dict(customers=10, charge=45, range_km=400, window=\"mittel\", seed=211),", "\"Standard\": dict(customers=10, charge=45, range_km=400, window=\"mittel\", seed=212),"),
]


def build_args(name):
    tests = sorted(p.as_posix() for p in (ROOT / "tests").glob("test_*.py"))
    rel = [str(pathlib.PurePosixPath("tests") / pathlib.PurePosixPath(t).name) for t in tests]
    skip = set(APP_TESTS)
    if name not in CORE:
        skip |= set(SLOW_CORE_TESTS)
    first = [f"tests/{f}" for f in FIRST.get(name, []) + ["test_mutation_gaps.py"] if f"tests/{f}" not in skip]
    rest = [t for t in rel if t not in skip and t not in first]
    return first + rest


def run_one(n, name, old, new, tmp_root):
    """Ein Mutant in eigener Kopie; Rückgabe (n, name, old, new, Status)."""
    work = pathlib.Path(tempfile.mkdtemp(prefix=f"fv_mut{n}_", dir=tmp_root))
    try:
        for f in ROOT.glob("*.py"):
            (work / f.name).write_bytes(f.read_bytes().replace(b"\r\n", b"\n"))
        (work / "tools").mkdir()
        for f in (ROOT / "tools").glob("*.py"):
            (work / "tools" / f.name).write_bytes(f.read_bytes().replace(b"\r\n", b"\n"))
        shutil.copy(ROOT / "README.md", work / "README.md")                        # test_claims.py liest das README
        shutil.copytree(ROOT / "data", work / "data")                              # test_results.py liest die Ergebnisdatei
        shutil.copytree(ROOT / "tests", work / "tests", ignore=shutil.ignore_patterns("__pycache__"))
        for f in (work / "tests").rglob("*.py"):
            f.write_bytes(f.read_bytes().replace(b"\r\n", b"\n"))
        path = work / name
        original = path.read_bytes().decode("utf-8")
        if original.count(old) != 1:
            return n, name, old, new, f"FEHLER:{original.count(old)}"
        path.write_bytes(original.replace(old, new).encode("utf-8"))
        args = [PY, "-m", "pytest", "-x", "-q", "-p", "no:cacheprovider"] + build_args(name)
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        try:
            r = subprocess.run(args, cwd=work, env=env, capture_output=True, text=True, timeout=TIMEOUT)
            return n, name, old, new, "UEBERLEBT" if r.returncode == 0 else "gefunden"
        except subprocess.TimeoutExpired:
            return n, name, old, new, "gefunden(Zeitueberschreitung)"     # Endlosschleife gilt als gefunden
    finally:
        shutil.rmtree(work, ignore_errors=True)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    jobs = 6
    for i, a in enumerate(sys.argv[1:]):
        if a == "--jobs":
            jobs = int(sys.argv[i + 2])
            args = [x for x in args if x != sys.argv[i + 2]]
    only = args[0] if args else ""
    tmp_root = tempfile.mkdtemp(prefix="fv_mut_")
    # Selbstprüfung des Werkzeugs: ein Mutant, der nichts ändert, MUSS überleben. Sonst scheitern die Tests schon in der Kopie
    # (fehlende Datei, Umgebung), und jeder "gefundene" Mutant wäre vorgetäuscht. Ein Kernmodul und ein Randmodul.
    for probe, marker in (("fv_search.py", "import math"), ("fv_results.py", "import json")):
        status = run_one(0, probe, marker, marker, tmp_root)[4]
        if status != "UEBERLEBT":
            print(f"ABBRUCH: unveränderte Kopie besteht die Tests nicht ({probe}: {status}) - Ergebnisse wären wertlos")
            shutil.rmtree(tmp_root, ignore_errors=True)
            return 2
    print("Selbstprüfung: unveränderte Kopie besteht alle Tests (Werkzeug funktioniert)", flush=True)
    todo = [(n, *m) for n, m in enumerate(MUTANTS, 1) if not only or only in m[0]]
    survivors, errors, killed = [], [], 0
    with cf.ThreadPoolExecutor(max_workers=jobs) as pool:
        futures = [pool.submit(run_one, n, name, old, new, tmp_root) for n, name, old, new in todo]
        for fut in cf.as_completed(futures):
            n, name, old, new, status = fut.result()
            if status.startswith("FEHLER"):
                errors.append((n, name, old[:60], status))
                print(f"[{n:3d}] FEHLER (Stelle nicht eindeutig: {status})  {name}: {old[:60]!r}", flush=True)
            elif status == "UEBERLEBT":
                survivors.append((n, name, old[:70], new[:70]))
                print(f"[{n:3d}] UEBERLEBT  {name}: {old[:60]!r} -> {new[:60]!r}", flush=True)
            else:
                killed += 1
                print(f"[{n:3d}] {status}  {name}", flush=True)
    print(f"\n{killed} gefunden, {len(survivors)} überlebt, {len(errors)} Fehler in der Mutantenliste (von {len(todo)})")
    shutil.rmtree(tmp_root, ignore_errors=True)
    return 1 if (survivors or errors) else 0


if __name__ == "__main__":
    sys.exit(main())
