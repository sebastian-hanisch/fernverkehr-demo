"""fv_evaluator.py - Routen-Evaluator: aus einer Stoppfolge der kostenoptimale Fahrplan (Label-Setting-DP).

Mechanisch aus messreihe_fernverkehr/fern.py übernommen (Abschnitt "Evaluator", `plan_stats`, `cost_from_events`), Logik
unverändert. Ladestopps, Ladeumfang, Pausen, Tagesruhen und Fahrerwechsel werden per Label-Setting mit Pareto-Dominanz über
(g, t, dc, dd, -b) bestimmt (kleine eps-Toleranzen, Cfg).
"""

from __future__ import annotations

from fv_model import BIG, INF, Cfg, Inst, _route_len

# ----------------------------------------------------------------------------------------------------------------
# Evaluator
# ----------------------------------------------------------------------------------------------------------------
# Label: (k0, tk, dc, dd, nb, cost, prev, ev, t)
#   k0 = cost - rate*t (Zeitfenster relevant: Warten kostet rate, also g-Vergleich) sonst cost;  tk = t oder 0;
#   nb = -Akkustand;  alle Dominanzkriterien "kleiner ist besser".  (eps > 0: eps-Dominanz, siehe Cfg)
def _insert(lst, lab, tol):
    eg, et, ec, eb = tol
    k0, tk, dc, dd, nb = lab[0], lab[1], lab[2], lab[3], lab[4]
    for o in lst:
        if o[0] <= k0 + eg and o[1] <= tk + et and o[2] <= dc + ec and o[3] <= dd + ec and o[4] <= nb + eb:
            return
    lst[:] = [o for o in lst if not (k0 <= o[0] + eg and tk <= o[1] + et and dc <= o[2] + ec
                                    and dd <= o[3] + ec and nb <= o[4] + eb)]
    lst.append(lab)


class Ev:
    """Kostenoptimaler Fahrplan je Stoppfolge. F/E/S schalten die Regeln ein; alle aus = einfache CVRPTW-Tour."""

    def __init__(self, inst: Inst, cfg: Cfg, F=False, E=False, S=False):
        self.inst, self.cfg = inst, cfg
        self.F, self.E = bool(F), bool(E)
        self.S = bool(S) and self.F
        self.v = cfg.speed / 60.0
        self.rate = (cfg.c_drv + cfg.c_veh) / 60.0
        self.rveh = cfg.c_veh / 60.0
        # Kosten einer Pflichtpause (45 min): bezahlt = rate*brk (bitgleich zum bisherigen Ausdruck), unbezahlt = nur Fahrzeug
        self.brk_cost = self.rate * cfg.brk if cfg.pause_paid else self.rveh * cfg.brk
        self.tk = cfg.t_typ / cfg.typ_share / cfg.R       # min je km Reichweite
        self.tol = (cfg.eps_g + 1e-7, cfg.eps_t + 1e-7, cfg.eps_c + 1e-7, cfg.eps_b + 1e-7)
        self._cache: dict = {}
        self._wp: dict = {}
        self.n_eval = 0
        self._tr = False

    # -- Hilfen ---------------------------------------------------------------------------------------------
    def _wps(self, a: int, b: int) -> list:
        key = (a, b)
        r = self._wp.get(key)
        if r is not None:
            return r
        inst, cfg, D = self.inst, self.cfg, self.inst.D
        out = []
        if self.E:
            c = sorted((D[a][s] + D[s][b] - D[a][b], s) for s in inst.stations if D[a][s] + D[s][b] - D[a][b] <= cfg.max_detour)
            out += [s for _, s in c[:cfg.max_st]]
        if self.S:
            c = sorted((D[a][s] + D[s][b] - D[a][b], s) for s in inst.relays if D[a][s] + D[s][b] - D[a][b] <= cfg.max_detour)
            out += [s for _, s in c[:cfg.max_rl]]
        out.sort(key=lambda w: -D[w][b])
        self._wp[key] = out
        return out

    def _mk(self, cost, t, dc, dd, nb, prev, evs):
        if self._tr:
            return (cost - self.rate * t, t, dc, dd, nb, cost, prev, evs, t)
        return (cost, 0.0, dc, dd, nb, cost, prev, evs, t)

    def _drive(self, lab, dist, track):
        _, _, dc, dd, nb, cost, prev, ev, t = lab
        cfg = self.cfg
        b = -nb
        if self.E:
            b -= dist
            if b < -1e-7:
                return None
        rem = dist / self.v
        cost += cfg.c_km * dist
        rate = self.rate
        evs = [] if track else None
        if not self.F:
            t0 = t
            t += rem
            cost += rate * rem
            if track:
                evs.append(("drive", t0, t, dist))
        else:
            while rem > 1e-9:
                room = min(cfg.blk - dc, cfg.day - dd)
                step = rem if rem <= room + 1e-9 else max(room, 0.0)
                if step > 1e-12:
                    t0 = t
                    t += step
                    cost += rate * step
                    dc += step
                    dd += step
                    rem -= step
                    if track:
                        evs.append(("drive", t0, t, step * self.v))
                if rem <= 1e-9:
                    break
                t0 = t
                if cfg.day - dd <= 1e-9:
                    t += cfg.rest
                    cost += self.rveh * cfg.rest + cfg.c_night
                    dc = dd = 0.0
                    if track:
                        evs.append(("rest", t0, t, "road"))
                else:
                    t += cfg.brk
                    cost += self.brk_cost
                    dc = 0.0
                    if track:
                        evs.append(("break", t0, t, "road"))
        return self._mk(cost, t, dc, dd, -b, lab if track else None, evs)

    def _serve(self, labels, c, track):
        inst, cfg, rate = self.inst, self.cfg, self.rate
        e_c, l_c, sv = inst.e[c], inst.l[c], inst.svc[c]
        out = []
        for lab in labels:
            _, _, dc, dd, nb, cost, prev, ev, t = lab
            variants = [(t, dc, dd, cost, None)]
            if self.F:
                waits = t < e_c - 1e-9
                if dc > 1e-9 and (waits or dc >= cfg.vol_c * cfg.blk):
                    variants.append((t + cfg.brk, 0.0, dd, cost + self.brk_cost, ("break", t, t + cfg.brk, "cust")))
                if dd > 1e-9 and (waits or dd >= cfg.vol_d * cfg.day):
                    variants.append((t + cfg.rest, 0.0, 0.0, cost + self.rveh * cfg.rest + cfg.c_night,
                                     ("rest", t, t + cfg.rest, "cust")))
            for (t2, dc2, dd2, cost2, evp) in variants:
                start = t2 if t2 >= e_c else e_c
                late = start - l_c if start > l_c else 0.0
                cost3 = cost2 + rate * ((start - t2) + sv) + cfg.c_late * late / 60.0
                t3 = start + sv
                evs = None
                if track:
                    evs = []
                    if evp:
                        evs.append(evp)
                    if start > t2 + 1e-9:
                        evs.append(("wait", t2, start, c))
                    evs.append(("serve", start, t3, c, late))
                _insert(out, self._mk(cost3, t3, dc2, dd2, nb, lab if track else None, evs), self.tol)
        return out

    def _at_waypoint(self, arr, w, nodes, k, W, track):
        """Ankunftslabels an Waypoint w -> Abfahrtslabels (Laden/Pause/Ruhe bzw. Fahrerwechsel)."""
        inst, cfg, rate, D = self.inst, self.cfg, self.rate, self.inst.D
        out = []
        tol, mk = self.tol, self._mk
        if w in inst.relays:
            for lab in arr:
                _, _, dc, dd, nb, cost, prev, ev, t = lab
                if dc < 1e-9 and dd < 1e-9:
                    continue                                   # frischer Fahrer bringt nichts
                t2 = t + cfg.t_swap
                cost2 = cost + rate * cfg.t_swap + cfg.c_drv * cfg.t_swap / 60.0 + cfg.c_swap + cfg.c_ret * D[w][0]
                evs = [("swap", t, t2, w)] if track else None
                _insert(out, mk(cost2, t2, 0.0, 0.0, nb, lab if track else None, evs), tol)
            return out
        # Ladesaeule
        R, tk = cfg.R, self.tk
        nxt = nodes[k + 1]
        # Zielakkustaende: genau so viel laden, dass man den naechsten Punkt erreicht - naechster Kunde, die naechste
        # Ladesaeule NACH dem Kunden, uebernaechster Kunde usw. (Lookahead 2 Legs), oder voll.
        reqs = {R}
        acc = D[w][nxt]
        reqs.add(acc)
        j = k + 1
        for _ in range(2):
            if j >= len(nodes) - 1:
                break
            for x in self._wps(nodes[j], nodes[j + 1]):
                if x <= inst.n + inst.ns:
                    reqs.add(acc + D[nodes[j]][x])
            acc += D[nodes[j]][nodes[j + 1]]
            reqs.add(acc)
            j += 1
        for x in W:
            reqs.add(D[w][x])
        reqs = sorted(x for x in reqs if x <= R + 1e-9)
        for lab in arr:
            _, _, dc, dd, nb, cost, prev, ev, t = lab
            b_in = -nb
            cands = [x for x in reqs if x > b_in + 1e-7]
            for B in cands:
                tc = (B - b_in) * tk
                t2 = t + tc
                cost2 = cost + rate * tc
                evs = [("charge", t, t2, w, B - b_in, "plain")] if track else None
                _insert(out, mk(cost2, t2, dc, dd, -B, lab if track else None, evs), tol)
            if self.F:
                if dc > 1e-9 and dc >= cfg.vol_c * cfg.blk:
                    fw = b_in + cfg.brk / tk
                    cb = set(cands)
                    if fw > b_in + 1e-7:
                        cb.add(min(R, fw))
                    for B in cb:
                        if B <= b_in + 1e-7:
                            continue
                        dur = max(cfg.brk, (B - b_in) * tk)
                        t2 = t + dur
                        if cfg.pause_paid:
                            cost2 = cost + rate * dur
                        else:                                   # Pause unbezahlt, der Ladeanteil ueber die Pause hinaus bezahlt
                            cost2 = cost + self.brk_cost + rate * (dur - cfg.brk)
                        evs = [("charge", t, t2, w, B - b_in, "break")] if track else None
                        _insert(out, mk(cost2, t2, 0.0, dd, -B, lab if track else None, evs), tol)
                if (dd > 1e-9 or dc > 1e-9) and dd >= cfg.vol_d * cfg.day:
                    dur = cfg.rest
                    t2 = t + dur
                    cost2 = cost + self.rveh * dur + cfg.c_night
                    evs = [("charge", t, t2, w, R - b_in, "rest")] if track else None
                    _insert(out, mk(cost2, t2, 0.0, 0.0, -R, lab if track else None, evs), tol)
        return out

    # -- Kern ----------------------------------------------------------------------------------------------
    def _run(self, route, track):
        inst, cfg, D = self.inst, self.cfg, self.inst.D
        nodes = [0] + list(route) + [0]
        m_n = len(nodes)
        # trel[i]: gibt es ab Knotenindex i (inkl.) noch ein Zeitfenster? Sonst ist die Zeit fuer die Zukunft egal.
        trel = [False] * (m_n + 1)
        for i in range(m_n - 1, -1, -1):
            c = nodes[i]
            trel[i] = trel[i + 1] or (c != 0 and (inst.e[c] > 0.0 or inst.l[c] < INF))
        b0 = cfg.R if self.E else 0.0
        labels = [(0.0, 0.0, 0.0, 0.0, -b0, 0.0, None, [] if track else None, 0.0)]
        tol = self.tol
        for k in range(m_n - 1):
            a, b = nodes[k], nodes[k + 1]
            self._tr = trel[k + 1]
            # Labels der Abfahrt neu schluesseln (t-Relevanz kann sich geaendert haben)
            labels = [self._mk(o[5], o[8], o[2], o[3], o[4], o[6], o[7]) for o in labels]
            W = self._wps(a, b)
            pos = [a] + W + [b]
            m = len(pos)
            arr = [[] for _ in range(m)]
            dl = labels
            for p in range(m - 1):
                if p > 0:
                    dl = self._at_waypoint(arr[p], pos[p], nodes, k, W, track)
                    if not dl:
                        continue
                src = pos[p]
                for q in range(p + 1, m):
                    dst = pos[q]
                    if p > 0 and q < m - 1 and not (D[dst][b] < D[src][b] - 1e-9):
                        continue
                    dist = D[src][dst]
                    for lab in dl:
                        nl = self._drive(lab, dist, track)
                        if nl is not None:
                            _insert(arr[q], nl, tol)
            labels = arr[-1]
            if not labels:
                return None
            if b != 0:
                self._tr = trel[k + 2]
                labels = self._serve(labels, b, track)
        return min(labels, key=lambda o: o[5])

    def cost(self, route) -> float:
        route = tuple(route)
        if not route:
            return 0.0
        c = self._cache.get(route)
        if c is None:
            self.n_eval += 1
            lab = self._run(route, False)
            if lab is not None:
                c = lab[5]
            else:                                   # unzulaessig: grosse Strafe + Tourlaenge (Gradient fuer die Suche)
                c = BIG + _route_len(self.inst.D, route)
            self._cache[route] = c
        return c

    def plan(self, route):
        """Fahrplan mit Ereignisliste: [(art, t0, t1, ...)]. None wenn unzulaessig."""
        route = tuple(route)
        if not route:
            return dict(cost=0.0, events=[], route=route)
        lab = self._run(route, True)
        if lab is None:
            return None
        chain = []
        x = lab
        while x is not None:
            chain.append(x[7])
            x = x[6]
        events = [e for evs in reversed(chain) if evs for e in evs]
        return dict(cost=lab[5], events=events, route=route)


def plan_stats(events, cfg: Cfg) -> dict:
    """Kennzahlen aus einer Ereignisliste (unabhaengig vom DP neu berechnet)."""
    km = sum(e[3] for e in events if e[0] == "drive")
    drive_min = sum(e[2] - e[1] for e in events if e[0] == "drive")
    rest_ev = [e for e in events if e[0] == "rest" or (e[0] == "charge" and e[5] == "rest")]
    brk_road = sum(1 for e in events if e[0] == "break")
    brk_charge = [e for e in events if e[0] == "charge" and e[5] == "break"]
    charges = [e for e in events if e[0] == "charge"]
    swaps = sum(1 for e in events if e[0] == "swap")
    wait = sum(e[2] - e[1] for e in events if e[0] == "wait")
    late_min = sum(e[4] for e in events if e[0] == "serve")
    late_n = sum(1 for e in events if e[0] == "serve" and e[4] > 1e-9)
    serve_min = sum(e[2] - e[1] for e in events if e[0] == "serve")
    t_end = max((e[2] for e in events), default=0.0)
    rest_min = sum(e[2] - e[1] for e in rest_ev)
    idle = t_end - drive_min - serve_min
    charge_min_plain = sum(e[2] - e[1] for e in charges if e[5] == "plain")
    charge_km = sum(e[4] for e in charges)
    pause_min = sum(e[2] - e[1] for e in events if e[0] == "break") + cfg.brk * len(brk_charge)
    free_charge_min = 0.0
    for e in brk_charge:
        free_charge_min += min(cfg.brk, e[4] * cfg.t_typ / cfg.typ_share / cfg.R)
    return dict(km=km, drive_min=drive_min, t_end=t_end, nights=len(rest_ev), rest_min=rest_min,
                breaks=brk_road + len(brk_charge), breaks_at_charger=len(brk_charge),
                charges=len(charges), charge_km=charge_km, charge_min_plain=charge_min_plain,
                free_charge_min=free_charge_min, rests_at_charger=sum(1 for e in charges if e[5] == "rest"),
                swaps=swaps, wait_min=wait, late_min=late_min, late_n=late_n, idle_min=idle, pause_min=pause_min)


def cost_from_events(events, cfg: Cfg, inst: Inst) -> float:
    """Kosten aus der Ereignisliste, unabhaengig vom DP (Nachrechnung)."""
    rate = (cfg.c_drv + cfg.c_veh) / 60.0
    rveh = cfg.c_veh / 60.0
    total = 0.0
    for e in events:
        dur = e[2] - e[1]
        kind = e[0]
        if kind == "drive":
            total += cfg.c_km * e[3] + rate * dur
        elif kind == "rest" or (kind == "charge" and e[5] == "rest"):
            total += rveh * dur + cfg.c_night
        elif kind == "swap":
            total += rate * dur + cfg.c_drv * dur / 60.0 + cfg.c_swap + cfg.c_ret * inst.D[e[3]][0]
        elif not cfg.pause_paid and kind == "break":
            total += rveh * dur
        elif not cfg.pause_paid and kind == "charge" and e[5] == "break":
            total += rveh * cfg.brk + rate * (dur - cfg.brk)
        else:
            total += rate * dur
        if kind == "serve":
            total += cfg.c_late * e[4] / 60.0
    return total
