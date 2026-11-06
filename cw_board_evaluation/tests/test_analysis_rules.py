"""Draft-signal thresholds (app.domain.analysis_rules): defaults, per-run values, limits. No database."""

from __future__ import annotations

import pytest

from app.domain import analysis_rules as R


def test_defaults_when_nothing_is_given() -> None:
    assert R.resolve_thresholds(None) == R.resolve_thresholds({}) == R.DEFAULT_THRESHOLDS
    assert R.DEFAULT_THRESHOLDS == {"theme_strength_mean": 4.2, "item_strength_mean": 4.5,
                                    "concern_mean": 2.5, "self_peer_gap": 1.0}


def test_given_values_replace_only_their_own_default() -> None:
    got = R.resolve_thresholds({"concern_mean": 2, "self_peer_gap": None})
    assert got == {**R.DEFAULT_THRESHOLDS, "concern_mean": 2.0}


@pytest.mark.parametrize("given, message", [
    ({"concern_mean": 0.5}, "between 1 and 5"),
    ({"theme_strength_mean": 6}, "between 1 and 5"),
    ({"self_peer_gap": 0}, "between 0.1 and 4"),
    ({"concern_mean": "low"}, "must be a number"),
    ({"effectiveness": 4}, "Unknown threshold"),
])
def test_out_of_range_or_unknown_thresholds_are_refused(given, message) -> None:
    with pytest.raises(ValueError, match=message):
        R.resolve_thresholds(given)


def test_a_run_without_recorded_thresholds_used_the_defaults() -> None:
    assert R.thresholds({"min_raters": 3}) == R.DEFAULT_THRESHOLDS
    assert R.thresholds({"thresholds": {"concern_mean": 2.0}})["concern_mean"] == 2.0
