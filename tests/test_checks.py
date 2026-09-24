"""Die Korrektheits-Checks des Fahrplan-Modells (tests/fv_checks.py, Übernahme von check.py aus messreihe_fernverkehr) in der
verkleinerten CI-Fassung. Die volle Fassung (3,9 Mio. simulierte Pläne für die Brute-Force-Referenz, alle Instanzen) läuft einmal
lokal als Bau-Gate: `python tools/check_full.py`.

Was die Checks beweisen: alle Regeln aus == Bewertung der vrp_demo (tests/vrp_reference.py, Kopie); Fahrplan-DP == unabhängiger
Tick-Simulator mit Plan-Enumeration (nie schlechter, gleich); Fahrplan-Validator (Lenkzeiten, Akku, Pausen, Ruhen, Zeitlinie);
jeder Schalter greift; Monotonie; Suche gültig, deterministisch, passt die Touren an."""
import fv_checks as K


def test_all_rules_off_equals_the_vrp_demo_evaluation():
    K.check_alloff_equals_vrp_demo(n_inst=6)


def test_schedule_validator_and_cost_recomputation():
    K.check_validator_and_cost_recompute(n_inst=3)


def test_every_switch_bites():
    K.check_switches_bite()


def test_unpaid_pause_option():
    K.check_unpaid_pause()


def test_brute_force_reference_chain_one():
    K.check_brute_force(n_seeds=2, n_multi=1, n_unpaid=2)


def test_brute_force_reference_chain_two():
    K.check_brute_force_chain2(n_e=2, n_fe=1)


def test_dominance_does_not_cut_anything():
    K.check_dp_dominance_off(n=3)


def test_monotonicity_and_eps_accuracy():
    K.check_monotonicity_and_eps(n_inst=3)


def test_search_is_valid_and_deterministic():
    K.check_search(n_inst=1)


def test_search_adapts_the_tours_to_the_rules():
    K.check_adaptation(n_seeds=3)


def test_solve_all_pool_consistency():
    K.check_solve_all(n_inst=1)
