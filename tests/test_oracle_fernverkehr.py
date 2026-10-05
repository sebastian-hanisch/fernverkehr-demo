"""Unabhängige Orakel für die Fernverkehrs-Demo (zusätzlich zum Tick-Simulator in fv_checks.py).

1. Tourensuche: **vollständige Aufzählung** aller Zuordnungen von 5 Kunden auf 2 Lkw und aller Reihenfolgen je Lkw, bewertet mit
   demselben Evaluator. Die Suche (solve_all) darf nie unter dem Aufzählungsoptimum liegen und muss eine gültige Aufteilung liefern
   (jeder Kunde genau einmal, höchstens K Touren, Kapazität, Gesamtkosten = Summe der Tourkosten).
2. Erreichbarkeit: Der Evaluator darf eine Rundfahrt Depot - Kunde - Depot nur dann zulassen, wenn es per Graph (Ladesäulen mit
   Kanten bis zur Reichweite, vollladen an jeder Säule) tatsächlich eine Kette gibt. Umgekehrt kennt der Evaluator höchstens
   `max_st` Ladesäulen je Fahrtabschnitt: bei 300 km erklärt er einzelne Kunden für nicht erreichbar, obwohl eine Kette existiert
   (bekannte Modellgrenze, im README genannt); bei 400 km stimmen beide überein."""

import itertools
from collections import deque
from dataclasses import replace

import pytest

from fv_evaluator import Ev
from fv_model import INF, Cfg, is_feasible, make_geometry
from fv_search import make_instance, solve_all

CELLS = [(0, 0, 0), (1, 0, 0), (0, 1, 0), (1, 1, 0)]


def _optimum(ev, inst):
    best = INF
    for zuordnung in itertools.product(range(inst.K), repeat=inst.n):
        gruppen = [[c + 1 for c in range(inst.n) if zuordnung[c] == k] for k in range(inst.K)]
        if any(sum(inst.dem[x] for x in g) > inst.Q for g in gruppen):
            continue
        summe = sum(min(ev.cost(p) for p in itertools.permutations(g)) for g in gruppen if g)
        best = min(best, summe)
    return best


@pytest.mark.parametrize("seed", range(4))
def test_suche_nie_unter_aufzaehlungsoptimum_und_gueltig(seed):
    cfg = Cfg()
    inst = make_instance(seed, n=5, K=2, cfg=cfg, tw_share=[0.0, 0.6, 0.8, 0.6][seed], tw_width_h=[4.0, 8.0][seed % 2])
    out, _pool = solve_all(inst, cfg, CELLS, seed, restarts=2)
    for zelle in CELLS:
        routen, kosten, ev = out[zelle]
        assert sorted(x for r in routen for x in r) == list(range(1, inst.n + 1))
        assert len([r for r in routen if r]) <= inst.K
        assert all(sum(inst.dem[x] for x in r) <= inst.Q for r in routen)
        assert kosten == pytest.approx(sum(ev.cost(tuple(r)) for r in routen if r), abs=1e-6)
        assert kosten >= _optimum(ev, inst) - 1e-6, (seed, zelle)


def _rundfahrt_per_graph(inst, R, c):
    knoten = [0] + inst.stations
    gesehen, schlange = {0}, deque([0])
    while schlange:                                   # Säulen, an denen man (voll geladen) weiterfahren kann
        u = schlange.popleft()
        for v in knoten:
            if v not in gesehen and inst.D[u][v] <= R + 1e-9:
                gesehen.add(v)
                schlange.append(v)
    for s in gesehen:
        rest = R - inst.D[s][c]                       # Akku am Kunden nach Vollladen an s (am Kunden wird nicht geladen)
        if rest < -1e-9:
            continue
        if inst.D[c][0] <= rest + 1e-9 or any(inst.D[c][t] <= rest + 1e-9 for t in gesehen):
            return True
    return False


@pytest.mark.parametrize("reichweite", [300.0, 400.0])
def test_erreichbarkeit_gegen_graph(reichweite):
    cfg = replace(Cfg(max_rl=4), R=reichweite)
    verpasst = 0
    for seed in range(25):
        inst = make_geometry(seed, 12, 2)
        ev = Ev(inst, cfg, 0, 1, 0)
        for c in range(1, inst.n + 1):
            ev_ok, graph_ok = is_feasible(ev.cost((c,))), _rundfahrt_per_graph(inst, reichweite, c)
            assert graph_ok or not ev_ok, (seed, c)   # der Evaluator erfindet nie eine Strecke
            verpasst += graph_ok and not ev_ok
    if reichweite >= 400.0:
        assert verpasst == 0
