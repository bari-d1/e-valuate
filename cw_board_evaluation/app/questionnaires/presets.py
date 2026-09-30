"""
Deterministic questionnaire seeds for POST .../seed/questions.

Presets are keyed by short names; each maps to a list of question dicts:
  dimension, text, answer_type, weight
"""

from __future__ import annotations

from typing import Any, Dict, List

_DEFAULT_CORE: List[Dict[str, Any]] = [
    {
        "dimension": "Board Composition",
        "text": "The board has an appropriate mix of skills, experience, and independence to oversee the organisation effectively.",
        "answer_type": "rating",
        "weight": 1,
    },
    {
        "dimension": "Board Composition",
        "text": "Board succession planning is proactive and aligned to future strategic needs.",
        "answer_type": "rating",
        "weight": 1,
    },
    {
        "dimension": "Risk Oversight",
        "text": "The board provides effective oversight of key enterprise risks (financial, operational, regulatory).",
        "answer_type": "rating",
        "weight": 1,
    },
    {
        "dimension": "Risk Oversight",
        "text": "The board actively oversees emerging risks, including technology and cyber risks.",
        "answer_type": "rating",
        "weight": 1,
    },
    {
        "dimension": "Strategy Oversight",
        "text": "The board provides robust challenge and guidance on strategy, performance, and value creation.",
        "answer_type": "rating",
        "weight": 1,
    },
    {
        "dimension": "Strategy Oversight",
        "text": "The board monitors execution against strategy using clear KPIs and timely reporting.",
        "answer_type": "rating",
        "weight": 1,
    },
    {
        "dimension": "Board Culture & Dynamics",
        "text": "Board discussions encourage constructive challenge, candour, and healthy debate.",
        "answer_type": "rating",
        "weight": 1,
    },
    {
        "dimension": "Board Culture & Dynamics",
        "text": "Board papers and meeting minutes are well-structured and support effective decision-making.",
        "answer_type": "rating",
        "weight": 1,
    },
    {
        "dimension": "Open Comments",
        "text": "What are the board’s top 3 governance strengths?",
        "answer_type": "comment",
        "weight": 1,
    },
    {
        "dimension": "Open Comments",
        "text": "What are the board’s top 3 governance weaknesses / improvement areas?",
        "answer_type": "comment",
        "weight": 1,
    },
]

_EXPANDED_EXTRA: List[Dict[str, Any]] = [
    {
        "dimension": "Audit & Assurance",
        "text": "The audit committee provides effective oversight of financial reporting and internal controls.",
        "answer_type": "rating",
        "weight": 1,
    },
    {
        "dimension": "Audit & Assurance",
        "text": "Management responds appropriately to internal and external audit findings.",
        "answer_type": "rating",
        "weight": 1,
    },
    {
        "dimension": "Remuneration & Nomination",
        "text": "Executive and board remuneration align with long-term performance and stakeholder interests.",
        "answer_type": "rating",
        "weight": 1,
    },
    {
        "dimension": "Remuneration & Nomination",
        "text": "Board composition reviews address independence, tenure, and diversity constructively.",
        "answer_type": "rating",
        "weight": 1,
    },
    {
        "dimension": "Stakeholder & Stakeholder Governance",
        "text": "The board considers stakeholder impacts when making major decisions.",
        "answer_type": "rating",
        "weight": 1,
    },
    {
        "dimension": "Stakeholder & Stakeholder Governance",
        "text": "Shareholder and stakeholder communications are clear, timely, and balanced.",
        "answer_type": "rating",
        "weight": 1,
    },
    {
        "dimension": "Compliance & Ethics",
        "text": "The board promotes a strong tone at the top on ethics and regulatory compliance.",
        "answer_type": "rating",
        "weight": 1,
    },
    {
        "dimension": "Compliance & Ethics",
        "text": "Escalation pathways for misconduct or whistle-blowing are understood and trusted.",
        "answer_type": "rating",
        "weight": 1,
    },
    {
        "dimension": "Management Oversight",
        "text": "The board receives adequate depth of information to oversee management performance.",
        "answer_type": "rating",
        "weight": 1,
    },
    {
        "dimension": "Management Oversight",
        "text": "CEO and executive succession risks are reviewed regularly by the board.",
        "answer_type": "rating",
        "weight": 1,
    },
]

SEED_PRESETS: Dict[str, List[Dict[str, Any]]] = {
    "default": _DEFAULT_CORE,
    "expanded": _DEFAULT_CORE + _EXPANDED_EXTRA,
}


def list_preset_names() -> List[str]:
    return sorted(SEED_PRESETS.keys())


def get_questions_for_preset(preset: str) -> List[Dict[str, Any]]:
    key = (preset or "default").strip().lower()
    if key not in SEED_PRESETS:
        raise KeyError(key)
    return [dict(q) for q in SEED_PRESETS[key]]
