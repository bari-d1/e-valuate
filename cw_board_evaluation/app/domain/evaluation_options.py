"""
app.domain.evaluation_options
-----------------------------
Per-evaluation methodology options a consultant can switch per engagement.
Stored on evaluations.options (JSONB); missing keys take their default.

- peer_mode: "core" (default) asks every director the five core peer items
  about each colleague plus deep sets from those best placed to judge;
  "full" restores the original full peer forms (PEER-NED, PEER-EXEC,
  CHAIR-PEER) for every director.
"""

from __future__ import annotations

from typing import Any, Dict, List

EVALUATION_OPTIONS: List[Dict[str, Any]] = [
    {
        "key": "peer_mode",
        "label": "Peer assessment",
        "values": [
            {"key": "core", "label": "Core five about each colleague, plus deep sets from those best placed to judge"},
            {"key": "full", "label": "Full original peer forms for every director"},
        ],
        "default": "core",
    },
]
OPTIONS_BY_KEY: Dict[str, Dict[str, Any]] = {o["key"]: o for o in EVALUATION_OPTIONS}


class OptionError(ValueError):
    pass


def option_values(key: str) -> List[str]:
    return [v["key"] for v in OPTIONS_BY_KEY[key]["values"]]


def effective_options(stored: Dict[str, Any] | None) -> Dict[str, Any]:
    """Every option's value: the stored one, or the default."""
    stored = stored or {}
    return {o["key"]: stored.get(o["key"], o["default"]) for o in EVALUATION_OPTIONS}


def validate_options(values: Dict[str, Any]) -> Dict[str, Any]:
    """Normalised options to store, or raise OptionError."""
    if not isinstance(values, dict):
        raise OptionError("Options must be an object.")
    out: Dict[str, Any] = {}
    for key, value in values.items():
        if key not in OPTIONS_BY_KEY:
            raise OptionError(f"Unknown option {key!r}. Known options: {', '.join(OPTIONS_BY_KEY)}.")
        if value not in option_values(key):
            raise OptionError(f"{key} must be one of: {', '.join(option_values(key))}.")
        out[key] = value
    return out
