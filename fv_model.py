"""fv_model.py - Parameter, Instanz und Geometrie der Fernverkehrs-Tourenplanung (nur Standardbibliothek).

Mechanisch aus messreihe_fernverkehr/fern.py übernommen (Abschnitt "Parameter und Instanz" plus die Hilfen `_route_len`,
`COMBOS`, `combo_name`), Logik unverändert. Fern.py war ein Modul; die Aufteilung in fv_model / fv_evaluator / fv_search
ändert nur, wo eine Definition steht, nicht was sie tut (Nachweis: tests/test_frozen_reference.py).

Basismodell: CVRP mit Zeitfenstern (wie vrp_demo). Zwei Schalter führen entlang der Route Ressourcen:

  F  Fahrerregeln (EU 561/2006 vereinfacht): nach 4,5 h Lenkzeit 45 min Pause; max. 9 h Lenkzeit je Schicht,
     danach 11 h Tagesruhe (Fahrzeug steht, Übernachtungskosten).
  E  Elektro-Lkw: Reichweite R km bei vollem Akku, Laden nur an festen Ladesäulen (Umweg), Ladezeit
     proportional zur geladenen Energie.
  S  Stafette (Fahrerwechsel an Relaispunkten; nur mit F sinnvoll) ist im Modell erhalten, die App zeigt sie nicht.

Zeit in Minuten, Strecke in km, Geld in EUR.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

INF = float("inf")
EPS = 1e-9
BIG = 1e6                     # Strafkosten einer unzulaessigen Route (E: Reichweite nicht erreichbar)


def is_feasible(c: float) -> bool:
    return c < BIG / 2



# ----------------------------------------------------------------------------------------------------------------
# Parameter und Instanz
# ----------------------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Cfg:
    speed: float = 75.0        # km/h Durchschnitt
    c_km: float = 0.70         # EUR/km (Energie neutral: E-Lkw zahlt denselben km-Preis, Laden nur Zeit/Umweg)
    c_drv: float = 32.0        # EUR/h bezahlte Fahrerzeit (alles ausser Tagesruhe)
    c_veh: float = 15.0        # EUR/h Fahrzeugzeit (auch Stillstand, auch Tagesruhe)
    c_night: float = 100.0     # EUR je Tagesruhe (Uebernachtung/Spesen)
    c_late: float = 40.0       # EUR je Stunde Verspaetung je Stopp (weiche Zeitfenster)
    brk: float = 45.0          # min Pause
    blk: float = 270.0         # min Lenkzeit bis Pflichtpause (4,5 h)
    day: float = 540.0         # min Lenkzeit je Schicht (9 h)
    rest: float = 660.0        # min Tagesruhe (11 h)
    R: float = 400.0           # km Reichweite bei vollem Akku
    t_typ: float = 45.0        # min fuer eine "typische Ladung" ...
    typ_share: float = 0.6     # ... = 60 % der Reichweite (z. B. 20 -> 80 %)
    t_swap: float = 20.0       # min Fahrerwechsel
    c_swap: float = 80.0       # EUR je Wechsel (Organisation, Relaisfahrer-Bereitstellung)
    c_ret: float = 0.30        # EUR/km Rueckfuehrung des abgeloesten Fahrers (Abstand Relais-Depot)
    max_detour: float = 300.0  # km: Ladesaeulen/Relais mit mehr Umweg werden nicht betrachtet
    max_st: int = 5            # je Leg hoechstens diese Ladesaeulen (kleinster Umweg)
    max_rl: int = 4            # je Leg hoechstens diese Relaispunkte
    pause_paid: bool = True    # True (Standard, alle bisherigen Messreihen): Pflichtpause = bezahlte Fahrerzeit. False: die 45 min
                               # Pause werden NICHT als Fahrerlohn gerechnet (Fahrzeugzeit c_veh laeuft weiter); Warten, Laden
                               # ausserhalb der Pause und Service bleiben bezahlt (AP 0 c)
    vol_c: float = 0.0         # freiwillige Pause (an Kunde/Ladesaeule) erst ab dc >= vol_c*blk (Kunde: oder bei Wartezeit)
    vol_d: float = 0.0         # freiwillige Tagesruhe erst ab dd >= vol_d*day (Kunde: oder bei Wartezeit)
    eps_g: float = 0.5         # eps-Dominanz (0 = exakte Pareto-Mengen): EUR
    eps_t: float = 2.0         # min (Zeit, nur wenn noch Zeitfenster folgen)
    eps_c: float = 2.0         # min (Lenkzeit-Zaehler dc/dd)
    eps_b: float = 3.0         # km (Akkustand)


@dataclass
class Inst:
    n: int
    K: int
    Q: float
    xy: list
    ns: int
    nr: int
    dem: list
    e: list                    # fruehester Servicebeginn (min), je Knoten
    l: list                    # spaetester Servicebeginn (min), INF = kein Fenster
    svc: list                  # Servicedauer (min)
    D: list                    # km, symmetrisch
    tw_count: int = 0

    @property
    def stations(self):
        return list(range(self.n + 1, self.n + 1 + self.ns))

    @property
    def relays(self):
        return list(range(self.n + 1 + self.ns, self.n + 1 + self.ns + self.nr))


def _dist_matrix(xy):
    m = len(xy)
    D = [[0.0] * m for _ in range(m)]
    for i in range(m):
        xi, yi = xy[i]
        for j in range(i + 1, m):
            d = math.hypot(xi - xy[j][0], yi - xy[j][1])
            D[i][j] = D[j][i] = d
    return D


def _ffd_ok(dem, K, Q):
    loads = [0.0] * K
    for d in sorted(dem, reverse=True):
        j = min(range(K), key=lambda x: loads[x])
        if loads[j] + d > Q:
            return False
        loads[j] += d
    return True


def make_geometry(seed: int, n: int = 18, K: int = 3, area: float = 800.0, ns: int = 12, nr: int = 4,
                  depot=(0.5, 0.5), fill: float = 0.8) -> Inst:
    """Geometrie, Bedarf, Servicezeiten - unabhaengig von Zeitfenstern/Regeln (gepaart ueber Sweeps)."""
    rng = random.Random(seed * 1000 + n)
    xy = [(area * depot[0], area * depot[1])]
    for _ in range(n):
        xy.append((rng.uniform(0, area), rng.uniform(0, area)))
    # Ladesaeulen: 4x3-Raster mit Streuung plus (ns-12) Zufallspunkte
    for i in range(4):
        for j in range(3):
            xy.append((area * (i + 0.5) / 4 + rng.uniform(-0.07, 0.07) * area,
                       area * (j + 0.5) / 3 + rng.uniform(-0.07, 0.07) * area))
    for _ in range(ns - 12):
        xy.append((rng.uniform(0, area), rng.uniform(0, area)))
    # Relaispunkte: Quadrantenzentren
    for i in range(2):
        for j in range(2):
            if len(xy) - 1 - n - ns < nr:
                xy.append((area * (i + 0.5) / 2 + rng.uniform(-0.08, 0.08) * area,
                           area * (j + 0.5) / 2 + rng.uniform(-0.08, 0.08) * area))
    xy = [(min(max(x, 0.0), area), min(max(y, 0.0), area)) for x, y in xy]
    dem = [0] + [rng.randint(1, 10) for _ in range(n)]
    total = sum(dem)
    Q = max(max(dem), math.ceil(total / (fill * K)))
    while not _ffd_ok(dem[1:], K, Q):
        Q += 1
    svc = [0.0] + [float(rng.randint(30, 60)) for _ in range(n)]
    dem_full = dem + [0] * (ns + nr)
    svc_full = svc + [0.0] * (ns + nr)
    return Inst(n=n, K=K, Q=float(Q), xy=xy, ns=ns, nr=nr, dem=dem_full,
                e=[0.0] * len(xy), l=[INF] * len(xy), svc=svc_full, D=_dist_matrix(xy))


def _route_len(D, r):
    if not r:
        return 0.0
    p = [0] + list(r) + [0]
    return sum(D[p[i]][p[i + 1]] for i in range(len(p) - 1))


COMBOS = [(f, e, s) for f in (0, 1) for e in (0, 1) for s in (0, 1)]


def combo_name(c):
    return "".join(ch if v else "-" for ch, v in zip("FES", c))
