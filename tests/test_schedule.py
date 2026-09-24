"""Halteliste, Zeitstrahl-Balken, Knotenfolge und Zeitformat (fv_schedule.py) an Handbeispielen und an echten Fahrplänen."""
import pytest

import fv_constants as C
import fv_schedule as S
from live_cache import get_live

N = 6
EVENTS = [
    ("drive", 0.0, 100.0, 125.0), ("break", 100.0, 145.0, "road"), ("serve", 145.0, 195.0, 3, 0.0),
    ("charge", 195.0, 240.0, 9, 100.0, "break"), ("drive", 240.0, 300.0, 75.0), ("charge", 300.0, 310.0, 11, 20.0, "plain"),
    ("wait", 310.0, 330.0, 5), ("serve", 330.0, 360.0, 5, 12.0), ("break", 360.0, 405.0, "cust"), ("serve", 405.0, 435.0, 2, 0.0),
    ("rest", 435.0, 1095.0, "road"), ("drive", 1095.0, 1200.0, 131.0), ("rest", 1200.0, 1860.0, "cust"),
    ("charge", 1860.0, 2520.0, 8, 400.0, "rest"), ("drive", 2520.0, 2600.0, 100.0),
]


def test_clock_format_counts_days_from_the_departure():
    assert S.fmt_clock(0) == "Tag 1, 00:00"
    assert S.fmt_clock(59.6) == "Tag 1, 01:00"                     # Rundung überträgt in die Stunde
    assert S.fmt_clock(1439) == "Tag 1, 23:59" and S.fmt_clock(1440) == "Tag 2, 00:00" and S.fmt_clock(2 * 1440 + 75) == "Tag 3, 01:15"


def test_duration_format():
    assert S.fmt_duration(45) == "45 min" and S.fmt_duration(60) == "1 h 00 min" and S.fmt_duration(125.4) == "2 h 05 min"


def test_place_names_distinguish_depot_customers_and_stations():
    assert S.place_name(0, N) == "Depot" and S.place_name(1, N) == "Kunde 1" and S.place_name(N, N) == "Kunde 6"
    assert S.place_name(N + 1, N) == "Ladesäule 1" and S.place_name(N + 12, N) == "Ladesäule 12"


def test_halteliste_has_one_row_per_event_with_places_and_details():
    rows = S.halteliste(EVENTS, N)
    assert len(rows) == len(EVENTS)
    by = {(r["ereignis"], r["von"]): r for r in rows}
    drive0 = rows[0]
    assert drive0["ort"] == "unterwegs nach Kunde 3" and drive0["einzelheit"] == "125 km" and drive0["ereignis"] == "Fahrt"
    assert rows[1]["ereignis"] == "Pflichtpause" and rows[1]["ort"] == "unterwegs nach Kunde 3"
    assert rows[2]["ort"] == "Kunde 3" and rows[2]["einzelheit"] == "pünktlich"
    assert rows[3]["ereignis"] == "Laden in der Pause" and rows[3]["ort"] == "Ladesäule 3" and rows[3]["einzelheit"] == "+100 km Reichweite"
    assert rows[4]["ort"] == "unterwegs nach Ladesäule 5"                      # der nächste Halt ist die Säule 11 = Ladesäule 5
    assert rows[5]["ereignis"] == "Laden" and rows[6]["ereignis"] == "Warten" and rows[6]["einzelheit"] == "bis das Zeitfenster öffnet"
    assert rows[7]["ereignis"] == "Service" and rows[7]["einzelheit"] == "12 min verspätet"
    assert rows[8]["ereignis"] == "Pflichtpause" and rows[8]["ort"] == "Kunde 2"                # beim Kunden, vor dem Service
    assert rows[10]["ereignis"] == "Tagesruhe" and rows[10]["ort"].startswith("unterwegs nach")
    assert rows[12]["ereignis"] == "Tagesruhe" and rows[12]["ort"] == "Ladesäule 2"              # Ruhe beim Halt am Lader (folgende Ladung)
    assert rows[13]["ereignis"] == "Tagesruhe am Lader" and rows[13]["ort"] == "Ladesäule 2"
    assert rows[14]["ort"] == "unterwegs nach Depot"
    assert by[("Fahrt", "Tag 1, 00:00")] is drive0
    assert rows[10]["dauer"] == "11 h 00 min" and rows[10]["minuten"] == 660.0


def test_kinds_of_bars_map_to_the_legend_colors():
    kinds = [S.bar_kind(e) for e in EVENTS]
    assert kinds[:4] == ["drive", "break", "serve", "charge_break"] and kinds[5] == "charge" and kinds[6] == "wait"
    assert kinds[10] == "rest" and kinds[13] == "rest"
    assert set(kinds) <= set(C.EVENT_COLORS)


def test_bars_are_in_hours_and_carry_the_lateness():
    bars = S.bars(EVENTS, N)
    assert len(bars) == len(EVENTS) and bars[0]["t0"] == 0.0 and bars[0]["t1"] == pytest.approx(100 / 60)
    assert bars[7]["late"] == 12.0 and all(b["late"] == 0.0 for i, b in enumerate(bars) if i != 7)
    assert "Kunde 5" in bars[7]["text"] and "12 min verspätet" in bars[7]["text"]


def test_route_nodes_list_customers_and_charging_stops_in_order():
    assert S.route_nodes(EVENTS) == [0, 3, 9, 11, 5, 2, 8, 0]
    assert S.route_nodes([]) == [0, 0]


def test_charging_stops_and_event_counts():
    assert S.charging_stops(EVENTS) == [(9, "break"), (11, "plain"), (8, "rest")]
    assert S.event_counts(EVENTS) == dict(breaks=3, rests=3, charges=3)


def test_real_schedules_have_gapless_halteliste_and_bars():
    res = get_live()
    for cell in res["cells"].values():
        for t in cell["trucks"]:
            rows, bars = S.halteliste(t["events"], res["n"]), S.bars(t["events"], res["n"])
            assert len(rows) == len(bars) == len(t["events"])
            for a, b in zip(bars, bars[1:]):
                assert a["t1"] == pytest.approx(b["t0"])                                       # Zeitlinie lückenlos
            served = [r["ort"] for r in rows if r["ereignis"] == "Service"]
            assert served == [S.place_name(c, res["n"]) for c in t["route"]]
            nodes = S.route_nodes(t["events"])
            assert nodes[0] == 0 == nodes[-1] and [c for c in nodes if 1 <= c <= res["n"]] == list(t["route"])
