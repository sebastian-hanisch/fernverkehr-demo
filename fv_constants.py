"""Konstanten der Fernverkehrs-Demo (Fahrerregeln und Elektro-Lkw in der Tourenplanung).

Modell und Zahlen aus messreihe_fernverkehr/ (siehe tourenplanung-planung/plan_fernverkehr.html und
messreihe_fernverkehr/ERGEBNIS.md). Fachmodell-Konstanten (Kosten, Lenk- und Ruhezeiten, Ladesäulen, Geschwindigkeit) sind
FEST (fv_model.Cfg); einstellbar sind Kunden, typische Ladezeit, Reichweite, Zeitfenster und der Seed. Ladezeit, Reichweite und
Zeitfenster sind bewusst auf die GEMESSENEN Stufen festgelegt: zu jeder Reglerstellung gibt es (soweit gemessen) eine vorgerechnete
Vergleichsspalte, und weil die Live-Instanz immer alle vier Zellen (ohne Regeln, F, E, F+E) rechnet, ist kein Regler jemals
wirkungslos."""

# --- Regler (Plan Abschnitt 5) -----------------------------------------------------------------------------------------
CUSTOMERS_RANGE, CUSTOMERS_DEFAULT = (6, 12), 10       # Live-Instanz mit 2 Lkw; Rechenzeit wächst stark, deshalb höchstens 12
LIVE_TRUCKS = 2
CHARGE_OPTIONS, CHARGE_DEFAULT = (20, 45, 90), 45      # min für 60 % der Reichweite ("typische Ladung")
RANGE_OPTIONS, RANGE_DEFAULT = (300, 400, 600), 400    # km Vollakku-Reichweite
WINDOW_OPTIONS, WINDOW_DEFAULT = ("keine", "locker", "mittel", "eng"), "mittel"
# Anteil der Kunden mit Zeitfenster und Fensterbreite in Stunden (Zeitfenster um die Servicebeginne einer regelfreien Referenztour)
WINDOW_PARAMS = {"keine": (0.0, 8.0), "locker": (0.4, 12.0), "mittel": (0.6, 8.0), "eng": (0.8, 4.0)}
# Der Seed ist die Nummer der Instanz: der i-te GÜLTIGE Seed (jeder Kunde per Rundfahrt mit der Reichweite erreichbar). Das Suchen
# des i-ten gültigen Seeds kostet etwa 3 ms je gültigem Seed; bis 299 bleibt es unter einer Sekunde je Einstellung (der Plan sah
# 0 bis 9999 vor, das hätte bis zu 30 s Suchzeit vor der eigentlichen Rechnung bedeutet).
SEED_RANGE, SEED_DEFAULT = (0, 299), 211

# --- Live-Rechnung -------------------------------------------------------------------------------------------------------
LIVE_RESTARTS = 3                # Neustarts der Tourensuche je billiger Zelle (wie in messreihe_fernverkehr/timing_live.py)
CACHE_ENTRIES = 24               # Ergebnisse je Einstellung (st.cache_data)
# Gemessene Rechenzeit der vier Zellen (Sekunden, dieses Gerät, messreihe_fernverkehr/timing_live.txt); dient nur der Anzeige.
LIVE_SECONDS = {6: 0.5, 7: 0.7, 8: 1.0, 9: 3.0, 10: 5.0, 11: 7.0, 12: 10.0}

# --- Meldungen und Urteile (Plan Abschnitt 6) -----------------------------------------------------------------------------------
THRESHOLD_PCT = 2.0              # |I| bis 2 % der regelfreien Kosten: "praktisch additiv" (AP 0: gepooltes 95. Perzentil des Suchrauschens)
SE_FACTOR = 2.0                  # ein Vorzeichen gilt als belastbar, wenn |Mittel| > 2 Standardfehler

# --- Zellen ---------------------------------------------------------------------------------------------------------------------
CELL_BASE, CELL_F, CELL_E, CELL_FE = "---", "F--", "-E-", "FE-"
CELLS = (CELL_BASE, CELL_F, CELL_E, CELL_FE)
CELL_COMBOS = {CELL_BASE: (0, 0, 0), CELL_F: (1, 0, 0), CELL_E: (0, 1, 0), CELL_FE: (1, 1, 0)}
CELL_LABELS = {CELL_BASE: "ohne Regeln", CELL_F: "Fahrerregeln (F)", CELL_E: "Elektro (E)", CELL_FE: "beides (F+E)"}
CELL_SHORT = {CELL_BASE: "ohne Regeln", CELL_F: "F", CELL_E: "E", CELL_FE: "F+E"}
VIEW_DEFAULT = CELL_LABELS[CELL_FE]

# --- Kostenarten (Zerlegung) -----------------------------------------------------------------------------------------------------
COST_KEYS = ("km", "fahrer", "fahrzeug", "naechte", "verspaetung")
COST_LABELS = {"km": "Kilometer", "fahrer": "Fahrerzeit", "fahrzeug": "Fahrzeugzeit", "naechte": "Übernachtungen",
               "verspaetung": "Verspätung"}
COST_COLORS = {"km": "#5b6b80", "fahrer": "#2a6fb0", "fahrzeug": "#7d5ba6", "naechte": "#2e7d4f", "verspaetung": "#c0392b"}

# --- Ereignisse im Fahrplan ---------------------------------------------------------------------------------------------------------
EVENT_COLORS = {"drive": "#2a6fb0", "serve": "#5b6b80", "wait": "#c9d1db", "break": "#e0a800", "charge": "#2e7d4f",
                "charge_break": "#8bbf6a", "rest": "#7d5ba6"}
EVENT_NAMES = {"drive": "Fahrt", "serve": "Service beim Kunden", "wait": "Warten", "break": "Pflichtpause (45 min)",
               "charge": "Laden", "charge_break": "Laden in der Pause", "rest": "Tagesruhe"}
TRUCK_COLORS = ("#2a6fb0", "#c0392b")
BASE_COLOR = "#9aa5b4"
SUM_COLORS = ("#2a6fb0", "#2e7d4f")            # F allein, E allein
COMBO_COLOR = "#c77700"
SIZE_COLORS = {"10/2": "#2a6fb0", "18/3": "#c77700"}
CHART_HEIGHT = 380

# --- Größen der Messreihen ----------------------------------------------------------------------------------------------------------------
SIZE_LIVE = (10, 2)              # 10 Kunden, 2 Lkw (60 Instanzen): Vergleichsspalte zur Live-Instanz
SIZE_MAIN = (18, 3)              # 18 Kunden, 3 Lkw (60 Instanzen): Hauptmessreihe

# --- Presets (Plan Abschnitt 7; Abnahmekriterien in fv_stories.py) -----------------------------------------------------------------------
# Der Seed bestimmt nur die GEZEIGTE Instanz (Karte, Fahrplan, die vier Kennzahlen): die Messreihe steht auf anderen Instanzen
# (bei 10 Kunden die Seeds 6 bis 154), die Anzeige-Seeds liegen ausserhalb. Sie kommen aus tools/tune_presets.py: alle vier Zellen
# zulässig, Meldungszustand wie in der Messreihe am häufigsten, Wechselwirkung nah am Mittel der passenden 10-Kunden-Reihe.
PRESETS = {
    "Standard": dict(customers=10, charge=45, range_km=400, window="mittel", seed=211),
    "Ohne Zeitfenster": dict(customers=10, charge=45, range_km=400, window="keine", seed=220),
    "Lange Ladung": dict(customers=10, charge=90, range_km=400, window="keine", seed=228),
    "Kurze Ladung": dict(customers=10, charge=20, range_km=400, window="keine", seed=210),
    "Knappe Reichweite": dict(customers=10, charge=45, range_km=300, window="mittel", seed=206),
}
PRESET_HELP = {
    "Standard": "Der Grundfall: Beide Regeln zusammen sind teurer als die Summe der Einzelkosten, weil sich Verspätungen aufschaukeln.",
    "Ohne Zeitfenster": "Die naheliegende Erwartung: Pause und Laden lassen sich zusammenlegen, das spart etwas - aber kaum.",
    "Lange Ladung": "Bei 90 Minuten Ladezeit wird die Pause fürs Laden gratis: die Kombination ist klar billiger als die Summe.",
    "Kurze Ladung": "Ist die Ladung kürzer als die Pflichtpause, lohnt das Zusammenlegen kaum: sogar ohne Zeitfenster ist die Kombination nicht billiger als die Summe.",
    "Knappe Reichweite": "Je knapper die Reichweite, desto mehr wird Laden zum Zeittreiber: Verspätungen schaukeln sich stärker auf.",
}
