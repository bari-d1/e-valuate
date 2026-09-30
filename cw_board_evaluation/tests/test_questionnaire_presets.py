"""Questionnaire seed presets (no DB)."""

from app.questionnaires.presets import SEED_PRESETS, get_questions_for_preset, list_preset_names


def test_list_preset_names():
    names = list_preset_names()
    assert "default" in names
    assert "expanded" in names


def test_preset_sizes():
    assert len(SEED_PRESETS["default"]) == 10
    assert len(SEED_PRESETS["expanded"]) == 20


def test_get_questions_copy():
    a = get_questions_for_preset("default")
    b = get_questions_for_preset("default")
    assert a == b
    assert a is not b
