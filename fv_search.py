"""fv_search.py - Tourensuche und Zeitfenster-Kalibrierung.

Mechanisch aus messreihe_fernverkehr/fern.py übernommen (Abschnitt "Zeitfenster-Kalibrierung, Konstruktion, Tourensuche"), Logik
unverändert; `_route_len`, `COMBOS` und `combo_name` stehen in fv_model.py. `reference_windows` und `make_instance` brauchen
Evaluator und Suche und stehen deshalb hier (in fv_model.py wären sie ein Importzyklus).

`solve` arbeitet mit dem Evaluator der jeweiligen Zelle: die Touren passen sich an die Regeln an. `solve_all` löst alle Zellen
einer Instanz mit gemeinsamem Lösungspool.
"""

from __future__ import annotations

import math
import random
from dataclasses import replace

from fv_evaluator import Ev
from fv_model import INF, Cfg, Inst, _route_len, make_geometry

# ----------------------------------------------------------------------------------------------------------------
# Zeitfenster-Kalibrierung, Konstruktion, Tourensuche
# ----------------------------------------------------------------------------------------------------------------
def savings_routes(inst: Inst, rng: random.Random | None = None) -> list:
    """Clarke-Wright mit Kapazitaet (Distanz), hoechstens K Touren (sonst Einfuegung der kleinsten)."""
    n, D, dem, Q, K = inst.n, inst.D, inst.dem, inst.Q, inst.K
    routes = {i: [i] for i in range(1, n + 1)}
    where = {i: i for i in range(1, n + 1)}
    sav = sorted(((D[0][i] + D[0][j] - D[i][j], i, j) for i in range(1, n + 1) for j in range(i + 1, n + 1)), reverse=True)
    for s, i, j in sav:
        ri, rj = where[i], where[j]
        if ri == rj:
            continue
        a, b = routes[ri], routes[rj]
        if sum(dem[x] for x in a) + sum(dem[x] for x in b) > Q:
            continue
        if a[-1] == i and b[0] == j:
            new = a + b
        elif a[0] == i and b[-1] == j:
            new = b + a
        elif a[0] == i and b[0] == j:
            new = a[::-1] + b
        elif a[-1] == i and b[-1] == j:
            new = a + b[::-1]
        else:
            continue
        routes[ri] = new
        del routes[rj]
        for x in new:
            where[x] = ri
    out = list(routes.values())
    fit = _fit_K(inst, out, rng)
    return fit if fit is not None else ffd_routes(inst)


def ffd_routes(inst: Inst) -> list:
    """Rueckfall: First-Fit-Decreasing auf K Touren (garantiert zulaessig, siehe make_geometry), je Tour nach Winkel."""
    loads = [0.0] * inst.K
    routes = [[] for _ in range(inst.K)]
    for c in sorted(range(1, inst.n + 1), key=lambda x: -inst.dem[x]):
        j = min(range(inst.K), key=lambda x: loads[x])
        routes[j].append(c)
        loads[j] += inst.dem[c]
    x0, y0 = inst.xy[0]
    for r in routes:
        r.sort(key=lambda c: math.atan2(inst.xy[c][1] - y0, inst.xy[c][0] - x0))
    return routes



def _fit_K(inst, routes, rng=None):
    D, dem, Q, K = inst.D, inst.dem, inst.Q, inst.K
    routes = [list(r) for r in routes if r]
    while len(routes) > K:
        routes.sort(key=lambda r: sum(dem[x] for x in r))
        small = routes.pop(0)
        for c in small:
            best = None
            for ri, r in enumerate(routes):
                if sum(dem[x] for x in r) + dem[c] > Q:
                    continue
                for pos in range(len(r) + 1):
                    r2 = r[:pos] + [c] + r[pos:]
                    d = _route_len(D, r2) - _route_len(D, r)
                    if best is None or d < best[0]:
                        best = (d, ri, pos)
            if best is None:
                return None
            _, ri, pos = best
            routes[ri].insert(pos, c)
    while len(routes) < K:
        routes.append([])
    return routes


def insertion_routes(inst: Inst, rng: random.Random) -> list:
    """Zufaellige Reihenfolge, billigste Einfuegung unter Kapazitaet (Neustart-Konstruktion)."""
    for _ in range(50):
        order = list(range(1, inst.n + 1))
        rng.shuffle(order)
        routes = [[] for _ in range(inst.K)]
        loads = [0.0] * inst.K
        ok = True
        for c in order:
            best = None
            for ri, r in enumerate(routes):
                if loads[ri] + inst.dem[c] > inst.Q:
                    continue
                for pos in range(len(r) + 1):
                    r2 = r[:pos] + [c] + r[pos:]
                    d = _route_len(inst.D, r2) - _route_len(inst.D, r)
                    if best is None or d < best[0]:
                        best = (d, ri, pos)
            if best is None:
                ok = False
                break
            _, ri, pos = best
            routes[ri].insert(pos, c)
            loads[ri] += inst.dem[c]
        if ok:
            return routes
    return ffd_routes(inst)


def total_cost(ev: Ev, routes) -> float:
    return sum(ev.cost(tuple(r)) for r in routes)


def local_search(ev: Ev, routes, rng: random.Random, nn_k: int = 6, max_pass: int = 30, screen=None):
    """Relocate (Segmente 1-3, ggf. gedreht), Swap, 2-opt, 2-opt* mit dem Evaluator `ev` (First-Improvement je Kandidat).
    screen = (fn, margin): Kandidaten, deren NAEHERUNGSkosten fn(route) um mehr als `margin` EUR schlechter waeren, werden
    gar nicht erst mit dem (teuren) Evaluator bewertet (reiner Rechenzeit-Filter, z. B. fn = additive Naeherung
    F+E-Basis fuer den FE-Evaluator). Angenommen wird ein Zug immer nur nach dem echten Evaluator."""
    inst = ev.inst
    dem, Q, D = inst.dem, inst.Q, inst.D
    routes = [list(r) for r in routes]
    while len(routes) < inst.K:
        routes.append([])
    nn = {}
    for c in range(1, inst.n + 1):
        nn[c] = set(sorted((x for x in range(1, inst.n + 1) if x != c), key=lambda x: D[c][x])[:nn_k])
    cur = [ev.cost(tuple(r)) for r in routes]
    load = [sum(dem[x] for x in r) for r in routes]
    sc_cache: dict = {}

    def sc(r):
        t = tuple(r)
        v = sc_cache.get(t)
        if v is None:
            v = sc_cache[t] = screen[0](t) if t else 0.0
        return v

    def ok(new_rs, old_rs):
        if screen is None:
            return True
        return sum(sc(x) for x in new_rs) - sum(sc(x) for x in old_rs) <= screen[1]

    def near(base, j, seg):
        if not base:
            return True
        left = base[j - 1] if j > 0 else None
        right = base[j] if j < len(base) else None
        nb = nn[seg[0]] | nn[seg[-1]]
        return (left in nb) or (right in nb) or left is None or right is None

    for _ in range(max_pass):
        improved = False
        cand = []
        for ri, r in enumerate(routes):
            m = len(r)
            for i in range(m):
                for L in (1, 2, 3):
                    if i + L > m:
                        break
                    for rj in range(len(routes)):
                        cand.append(("reloc", ri, i, L, rj))
            for i in range(m):
                for j in range(i + 1, m):
                    cand.append(("2opt", ri, i, j))
        for ri in range(len(routes)):
            for rj in range(ri + 1, len(routes)):
                for i in range(len(routes[ri])):
                    for j in range(len(routes[rj])):
                        cand.append(("swap", ri, i, rj, j))
                for i in range(len(routes[ri]) + 1):
                    for j in range(len(routes[rj]) + 1):
                        cand.append(("2star", ri, i, rj, j))
        rng.shuffle(cand)
        for mv in cand:
            kind = mv[0]
            new = {}
            if kind == "reloc":
                _, ri, i, L, rj = mv
                r = routes[ri]
                if i + L > len(r):
                    continue
                seg = r[i:i + L]
                segload = sum(dem[x] for x in seg)
                if rj != ri and load[rj] + segload > Q:
                    continue
                base = (r[:i] + r[i + L:]) if rj == ri else routes[rj]
                src = r[:i] + r[i + L:]
                best = None
                for j in range(len(base) + 1):
                    if not near(base, j, seg):
                        continue
                    for rev in ((False, True) if L > 1 else (False,)):
                        s2 = seg[::-1] if rev else seg
                        nr = base[:j] + s2 + base[j:]
                        if rj == ri:
                            if nr == r:
                                continue
                            if not ok([nr], [r]):
                                continue
                            dl = ev.cost(tuple(nr)) - cur[ri]
                            key = (dl, j, rev)
                            if best is None or key < best[0]:
                                best = (key, {ri: nr})
                        else:
                            if not ok([nr, src], [r, routes[rj]]):
                                continue
                            dl = ev.cost(tuple(nr)) + ev.cost(tuple(src)) - cur[ri] - cur[rj]
                            key = (dl, j, rev)
                            if best is None or key < best[0]:
                                best = (key, {ri: src, rj: nr})
                if best is None or best[0][0] >= -1e-6:
                    continue
                new = best[1]
            elif kind == "2opt":
                _, ri, i, j = mv
                r = routes[ri]
                if j >= len(r):
                    continue
                nr = r[:i] + r[i:j + 1][::-1] + r[j + 1:]
                if not ok([nr], [r]):
                    continue
                if ev.cost(tuple(nr)) - cur[ri] >= -1e-6:
                    continue
                new = {ri: nr}
            elif kind == "swap":
                _, ri, i, rj, j = mv
                if i >= len(routes[ri]) or j >= len(routes[rj]):
                    continue
                u, v = routes[ri][i], routes[rj][j]
                if load[ri] - dem[u] + dem[v] > Q or load[rj] - dem[v] + dem[u] > Q:
                    continue
                a = list(routes[ri]); b = list(routes[rj])
                a[i], b[j] = v, u
                if not ok([a, b], [routes[ri], routes[rj]]):
                    continue
                if ev.cost(tuple(a)) + ev.cost(tuple(b)) - cur[ri] - cur[rj] >= -1e-6:
                    continue
                new = {ri: a, rj: b}
            else:  # 2star
                _, ri, i, rj, j = mv
                if i > len(routes[ri]) or j > len(routes[rj]):
                    continue
                a = routes[ri][:i] + routes[rj][j:]
                b = routes[rj][:j] + routes[ri][i:]
                if sum(dem[x] for x in a) > Q or sum(dem[x] for x in b) > Q:
                    continue
                if not ok([a, b], [routes[ri], routes[rj]]):
                    continue
                if ev.cost(tuple(a)) + ev.cost(tuple(b)) - cur[ri] - cur[rj] >= -1e-6:
                    continue
                new = {ri: a, rj: b}
            for ri2, nr in new.items():
                routes[ri2] = nr
                cur[ri2] = ev.cost(tuple(nr))
                load[ri2] = sum(dem[x] for x in nr)
            improved = True
        if not improved:
            break
    return routes, sum(cur)


def perturb(routes, rng, inst, k=3):
    routes = [list(r) for r in routes]
    for _ in range(k):
        src = [i for i, r in enumerate(routes) if r]
        ri = rng.choice(src)
        r = routes[ri]
        p = rng.randrange(len(r))
        c = r.pop(p)
        cand = [j for j in range(len(routes)) if sum(inst.dem[x] for x in routes[j]) + inst.dem[c] <= inst.Q]
        rj = rng.choice(cand) if cand else ri
        routes[rj].insert(rng.randint(0, len(routes[rj])), c)
    return routes


def solve(ev: Ev, seed: int, starts=None, ils: int = 2, n_ls: int = 3, screen=None):
    """Savings-Start + Insertion-Start (+ uebergebene Startloesungen), Relocate/Swap/2-opt/2-opt*, kleine ILS."""
    rng = random.Random(seed)
    inst = ev.inst
    cand_starts = [savings_routes(inst), insertion_routes(inst, rng)]
    if starts:
        cand_starts += [ [list(r) for r in s] for s in starts ]
    # billigste Startloesung zuerst verbessern
    scored = sorted(cand_starts, key=lambda s: total_cost(ev, s))
    best, best_c = None, INF
    for s in scored[:n_ls]:
        r, c = local_search(ev, s, rng, screen=screen)
        if c < best_c - 1e-9:
            best, best_c = r, c
    for _ in range(ils):
        r, c = local_search(ev, perturb(best, rng, inst), rng, screen=screen)
        if c < best_c - 1e-9:
            best, best_c = r, c
    return best, best_c


def _norm(routes):
    return tuple(sorted(tuple(r) for r in routes if r))


def solve_all(inst: Inst, cfg: Cfg, combos, seed: int, restarts: int = 6, margin: float = 150.0, reps_exp=(2, 3, 3)):
    """Loest alle Schalterkombinationen einer Instanz mit GEMEINSAMEM Loesungspool.
      1. billige Zellen (aus, F, E): je `restarts` Neustarts (verschiedene Seeds) -> Pool
      2. teure Zellen (FE, F-S, FES): LS aus den besten Pool-Mitgliedern, Kandidaten vorab mit additiver Naeherung
         (Summe der billigen Evaluatoren) gefiltert (`margin`), angenommen wird nach dem echten Evaluator
      3. jede Zelle nimmt das Minimum ueber den GANZEN Pool unter IHREM Evaluator (Konsistenz: kein Zelle ist schlechter
         als eine Loesung, die eine andere Zelle gefunden hat)
    Liefert {combo: (routes, cost, Ev)} und den Pool."""
    evs = {c: Ev(inst, cfg, *c) for c in combos}
    pool: dict = {}

    def add(routes):
        pool.setdefault(_norm(routes), [list(r) for r in routes])

    ev0 = evs[(0, 0, 0)]
    cheap = [c for c in [(0, 0, 0), (1, 0, 0), (0, 1, 0)] if c in evs]
    for ci, c in enumerate(cheap):
        for k in range(restarts):
            r, _ = solve(evs[c], seed * 1000 + 37 * ci + k, starts=list(pool.values())[-4:], ils=2, n_ls=3)
            add(r)
    evF, evE = evs.get((1, 0, 0)), evs.get((0, 1, 0))

    def top_starts(ev, k=4):
        return sorted(pool.values(), key=lambda s: total_cost(ev, s))[:k]

    if (1, 1, 0) in evs:
        f = lambda t: evF.cost(t) + evE.cost(t) - ev0.cost(t)          # noqa: E731  additive Naeherung
        ev = evs[(1, 1, 0)]
        for k in range(reps_exp[0]):
            r, _ = solve(ev, seed * 1000 + 501 + k, starts=top_starts(ev), ils=2, n_ls=2, screen=(f, margin))
            add(r)
    if (1, 0, 1) in evs:
        evFS = evs[(1, 0, 1)]
        f = lambda t: evF.cost(t)                                       # noqa: E731  S nur zusaetzliche Optionen
        for k in range(reps_exp[1]):
            r, _ = solve(evFS, seed * 1000 + 521 + k, starts=top_starts(evFS), ils=2, n_ls=2, screen=(f, margin))
            add(r)
    if (1, 1, 1) in evs:
        evFES, evFS, evFE = evs[(1, 1, 1)], evs.get((1, 0, 1)), evs.get((1, 1, 0))
        f = (lambda t: evFS.cost(t) + evE.cost(t) - ev0.cost(t)) if evFS else (lambda t: evFE.cost(t))  # noqa: E731
        for k in range(reps_exp[2]):
            r, _ = solve(evFES, seed * 1000 + 541 + k, starts=top_starts(evFES), ils=2, n_ls=2, screen=(f, margin))
            add(r)
    out = {}
    for c, ev in evs.items():
        best = min(pool.values(), key=lambda s: total_cost(ev, s))
        out[c] = ([list(x) for x in best], total_cost(ev, best), ev)
    return out, pool


def reference_windows(inst: Inst, cfg: Cfg, seed: int, share: float, width_h: float, ref: str = "plain") -> Inst:
    """Fenster um die Servicebeginne einer Referenztour ohne Fenster. ref="plain": Referenz ohne Regeln (verspaetungsfrei
    ohne Regeln, Standard); ref="rules": Referenz mit Fahrerregeln F (Fenster kennen die Ruhezeiten, Sensitivitaet).
    Ziehungen (Auswahl, Lage) sind unabhaengig von share/width/ref -> gepaart ueber Sweeps."""
    ev0 = Ev(inst, cfg, 1 if ref == "rules" else 0, 0, 0)
    routes, _ = solve(ev0, seed=seed * 31 + 7, ils=1)
    arrive = {}
    for r in routes:
        if not r:
            continue
        for e in ev0.plan(r)["events"]:
            if e[0] == "serve":
                arrive[e[3]] = e[1]
    rng = random.Random(seed * 77 + 3)
    e = list(inst.e)
    l = list(inst.l)
    cnt = 0
    w = width_h * 60.0
    for c in range(1, inst.n + 1):
        pick, u = rng.random(), rng.uniform(0.2, 0.8)
        if pick < share:
            e[c] = max(0.0, arrive[c] - u * w)
            l[c] = e[c] + w
            cnt += 1
    return replace(inst, e=e, l=l, tw_count=cnt)


def make_instance(seed: int, n: int = 18, K: int = 3, cfg: Cfg | None = None, tw_share: float = 0.6,
                  tw_width_h: float = 8.0, tw_ref: str = "plain", **geo) -> Inst:
    cfg = cfg or Cfg()
    inst = make_geometry(seed, n, K, **geo)
    if tw_share > 0:
        inst = reference_windows(inst, cfg, seed, tw_share, tw_width_h, tw_ref)
    return inst
