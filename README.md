# Fernverkehr: Fahrerregeln und Elektro-Lkw – Streamlit-Demo

**[→ Demo live ausprobieren](https://sebastianhanisch-fernverkehr-demo.streamlit.app/)**

Interaktive Fall-Demo (Tourenplanung): Ein Lkw fährt mehrere Stopps über hunderte Kilometer, und zwei Pflichten bestimmen den Fahrplan – die **Lenk- und Ruhezeiten der Fahrer** (EU-Verordnung 561/2006, vereinfacht) und, beim
**Elektro-Lkw**, die **Reichweite** mit **Ladestopps** an festen Ladesäulen. Die Demo beantwortet: **Was kosten beide Pflichten, addieren sich die Kosten – oder helfen sich die Pflichten, weil man die Pflichtpause zum Laden
nutzen kann?** Live auf einer kleinen Instanz (6 bis 12 Kunden, 2 Lkw, immer vier Fahrpläne: ohne Regeln, Fahrerregeln, Elektro, beides) mit Karte, Halteliste und Zeitstrahl, und **vorgerechnet** über je 60 gepaarte
Instanzen, die die Aussage tragen.

Teil des Portfolios für die Website „Sebastian Hanisch – Operations Research und Machine Learning". **Erweiterung der Tourenplanungs-Demo** (`vrp_demo`): das Basismodell (CVRP mit Zeitfenstern) bleibt, neu ist eine
**Ressourcenschicht entlang der Route** (Lenkzeit-Zähler, Akkustand), die aus jeder Stoppfolge einen Fahrplan mit Pausen, Ruhezeiten und Ladestopps macht. Die Geschwindigkeitswahl (`slow-steaming-demo`) und der
Bestandsausgleich (`leercontainer-demo`) sind ausdrücklich **nicht** Teil des Modells.

## Warum dieses Problem

Man würde erwarten, dass sich Pflichtpause und Laden zusammenlegen lassen und die Kombination beider Regeln deshalb **billiger** wird als die Summe der Einzelkosten. Die Vorab-Messung zeigt: die naheliegende Erwartung
stimmt nur halb. Die Überlappung ist real (knapp zwei Drittel der Pausen liegen an einer Ladesäule), aber **ohne Zeitfenster addieren sich die Kosten praktisch**, und **mit Zeitfenstern ist die Kombination sogar
teurer als die Summe**, weil sich Verspätungen aufschaukeln. Das Vorzeichen hängt von der Ladezeit ab: bei 90 Minuten wird die Pause fürs Laden „gratis" und die Kombination klar billiger, bei 20 Minuten nicht.
Die Hauptansicht formuliert deshalb eine **bedingte Aussage in drei Zuständen** (billiger / praktisch additiv / teurer als die Summe) für die Live-Instanz und stellt die vorgerechnete Messreihe **gleichberechtigt
daneben**: eine einzelne kleine Instanz streut stark.

## Befunde und Korrekturen gegenüber dem Plan

Die App folgt dem Detailplan (`plan_fernverkehr.html`, Arbeitspakete 1 bis 7). Abweichungen und Präzisierungen, ehrlich benannt:

- **Seed-Bereich 0 bis 299 statt 0 bis 9999.** Der Seed ist die Nummer der Instanz: der *i*-te **gültige** Seed (jeder Kunde ist mit der eingestellten Reichweite per Rundfahrt erreichbar, dieselbe Regel wie in der Messreihe).
  Das Suchen kostet etwa 3 ms je gültigem Seed; bis 9999 wären das bis zu 30 Sekunden Suchzeit vor jeder neuen Einstellung.
- **Die Live-Rechnung startet automatisch mit Spinner** (Ergebnis je Einstellung zwischengespeichert), nicht über einen eigenen Knopf: sonst wäre die Hauptansicht beim ersten Aufruf leer. Ein Rechenlauf dauert auf dem
  Entwicklungsgerät etwa 1 s (8 Kunden), 5 s (10) und 10 s (12); auf einem langsameren Server entsprechend länger.
- **`reference_windows` und `make_instance` stehen in `fv_search.py`, nicht in `fv_model.py`:** sie brauchen Evaluator und Suche, in `fv_model.py` wären sie ein Importzyklus. Das ist die einzige Umstellung bei der
  Aufteilung von `fern.py` (Logik unverändert, siehe Tests).
- **Ergänzung der Meldung um „nicht zulässig"**: bei 300 km Reichweite findet die Suche für einzelne Lagen (jeder Kunde einzeln erreichbar) keine zulässige Aufteilung auf 2 Lkw (Messreihe, 10 Kunden: 3 von 40 Lagen; live
  z. B. mit 6 Kunden bei Instanz Nr. 10, 300 km, ohne Zeitfenster, als Test hinterlegt). Die App meldet das ehrlich, statt abzustürzen; die Messreihe schließt solche Lagen aus.
- **Vergleichsspalte auch in Größe der Live-Instanz**, wo gemessen: bei 12 Kunden mit 2 Lkw steht zusätzlich die Messreihe „2 Fahrzeuge" (12 Kunden) daneben.
- **Die Vergleichsreihen hängen nicht an der Kundenzahl des Reglers:** bei jeder Kundenzahl stehen die vorgerechneten Reihen in Live-Größe (10 Kunden, 2 Lkw) und in der Hauptgröße (18 Kunden, 3 Lkw) daneben, die Größe steht
  an jeder Zahl.

## Modell

800 × 800 km, Depot in der Mitte, Kunden mit Bedarf 1 bis 10 und Service 30 bis 60 Minuten, 2 Lkw (Live; die Hauptmessreihe: 18 Kunden, 3 Lkw), Kapazität so, dass die Bedarfssumme 80 % der Flottenkapazität ist,
Luftlinie, 75 km/h. **Weiche Zeitfenster**: 40 EUR je Stunde Verspätung je Stopp; die Fenster liegen um die Servicebeginne einer regelfreien Referenztour (keine: 0 % der Kunden, locker 40 % · 12 h, mittel 60 % · 8 h,
eng 80 % · 4 h), deshalb hat die regelfreie Basis 0 Verspätung (Konstruktion). **F, Fahrerregeln:** nach 4,5 h Lenkzeit 45 min Pause am Stück, höchstens 9 h Lenkzeit je Schicht, danach 11 h Tagesruhe (Fahrzeug steht, 100 EUR
Übernachtung); Pause oder Ruhe dürfen freiwillig früher genommen werden, am Kunden und an jeder Ladesäule. **E, Elektro-Lkw:** Reichweite 400 km bei vollem Akku (Start voll), 12 feste Ladesäulen, Laden nur dort (Umweg,
Zeit); „typische Ladung" = 60 % der Reichweite in 20 / 45 / 90 min, proportional zur Energie; Pause am Lader: Halt dauert max(45 min, Ladezeit); Tagesruhe am Lader: Akku danach voll. **Kosten (EUR):** 0,70/km (Energie
neutral: gemessen wird, was Reichweite und Ladezwang kosten, nicht der Energiepreis), 32/h bezahlte Fahrerzeit (auch Pausen, Warten, Laden), 15/h Fahrzeugzeit (auch Stillstand), 100 je Tagesruhe, 40/h Verspätung.
**Wechselwirkung** I = Kosten(F+E) − Kosten(F) − Kosten(E) + Kosten(ohne Regeln), in Prozent der regelfreien Kosten; I < 0: die Kombination ist billiger als die Summe der Einzelkosten. Formal im Expander „📐 Mathematische
Formulierung" der App.

**Modellzuordnung:** CVRP mit Zeitfenstern plus eine Ressourcenschicht entlang der Route (Lenkzeit-Zähler, Akkustand). Alle Regeln aus fällt **exakt** auf die Bewertung der `vrp_demo` zurück (Test, Kopie ihrer
Bewertungsfunktionen in `tests/vrp_reference.py`).

## Methodik

- **⏱️ Fahrplan-Evaluator** (`fv_evaluator.py`): gegeben eine Stoppfolge, der **kostenoptimale Fahrplan** (Ladestopps, Ladeumfang, Pausen, Ruhen) per Label-Setting-Dynamik mit Pareto-Dominanz über Kosten, Zeit, Lenkzeit-Zähler und
  Akkustand (kleine eps-Toleranzen für die Geschwindigkeit). In der Vorab-Messung lag der Fehler gegen den exakten Wert bei höchstens 0,18 % je Route (30 Routen), im Test gilt: nie billiger als der exakte Wert.
  Das ist die eigentliche Neuentwicklung.
- **🔎 Tourensuche** (`fv_search.py`): Savings- und Einfüge-Starts, Relocate, Swap, 2-opt, 2-opt*, kleine ILS – **alles mit dem Evaluator der jeweiligen Zelle**, die Touren passen sich also an die Regeln an. Nur so wird der
  Preis der Regeln gemessen, nicht die Nachbewertung fester Touren. Die vier Zellen (ohne Regeln, F, E, F+E) teilen sich einen Lösungspool.
- **➕ Wechselwirkung I** mit Standardfehler über gepaarte Instanzen; **Urteil in drei Zuständen** (Mittel mehr als 2 Standardfehler von 0 entfernt: billiger oder teurer als die Summe, sonst nicht von additiv zu unterscheiden).
- **🔁 Fest oder neu geplant**: die regelfreien Touren unter den Regeln nachbewertet gegenüber neu geplanten Touren.
- **Meldung der Live-Instanz** mit Schwelle **2 % der regelfreien Kosten** (Suchrauschen, siehe Befunde): darunter „praktisch additiv".

**Kernlogik unverändert übernommen**: `fv_model.py`, `fv_evaluator.py` und `fv_search.py` stammen aus `tourenplanung-planung/messreihe_fernverkehr/fern.py` – dort gegen alle Checks aus `check.py` verifiziert, hier rein
mechanisch auf drei Module verteilt und als Tests übernommen. Nur Standardbibliothek, kein Solver.

## Befunde (gemessen, keine Behauptungen)

Alle Zahlen stammen aus den vorgerechneten Messreihen (`data/fv_results.json`, erzeugt aus `tools/sweep.py` und `tools/dump_sweep.py`) und sind in `tests/test_claims.py` nachgerechnet. Mittel ± Standardfehler in Prozent der
regelfreien Kosten, gepaart je Instanz; 18/3 bedeutet 18 Kunden und 3 Lkw (60 Instanzen, wenn nicht anders angegeben), 10/2 bedeutet 10 Kunden und 2 Lkw (Live-Größe).

| Frage | Befund | Test |
|---|---|---|
| Was kosten die Regeln (18/3, Zeitfenster mittel)? | Fahrerregeln **+39,7 ± 1,1 %**, Elektro **+21,9 ± 0,6 %**, beides **+69,5 ± 2,1 %**; ohne Zeitfenster +21,1 ± 0,2 / +18,1 ± 0,4 / +38,3 ± 0,5 % | `test_claims.py::test_what_the_rules_cost` |
| Ist die Überlappung von Pause und Laden real? | Ja: 63 % der Pausen liegen an einer Ladesäule (18/3, ohne Fenster), im Mittel 261 Lademinuten je Flottenlösung laufen „gratis" in der Pause, 2,9 von 4,1 Tagesruhen liegen an einer Säule | `::test_the_overlap_is_real` |
| … aber addieren sich die Kosten trotzdem? | Ohne Zeitfenster praktisch ja: I = **−0,9 ± 0,3 %** (bei 65 % der Instanzen I < 0; rund 2 % der Summe der Einzelkosten). Der Gewinn steckt in der Fahrerzeit (−153 ± 7 EUR), wird aber von mehr Übernachtungen (+68 ± 7 EUR) und Fahrzeugzeit (+41 ± 10 EUR) fast aufgezehrt | `::test_without_time_windows_the_costs_nearly_add` |
| Mit Zeitfenstern? | Die Kombination ist **teurer** als die Summe: I = **+7,9 ± 1,0 %**, nur bei 15 % der Instanzen I < 0. Die Betriebskosten allein bleiben additiv (I = +0,6 ± 0,9 %), der Rest ist Verspätung (+398 ± 56 EUR). Die Erklärung „Verspätungen schaukeln sich über die Folgestopps auf" ist abgeleitet, nicht getrennt gemessen | `::test_with_time_windows_the_combination_is_dearer` |
| Hängt das Vorzeichen an der Ladezeit? | Ohne Fenster (typische Ladung 20 / 45 / 90 min): I = +1,6 ± 0,3 / −0,9 ± 0,3 / **−4,8 ± 0,3 %** (bei 90 min in 100 % der Instanzen I < 0). Mit Fenstern kehrt sich die Reihenfolge um: +11,3 ± 1,2 / +7,9 ± 1,0 / +3,9 ± 1,4 % | `::test_the_sign_depends_on_the_charging_time` |
| Und an der Reichweite (mit Fenstern)? | 600 / 400 / 300 km: I = +2,7 ± 0,5 / +7,9 ± 1,0 / **+18,0 ± 2,0 %** (bei 300 km nur 28 von 40 Lagen auswertbar, eher zu optimistisch) | `::test_range_amplifies_the_effect` |
| Zeitfenster und Flottengröße? | Zeitfenster locker / mittel / eng: +3,1 ± 0,8 / +7,9 ± 1,0 / +10,1 ± 1,6 %; 2 / 3 / 4 Lkw (12 / 18 / 24 Kunden): +4,3 ± 1,2 / +7,9 ± 1,0 / +6,0 ± 1,0 %; Fenster nach einem Regelplan kalibriert: +12,8 ± 0,9 % | `::test_window_tightness_fleet_size_and_calibration` |
| Trägt das auf die Live-Größe (10/2)? | Ja, dasselbe Muster: ohne Fenster −1,5 ± 0,4 %, mit Fenstern +6,4 ± 1,2 %; Ladezeit 20 / 90 min ohne Fenster +1,4 ± 0,5 / −5,5 ± 0,5 %; Reichweite 600 / 400 / 300 km +3,0 ± 0,8 / +5,3 ± 1,2 / +12,6 ± 2,7 % (29 von 40 Lagen) | `::test_the_pattern_carries_to_the_live_size` |
| Ändern unbezahlte Pausen das Vorzeichen? | Nein. Ohne Fenster wird I stärker unteradditiv (−2,9 ± 0,3 statt −0,9 %), mit Fenstern schwächer überadditiv (+5,5 ± 1,0 statt +7,9 %); die Ladezeit-Umkehr bleibt (90 min: −7,0 ± 0,3 %, 20 min: +0,5 ± 0,3 %, dort nicht mehr von 0 unterscheidbar) | `::test_unpaid_pauses_keep_the_sign` |
| Wie stark hängt es an der Verspätungsstrafe? | 20 / 40 / 80 EUR/h (je 40 Instanzen, mit Fenstern): I = +4,6 ± 0,7 / +8,4 ± 1,2 / +16,4 ± 2,2 % – fast linear in der Strafe; die Betriebskosten allein bleiben klein (höchstens 2 %). Das Vorzeichen hängt nicht an der Strafe, die Größe schon | `::test_the_penalty_scales_the_size_not_the_sign` |
| Kann man alte Touren einfach nachbewerten? | Nein: mit Zeitfenstern ergibt die Nachbewertung der regelfreien Touren I = +18,9 ± 1,4 % statt +7,9 ± 1,0 % (10/2: +12,8 ± 1,5 statt +6,4 ± 1,2 %): die Wechselwirkung wird mehr als doppelt überschätzt | `::test_re_evaluating_old_tours_overestimates` |
| Wie zuverlässig ist die Einzelinstanz? | Nur die Zelle F+E rauscht (Live-Größe, zwei Such-Seeds, 60 Instanzen: bei 7 von 60 verschieden, 95. Perzentil des Unterschieds von I 2,1 % der regelfreien Kosten, Maximum 16,2 %). Die Suche findet F+E höchstens zu teuer, nie zu billig: „billiger" ist robust, „teurer" kann ein Suchartefakt sein. Daraus die Meldungsschwelle von 2 % | `::test_search_noise_gives_the_two_percent_threshold` |
| Wie oft meldet die Schwelle was? | Auf den einzelnen Instanzen (10/2, Schwelle 2 %): mit Fenstern billiger 20 % / praktisch additiv 17 % / teurer 63 %; ohne Fenster 57 % / 30 % / 13 % | `::test_message_states_on_single_instances` |

## Ehrliche Grenzen

- **Stark stilisiert:** Luftlinie statt Straßennetz, konstante Geschwindigkeit, ein Depot, alle Lkw starten gleichzeitig mit vollem Akku und frischem Fahrer, Rückkehr ins Depot ohne Ladepflicht.
- **Die Kostenparameter sind erfunden, nicht kalibriert** (0,70 EUR/km, 32 EUR/h, 15 EUR/h, 100 EUR je Nacht, 40 EUR/h Verspätung): Prozentwerte sind Größenordnungen, keine Euro-Aussagen; besonders alles mit Verspätung hängt
  an den 40 EUR/h (gemessen: die Größe skaliert fast linear mit der Strafe, das Vorzeichen bleibt).
- **Pausen zählen als bezahlte Fahrerzeit** (Grundannahme). Die Sensitivität mit unbezahlten Pausen ist vorgerechnet und ändert das Vorzeichen nicht; sie ist bewusst **kein Regler**.
- **EU-Regeln vereinfacht:** keine 15+30-Aufteilung der Pause, keine 10-Stunden-Tage, keine Wochenruhe und Wochenlenkzeit, keine Uhrzeiten und Öffnungszeiten; keine juristische Aussage.
- **Ladeinfrastruktur vereinfacht:** Ladeleistung linear (keine Kurve), keine Wartezeit an der Säule, jede Säule beliebig oft nutzbar, Energiepreis neutral (kein Vergleich Diesel gegen Strom).
- **Weiche Zeitfenster sind eine Modellwahl:** harte Fenster wären mit Regeln massenhaft unzulässig, dann gäbe es keine Kostenmessung. Die Fenster sind an einer regelfreien Referenztour kalibriert (Sensitivität mit Regelplan:
  dieselbe Richtung, I = +12,8 ± 0,9 %).
- **Die Tourensuche ist eine Heuristik**, kein Optimalitätsbeweis für ganze Lösungen (nur für die Fahrpläne je Route, an Mini-Instanzen gegen Brute-Force). Einzelne Instanzen können deutlich danebenliegen (Live-Größe, zwei Such-Seeds: Maximum des Unterschieds von I 16,2 % der regelfreien Kosten);
  Aussagen tragen die Mittelwerte über 40 bis 60 Instanzen.
- **Ausgeschlossene Lagen:** bei 300 km Reichweite sind nur gut erreichbare Lagen zulässig (in der Vorab-Messung etwa 20 % der Zufallslagen mit 18 Kunden, nicht Teil der CI-Tests); die Messreihe wertet dort 28 von 40 (18/3) bzw. 29 von 40 Instanzen (10/2) aus, die
  ausgeschlossenen sind die schwierigeren Lagen. Die 300-km-Zahlen sind eher zu günstig.
- **Live-Instanz und Messreihe haben verschiedene Größen** (6 bis 12 Kunden mit 2 Lkw gegen 10/2 und 18/3): jede Zahl trägt ihre Größe. Andere Kundenzahlen als 10 (und 12 mit Standardstufen) haben keine eigene Messreihe.
- **Die gezeigte Instanz ist ein Einzelfall:** der Seed bestimmt nur Karte, Fahrplan und die vier Kennzahlen; die Preset-Seeds liegen außerhalb der Stichprobe der Messreihe (`tools/tune_presets.py`) und zeigen den Zustand,
  der in der Messreihe häufig ist.
- **Stafette nicht enthalten** (siehe unten): in der Vorab-Messung der größte Einzeleffekt, aber vollständig von zwei erfundenen Kostenparametern und den Zeitfenstern getrieben.

## Verwandte Demos mit demselben mathematischen Modell

Verschiedene Themen im Portfolio teilen (fast) dasselbe Modell. Vor einer neuen Demo-Idee deshalb das Modell vergleichen, nicht die Kulisse (Stand 2026-09-24):

- **`vrp_demo`** – das **Basismodell**: CVRP mit Zeitfenstern, dort ein Vergleich von Tourenheuristiken. Hier bleibt das Basismodell und bekommt eine Ressourcenschicht entlang der Route (Lenkzeit-Zähler, Akkustand); mit allen
  Regeln aus ist die Bewertung exakt die der `vrp_demo` (`tests/test_checks.py::test_all_rules_off_equals_the_vrp_demo_evaluation`).
- **`linehaul-demo`** – der Nachbar im Transport-Thema (Hauptlauf-Netz mit festen Linien); Netzwerkdesign statt Fahrplan je Tour, deshalb verlinken statt wiederholen.
- **`slow-steaming-demo`** – die **Geschwindigkeit** als Entscheidung; hier bewusst nicht Teil des Modells (konstant 75 km/h). Die Kopplung von Geschwindigkeit und Fahrerregeln wäre ein eigenes Stück.
- **`leercontainer-demo`** – der **Bestandsausgleich**; hier ebenfalls bewusst nicht Teil des Modells.
- **Das Muster „starr gegen reaktiv"** (`fahrzeugflotte-demo`, `robuste-kaiplatz-demo`, `hofrobust-demo`: starrer Vorausplan gegen reaktives Nachplanen unter Störung) taucht hier in verwandter, aber anderer Form auf:
  „regelfreie Touren nachbewertet" gegen „neu geplant" beim **Regelwechsel** (keine Störung). Der Befund – Nachbewerten überschätzt die Wechselwirkung mit Zeitfenstern mehr als doppelt – ist ein eigener Befund, keine
  Dopplung.
- **Stafette und Fahrerdienstplan** wäre der mögliche **Folgeausbau**: Fahrerwechsel an Relaispunkten wirkt nur zusammen mit Fahrerregeln, ein echter Stafettenverkehr ist Dienstplanung (Fahrerpool, Heimatbasis,
  Schichtgrenzen), also ein zweites Modell (Crew-Scheduling) auf der Tourenplanung.

## Tests

`python -m pytest tests/ -v` – 542 Tests, rund 3 bis 4 Minuten (davon etwa eine Minute die Modell-Checks und etwa eine Minute AppTests). Zusammensetzung:

- **Korrektheit des Fahrplan-Modells** (`test_checks.py`, Helfer `tests/fv_checks.py`): alle Checks aus `messreihe_fernverkehr/check.py` in verkleinerter Fassung – alle Regeln aus == Bewertung der `vrp_demo`; Fahrplan-DP == unabhängiger
  Tick-Simulator mit Plan-Enumeration (Brute-Force, nie schlechter, gleich); Fahrplan-Validator (Lenkzeiten, Akku, Pausen- und Ruhelänge, Zeitlinie lückenlos, Kosten aus Ereignissen == Evaluatorkosten); jeder Schalter greift;
  Monotonie; Suche gültig, deterministisch, passt die Touren an; Pool-Konsistenz. Das **volle Bau-Gate** (`python tools/check_full.py`, 3,9 Mio. simulierte Pläne) lief einmal lokal: 125 Sekunden, alle 11 Checks bestanden, mit denselben Zahlen wie in der Messreihe (150 Touren gegen `vrp_demo`, 178 Fahrpläne im Validator, 46 + 8 Brute-Force-Fälle, 3 916 830 simulierte Pläne, Evaluator-Fehler höchstens 0,18 %).
- **Bitgleichheit zum Original** (`test_frozen_reference.py`, `tests/data/fv_reference.json`): drei Kleininstanzen (Kosten und Touren je Zelle, auch die Stafette-Zellen) und Instanz Seed 55 der Messreihe (10 Kunden) exakt wie
  im Original `fern.py` bzw. wie `tools/sweep.py` sie auf 16 Kernen gerechnet hat – der Nachweis, dass die Aufteilung von `fern.py` in drei Module nichts an der Logik geändert hat.
- **Bausteine** (`test_model_units.py`): Parameter, Geometrie, Zeitfenster-Kalibrierung, Evaluator an Handrechnungen (exakte Kosten einer Route mit Pause, Tagesruhe, Ladung), Kennzahlen aus Ereignissen, Konstruktion, Lokalsuche.
- **Live-Instanz** (`test_live.py`): Seed-Auswahl (nur gültige Lagen, gleiche Konvention wie die Messreihe), alle Zeitfenster-Stufen, Reichweite 300 / 600, 6 und 12 Kunden, Fahrpläne gegen den unabhängigen Validator,
  Kostenzerlegung schließt, Determinismus, echte Lage ohne zulässige Elektro-Lösung; **Zweig-Tests gegen die Null-Spalte** (Pausen am Lader, freie Lademinuten, Warten, Verspätung nur mit Fenstern).
- **Messreihe und Urteil** (`test_results.py`, `test_claims.py`): Struktur und Invarianten der Ergebnisdatei (Zerlegung schließt, Anteile summieren sich zu 1, keine Rohdaten, keine Stafette), Urteil an der 2-Standardfehler-Grenze,
  Meldungszustand an der 2-%-Schwelle, Achsen, Wahl der passenden Reihe; **jede Zahl dieser README**.
- **Presets** (`test_stories.py`, `test_preset_stories.py`, `test_presets.py`): jedes Abnahmekriterium kippt an künstlichen Werten genau an seiner Schwelle, Vorzeichen-Kriterien nur zusammen mit der Standardfehler-Bedingung; die echten
  Presets erfüllen sie auf den Messreihen, und die gezeigte Live-Instanz erzählt qualitativ dieselbe Geschichte; Permalink-Parsing (Begrenzen, Einrasten, Müll).
- **Lücken aus dem Fehler-Einbau-Test** (`test_mutation_gaps.py`): Auswahl der Messreihe, Achsen, Sitzungszustand ohne App, Meldungswortlaut, PDF-Zahlen.
- **Fahrpläne und Figuren** (`test_schedule.py`, `test_visualization.py`): Halteliste und Zeitstrahl an Handbeispielen, Zeitlinie lückenlos, alle Achsen `fixedrange`, Inhalt der Figuren gegen die Daten.
- **PDF** (`test_pdf_export.py`): Sonderzeichen-Bereinigung (fpdf2 stürzt bei „–", „€", Emoji und dem Unicode-Minus ab – mit den genauen Zeichen getestet), jede Zelle, unzulässige Zellen, Seitenumbruch.
- **Werkzeuge** (`test_tools.py`): die ganze Kette Rohzeilen → `dump_sweep` → `build_results` → Auswertung auf synthetischen Rohdaten (die echte Messreihe läuft nie in der CI).
- **End-to-End** (`test_app.py`, `test_app_real.py`, AppTest): Skelett und Footer, jedes Preset, Permalink, alle Regler an Min und Max, kein toter Regler, alle drei Meldungszustände (plus unzulässig), Kernabschnitt, Ansichten, PDF.
  Die Live-Rechnung läuft in AppTest nur mit 6 bis 8 Kunden, ohne Wall-Clock-Assertions.

Zusätzlich ein Fehler-Einbau-Test (`tools/mutation_check.py`, 221 Mutanten über `fv_model`, `fv_evaluator`, `fv_search`, `fv_live`, `fv_results`, `fv_stories`, `fv_presets`, `fv_schedule`, `fv_visualization`, `fv_pdf_export`, `fv_ui_panel`, `fv_constants` und `tools/build_results.py`): **221 gefunden, 0 überlebt, 0 Fehler in der Mutantenliste.** Das Werkzeug prüft sich selbst: vor dem Lauf muss die **unveränderte Kopie** die Tests bestehen (sonst Abbruch); die Kopie enthält dafür auch `data/` und
`README.md`, die `test_results.py` bzw. `test_claims.py` lesen. Sechs gleichwertige Mutanten sind im Werkzeug begründet nicht geführt (Code ohne Wirkung, z. B. die Klammer der Koordinaten auf das Gebiet).

**Beim Bau gefundene Testlücken (per Mutationstest, dann geschlossen; alle Tests dazu in `test_mutation_gaps.py` und den Modul-Testdateien):** der erste Lauf ließ 33 Mutanten überleben (er brach danach bei der Ausgabe eines Emoji ab; das Werkzeug gibt jetzt UTF-8 aus), der zweite noch 6, der dritte keinen.
Geschlossen wurden unter anderem: (1) Konstruktionsheuristiken, Lokalsuche, Geometrie und Zeitfenster waren nur über Ergebnis-Pools abgesichert, ein anderer Sortier- oder Kapazitätsrand oder ein anderer Suchparameter fiel nicht auf – jetzt sind Geometrie,
Savings-, FFD- und Einfüge-Start, Lokalsuche, `solve` und die Fenster auf 8 Instanzen mit dem Original eingefroren und die Suchparameter als Signatur geprüft; (2) die Auswahl der passenden Messreihe: ein Sensitivitätslauf (unbezahlte Pausen, andere Strafe, Fenster nach Regelplan)
hätte die Hauptreihe ersetzen können, wenn er allein zur Wahl stand – jetzt mit Teilmengen der Daten getestet; (3) die Achsen des Kernabschnitts waren nur an einzelnen Werten geprüft – jetzt Zeile für Zeile; (4) `apply_preset` und der Seed-Knopf liefen nur im AppTest, der im Mutationslauf fehlt – jetzt ohne App
gegen einen Ersatz des Sitzungszustands; (5) das Vorzeichen des Ersparnisbetrags in der Meldung („um 80 EUR billiger" statt „um −80 EUR"), das PDF-Spaltenraster und die Prozente in der PDF-Tabelle; (6) `tools/build_results.py` lief nur mit vier Zellen und ohne ausgeschlossene Lagen: die synthetischen Rohdaten
enthalten jetzt Stafette-Zellen, ausgeschlossene Instanzen mit beiden Gründen und ein Rauschpaar, das bei 2 %, aber nicht bei 3 % kippt; (7) die Live-Rechnung mit einem verschobenen Such-Seed fiel erst auf, als eine Instanz gewählt wurde, auf der der Seed überhaupt etwas ändert.

## Dateistruktur

| Datei | Inhalt | Herkunft |
|---|---|---|
| `app.py` | Streamlit-Hauptablauf: Presets, Sidebar, Hauptansicht, Kernabschnitt, Ansichten, Texte | neu |
| `fv_constants.py` | Regler-Stufen, Zeitfenster-Stufen, Farben, `PRESETS` | neu |
| `fv_presets.py` | `SETTING_SPECS`, Permalink (Begrenzen, Einrasten), Presets, Seed-Knopf | Muster `wfg_presets.py` |
| `fv_model.py` | `Cfg`, `Inst`, `make_geometry`, Hilfen | `fern.py`, unverändert |
| `fv_evaluator.py` | `Ev` (Label-Setting-Fahrplan-Evaluator), `plan_stats`, `cost_from_events` | `fern.py`, unverändert |
| `fv_search.py` | `savings_routes`, `insertion_routes`, `local_search`, `solve`, `solve_all`, `reference_windows`, `make_instance` | `fern.py`, unverändert |
| `fv_live.py` | Live-Instanz: gültige Seeds, vier Zellen, Fahrpläne, Kostenarten, Kennzahlen | neu |
| `fv_results.py` | Laden und Auswerten von `data/fv_results.json`: Urteil in drei Zuständen, Meldungszustand, Achsen, Wahl der passenden Reihe | neu |
| `fv_schedule.py` | Halteliste, Zeitstrahl-Balken, Knotenfolge (reine Funktionen auf den Ereignislisten) | neu |
| `fv_visualization.py` | Karte, Zeitstrahl, Kostenzerlegung, Summe gegen Kombination, Achsen-Grafik, Zerlegung, Annahmen (alle Achsen fest) | neu |
| `fv_ui_panel.py` | Kennzahlen (2 × 2), Meldung, Vergleichstabelle, Karte und Fahrplan, Tabellen des Kernabschnitts | Muster `wfg_ui_panel.py` |
| `fv_pdf_export.py` | Fahrplan-PDF (`fpdf2`, Sonderzeichen-Bereinigung) | Muster `wfg_pdf_export.py` |
| `fv_stories.py` | Abnahmekriterien der Presets | Muster `wfg_stories.py` |
| `data/fv_results.json` | Aggregate der Messreihen (Mittel, Standardfehler, Median, Quartile, Zerlegungen, Mechanismus, Anteile der Meldungszustände) | `tools/build_results.py` |
| `tools/sweep.py`, `tools/dump_sweep.py` | Reproduktion der Messreihe (52 Minuten auf 16 Kernen, nicht in der CI) | `messreihe_fernverkehr/`, Importe angepasst |
| `tools/build_results.py` | erzeugt `data/fv_results.json` aus den Ausgaben von `sweep.py` und `dump_sweep.py` | neu |
| `tools/freeze_reference.py` | erzeugt `tests/data/fv_reference.json` mit dem unveränderten Original `fern.py` | neu |
| `tools/check_full.py` | das volle Bau-Gate (alle Checks in Originalgröße) | neu |
| `tools/tune_presets.py` | Suche repräsentativer Anzeige-Seeds je Preset | neu |
| `tools/mutation_check.py` | Fehler-Einbau-Test (parallel, je Mutant eine Kopie, mit Selbstprüfung) | Muster `wfg` |
| `tests/` | siehe oben; `vrp_reference.py` ist eine Kopie der Bewertungsfunktionen der `vrp_demo` | neu |

## Bewusst nicht umgesetzt

Die folgenden Erweiterungen sind ausdrücklich nicht Teil von Version 1 – jede würde Größenordnung und Aussage verschieben und gehört als Ausbau genannt, nicht stillschweigend eingebaut:

- **Stafette und Fahrerdienstplan** (Fahrerwechsel an Relaispunkten): wirkt nur zusammen mit F, ihr Nutzen hängt an den erfundenen Wechselkosten (Vorab-Messung, `ERGEBNIS.md` der Messreihe, nicht Teil der CI-Tests: mit Fenstern
  −14,6 % bis −5,2 % je nach Kosten, ohne Fenster im teuren Fall in keiner der 40 Instanzen genutzt) – ein zweites Modell, kein weiterer Zähler. Die Modellfelder (`Cfg.t_swap`, `c_swap`, `c_ret`) und die Logik bleiben in `fv_evaluator.py`, die App zeigt sie nicht.
- **Energiepreis und Vergleich Diesel gegen Strom** (der Energiepreis ist neutral).
- **Ladeleistungskurve und Wartezeit an der Säule** (Laden ist linear, keine Warteschlange).
- **Unbezahlte Pausen als Regler** (vorgerechneter Vergleich statt Regler: das Vorzeichen bleibt).
- **Wochenruhe und Wochenlenkzeit**, 15+30-Aufteilung der Pause, 10-Stunden-Tage.
- **Geschwindigkeitswahl** (bleibt bei `slow-steaming-demo`), **mehrere Depots**, **Straßennetz statt Luftlinie**.
- **Kalibrierung an echten Daten** (Kosten, Zeitfenster, Ladesäulen sind synthetisch).
- **Live-Rechnung für die Messreihe**: 60 Instanzen mit 18 Kunden brauchen 52 Minuten auf 16 Kernen und werden nie im Browser gerechnet.

## Reproduktion der Messreihe

Nicht in der CI, nicht im Browser: die Läufe brauchten **52 Minuten Wanduhrzeit auf 16 Kernen** (18 Konfigurationen der Hauptmessreihe, dazu die Restmessungen in Live-Größe, mit unbezahlten Pausen, mit anderen
Verspätungsstrafen und das Suchrauschen).

```bash
python tools/sweep.py list                      # alle Konfigurationen
PROCS=14 python tools/sweep.py all              # rechnet raw_<Konfiguration>.jsonl (setzt unterbrochene Läufe fort), Seeds wie in der Seed-Konvention der Datei
python tools/sweep.py noise_live && python tools/sweep.py noise_ext   # Suchrauschen auf Live-Größe
python tools/dump_sweep.py                      # aggregiert -> sweep_data.json, sweep_report.txt
python tools/build_results.py                   # -> data/fv_results.json
```

`tools/*.jsonl`, `sweep_data.json` und `sweep_report.txt` stehen in der `.gitignore` (Rohdaten, 5 MB). Die Seed-Konvention: Instanz *i* einer Messreihe = *i*-ter gültiger Seed *s* (aufsteigend ab 0; gültig = jeder Kunde per
Rundfahrt mit R = 300 km erreichbar); Geometrie und Bedarf `Random(s·1000 + n)`, Fensterlage `Random(s·77 + 3)`, Referenztour für die Fenster Suche mit Seed `s·31 + 7`, Tourensuche `solve_all(..., seed = s)`. Ein Wiederholungslauf
liefert bitgleiche Kosten und Touren (Test: Seed 55 der Messreihe).

## Lokal ausführen

```bash
pip install -r requirements-dev.txt
streamlit run app.py
```

Tests: `python -m pytest tests/ -v`. Volles Bau-Gate: `python tools/check_full.py`. Preset-Abstimmung: `python tools/tune_presets.py [erster_Seed] [letzter_Seed]`. Fehler-Einbau: `python tools/mutation_check.py [Modul] [--jobs N]`.

---

Gebaut mit Streamlit, Plotly und fpdf2.
