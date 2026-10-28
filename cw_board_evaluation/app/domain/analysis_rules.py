"""
app.domain.analysis_rules
-------------------------
Every threshold and rule the analysis uses, in one place. Change them here;
nothing else in the analysis hard-codes a number.

Small numbers
  MIN_RATERS (default 3, set per run): results about an individual director, or
  a rater-group split, need at least this many distinct people behind them, or
  they're suppressed with the reason. Board, committee and secretariat results
  with fewer respondents are still shown, flagged "small sample".

Facts are not opinions
  ORG_FACT answers, and ROLE_SELF yes/no, choice and text answers (a director's
  own declarations), are listed as facts and never averaged into scores. Scores
  come from PERCEPTION ratings by people other than the subject. ROLE_SELF
  ratings are only used as the "self" side of self versus peer.

Consensus (ratings on a 1 to 5 scale, population standard deviation; for a theme,
over each rater's average across the theme's items, so one person's many answers
count once; for an item, over the ratings themselves)
  single view       fewer than 2 ratings
  divided           SD >= 1.25, or at least 25% of ratings at each end (<= 2 and >= 4)
  strong agreement  SD <= 0.75
  mixed             anything else

Computed findings
  strength             theme average >= 4.2 with strong agreement; or an item linked to a
                       governance clause averaging >= 4.5 with strong agreement
  concern              theme average <= 2.5; or a clause-linked item averaging <= 2.5
  observation          a theme where views are divided (support "conflicting")
  self_perception_gap  |self - peer average| >= 1.0 on a core peer statement
  compliance_gap       a factual yes/no item with an expected answer and a governance
                       clause, answered the other way. Never from opinion ratings.

Support levels (distinct people behind the evidence)
  strong       >= 5 people, and they agree (not divided)
  moderate     >= 3 people
  limited      fewer (or a single factual answer: a fact from the person responsible
               is "moderate"; see FACT_SUPPORT)
  conflicting  the evidence is divided
  AI drafts may not claim more than max_support() allows for the evidence they cite.
"""

from __future__ import annotations

import math
from typing import Dict, Iterable, List, Optional

DEFAULT_MIN_RATERS = 3

STRONG_AGREEMENT_SD = 0.75
DIVIDED_SD = 1.25
DIVIDED_END_SHARE = 0.25  # share of ratings at each end of the scale that makes views "divided"

THEME_STRENGTH_MEAN = 4.2
ITEM_STRENGTH_MEAN = 4.5
CONCERN_MEAN = 2.5
SELF_PEER_GAP = 1.0

STRONG_SUPPORT_PEOPLE = 5
MODERATE_SUPPORT_PEOPLE = 3
FACT_SUPPORT = "moderate"

SUPPORT_ORDER = ("limited", "moderate", "strong")  # "conflicting" sits outside the order

# Respondent categories (never names). Rater-group splits compare executives with non-executives.
CATEGORY_FOR_ROLE = {
    "chair": "chair", "md_ceo": "executive", "ed": "executive", "ned": "non_executive", "ined": "independent",
    "company_secretary": "company_secretary",
}
CATEGORY_LABELS = {
    "chair": "Chair", "executive": "Executive director", "non_executive": "Non-executive director",
    "independent": "Independent non-executive director", "company_secretary": "Company secretary",
    "other": "Other", "self": "Self-assessment",
}
SPLIT_GROUPS = {
    "executive": ("Executives", {"executive"}),
    "non_executive": ("Non-executives", {"chair", "non_executive", "independent"}),
}

# Self and peer versions of the core statements: PEER-CORE-0n pairs with SELF-CORE-0n
PEER_PREFIX, SELF_PREFIX = "PEER-CORE-", "SELF-CORE-"


def mean(xs: List[float]) -> Optional[float]:
    return round(sum(xs) / len(xs), 2) if xs else None


def spread(xs: List[float]) -> Optional[float]:
    """Population standard deviation, to 2 places."""
    if len(xs) < 2:
        return 0.0 if xs else None
    m = sum(xs) / len(xs)
    return round(math.sqrt(sum((x - m) ** 2 for x in xs) / len(xs)), 2)


def consensus(xs: List[float], low: int = 1, high: int = 5) -> str:
    if len(xs) < 2:
        return "single view"
    sd = spread(xs)
    lo_end = sum(1 for x in xs if x <= low + 1) / len(xs)
    hi_end = sum(1 for x in xs if x >= high - 1) / len(xs)
    if sd >= DIVIDED_SD or (lo_end >= DIVIDED_END_SHARE and hi_end >= DIVIDED_END_SHARE):
        return "divided"
    if sd <= STRONG_AGREEMENT_SD:
        return "strong agreement"
    return "mixed"


def support_for(people: int, label: Optional[str] = None) -> str:
    """Support level for a computed finding from the number of distinct people and the consensus."""
    if label == "divided":
        return "conflicting"
    if people >= STRONG_SUPPORT_PEOPLE:
        return "strong"
    if people >= MODERATE_SUPPORT_PEOPLE:
        return "moderate"
    return "limited"


def max_support(people: int) -> str:
    """The highest support an AI draft may claim for evidence from this many distinct people."""
    return support_for(people)


def support_allowed(claimed: str, people: int) -> bool:
    if claimed == "conflicting":
        return people >= 2
    return SUPPORT_ORDER.index(claimed) <= SUPPORT_ORDER.index(max_support(people))


def distribution(xs: Iterable[float], low: int = 1, high: int = 5) -> Dict[str, int]:
    out = {str(p): 0 for p in range(low, high + 1)}
    for x in xs:
        key = str(int(x))
        if key in out:
            out[key] += 1
    return out
