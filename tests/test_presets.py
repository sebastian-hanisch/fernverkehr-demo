"""Regler: Permalink-Parsing (Begrenzen, Einrasten, Müll), Presets innerhalb ihrer Bereiche, Namen und Hilfetexte."""
import pytest

import fv_constants as C
from fv_presets import PRESET_STATE_KEYS, SETTING_SPECS, SettingSpec, bounds, parse_setting


def test_number_range_settings_are_clamped():
    spec = SETTING_SPECS["customers_slider"]
    assert parse_setting(spec, "999") == 12 and parse_setting(spec, "-5") == 6 and parse_setting(spec, "0") == 6
    assert parse_setting(spec, "6") == 6 and parse_setting(spec, "12") == 12 and parse_setting(spec, "9") == 9
    assert parse_setting(SETTING_SPECS["seed_input"], "99999") == C.SEED_RANGE[1]
    assert parse_setting(SETTING_SPECS["seed_input"], "-3") == C.SEED_RANGE[0]


def test_integer_settings_accept_float_text_and_reject_garbage():
    spec = SETTING_SPECS["customers_slider"]
    assert parse_setting(spec, "9.0") == 9 and isinstance(parse_setting(spec, "9.0"), int)
    assert parse_setting(spec, "8.6") == 9
    for garbage in ("abc", "", None, "1e999x"):
        assert parse_setting(spec, garbage) is None


def test_non_finite_values_are_rejected():
    for key in ("customers_slider", "charge_slider", "range_slider", "seed_input"):
        assert parse_setting(SETTING_SPECS[key], "nan") is None
        assert parse_setting(SETTING_SPECS[key], "inf") is None
        assert parse_setting(SETTING_SPECS[key], "-inf") is None


def test_stepped_numbers_snap_to_the_nearest_step_and_ties_go_down():
    charge = SETTING_SPECS["charge_slider"]
    assert [parse_setting(charge, v) for v in ("20", "45", "90", "30", "31", "60", "70", "500", "0")] == [20, 45, 90, 20, 20, 45, 90, 90, 20]
    assert parse_setting(charge, "32.5") == 20 and parse_setting(charge, "32.6") == 45           # Mitte zwischen 20 und 45: die kleinere
    rng = SETTING_SPECS["range_slider"]
    assert [parse_setting(rng, v) for v in ("300", "400", "600", "350", "351", "500", "501", "1000")] == [300, 400, 600, 300, 400, 400, 600, 600]


def test_window_names_are_accepted_case_insensitively_and_unknown_names_ignored():
    spec = SETTING_SPECS["window_slider"]
    assert [parse_setting(spec, w) for w in C.WINDOW_OPTIONS] == list(C.WINDOW_OPTIONS)
    assert parse_setting(spec, " Eng ") == "eng" and parse_setting(spec, "MITTEL") == "mittel"
    assert parse_setting(spec, "sehr eng") is None and parse_setting(spec, "") is None and parse_setting(spec, "3") is None


def test_url_params_are_unique_and_defaults_are_valid():
    assert len({spec.url_param for spec in SETTING_SPECS.values()}) == len(SETTING_SPECS)
    for key, spec in SETTING_SPECS.items():
        if spec.options:
            assert spec.default in spec.options, key
        else:
            assert spec.lo <= spec.default <= spec.hi, key
        assert spec.encoder(spec.default)


def test_encoders_roundtrip_through_parse():
    for key, spec in SETTING_SPECS.items():
        assert parse_setting(spec, spec.encoder(spec.default)) == spec.default, key
    for key, spec in SETTING_SPECS.items():
        for option in (spec.options or (spec.lo, spec.hi)):
            assert parse_setting(spec, spec.encoder(option)) == option, (key, option)


def test_bounds_come_from_the_constants():
    assert bounds("customers_slider") == C.CUSTOMERS_RANGE == (6, 12)
    assert bounds("seed_input") == C.SEED_RANGE
    assert bounds("charge_slider") == (None, None)                                       # Stufenregler haben keine Zahlenbereiche


def test_defaults_equal_the_standard_preset():
    for field, state_key in PRESET_STATE_KEYS.items():
        assert SETTING_SPECS[state_key].default == C.PRESETS["Standard"][field], field
    assert (C.CUSTOMERS_DEFAULT, C.CHARGE_DEFAULT, C.RANGE_DEFAULT, C.WINDOW_DEFAULT) == (10, 45, 400, "mittel")


def test_every_preset_is_within_its_own_widget_options_and_bounds():
    for name, p in C.PRESETS.items():
        assert set(p) == set(PRESET_STATE_KEYS), name
        assert C.CUSTOMERS_RANGE[0] <= p["customers"] <= C.CUSTOMERS_RANGE[1]
        assert p["charge"] in C.CHARGE_OPTIONS and p["range_km"] in C.RANGE_OPTIONS and p["window"] in C.WINDOW_OPTIONS
        assert C.SEED_RANGE[0] <= p["seed"] <= C.SEED_RANGE[1]
        for field, state_key in PRESET_STATE_KEYS.items():                                # rasterkonform: der Permalink ergibt denselben Wert
            spec = SETTING_SPECS[state_key]
            assert parse_setting(spec, spec.encoder(p[field])) == p[field], (name, field)


def test_preset_seeds_are_outside_the_measurement_series_seeds():
    """Die gezeigte Instanz liegt bewusst außerhalb der Stichprobe: die Messreihe mit 10 Kunden nutzt die Seeds 6 bis 154 (Reichweite 300
    als Gültigkeit), die Anzeige-Instanzen sind der 200. gültige Seed und höher."""
    assert C.SEED_DEFAULT >= 200 and all(p["seed"] >= 200 for p in C.PRESETS.values())


def test_preset_names_are_short_enough_for_a_button_label_and_have_help():
    assert all(len(name) <= 32 for name in C.PRESETS)
    assert set(C.PRESET_HELP) == set(C.PRESETS) and all(len(h) > 30 for h in C.PRESET_HELP.values())


def test_there_are_exactly_five_presets_arranged_three_plus_two():
    assert list(C.PRESETS) == ["Standard", "Ohne Zeitfenster", "Lange Ladung", "Kurze Ladung", "Knappe Reichweite"]


def test_the_presets_set_the_settings_their_story_needs():
    p = C.PRESETS
    assert (p["Standard"]["charge"], p["Standard"]["range_km"], p["Standard"]["window"]) == (45, 400, "mittel")
    assert p["Ohne Zeitfenster"]["window"] == "keine" and p["Ohne Zeitfenster"]["charge"] == 45
    assert (p["Lange Ladung"]["charge"], p["Lange Ladung"]["window"]) == (90, "keine")
    assert (p["Kurze Ladung"]["charge"], p["Kurze Ladung"]["window"]) == (20, "keine")
    assert (p["Knappe Reichweite"]["range_km"], p["Knappe Reichweite"]["window"]) == (300, "mittel")
    assert all(x["customers"] == 10 for x in p.values())                                    # Standardgröße der Live-Instanz


def test_setting_spec_defaults_use_plain_text_encoding():
    assert SettingSpec("x", int, 3).encoder(3) == "3"
    assert SETTING_SPECS["window_slider"].encoder("eng") == "eng"


@pytest.mark.parametrize("key", list(SETTING_SPECS))
def test_every_setting_has_a_state_key_used_by_a_preset_field(key):
    assert key in PRESET_STATE_KEYS.values()
