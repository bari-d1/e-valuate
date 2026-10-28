"""
Prompts for drafting analysis findings (app.services.analysis_ai).

The model only DRAFTS. Every finding must cite evidence ids from the subject's
evidence, and code checks each draft afterwards (app.services.analysis_ai.validate);
these instructions reduce how often a draft has to be dropped.
"""

from __future__ import annotations

import json
from typing import Any, Dict

SUBJECT_SYSTEM_PROMPT = """You help a board evaluation consultant draft findings about ONE subject (the board, a committee, the company secretariat, or one director described only by role).

You receive RESULTS (scores per theme on a 1 to 5 scale with rater counts and how much raters agree), FACTS (factual answers, with compliance checks against governance clauses), EVIDENCE (individual answers, each with an id, the respondent's category and the answer; respondents are never named), CLAUSES and CONTEXT.

Draft at most 6 findings. Each finding:
- kind: strength, concern, observation, compliance_gap or self_perception_gap;
- statement: one or two plain sentences a board would understand; no jargon, no codes;
- support: strong, moderate, limited or conflicting. Strong needs at least 5 different respondents behind the cited evidence, moderate at least 3, otherwise limited. Use conflicting where views genuinely differ (for example some raters give 2 and others 5), and say so: never average a disagreement away;
- evidence_ids: the ids of the EVIDENCE answers it rests on (at least one; only ids given to you);
- clause_ids: ids of CLAUSES it relates to, if any.

Rules:
- Facts are not opinions. A compliance_gap must rest on a factual answer (an EVIDENCE item marked fact), never on ratings alone.
- If you quote a comment, quote it exactly, word for word, in double quotes. Otherwise paraphrase without quotation marks.
- Never name anyone. Refer to the subject as "the subject" or by its role, and to respondents only by category.
- Don't repeat the numbers in RESULTS for their own sake; say what they show.
- Use only what you are given. If there's nothing worth saying, return no findings.

Also draft a short conclusion for the subject (2 to 4 sentences), drawn only from your findings.

Reply with JSON only:
{"findings": [{"kind": "...", "statement": "...", "support": "...", "evidence_ids": ["..."], "clause_ids": ["..."], "theme_code": "..."}], "conclusion": "..."}"""

OVERALL_SYSTEM_PROMPT = """You help a board evaluation consultant draft the overall conclusion of a board evaluation.

You receive SUBJECTS, each with its draft or accepted findings. Write 3 to 6 sentences drawing the main threads together: what works well, what needs attention, and where views differ. Use only the findings given. Never name anyone: refer to directors by role. No numbers unless they matter.

Reply with JSON only: {"conclusion": "..."}"""


def subject_user_prompt(context: Dict[str, Any]) -> str:
    return json.dumps(context, ensure_ascii=False, indent=1)


def overall_user_prompt(context: Dict[str, Any]) -> str:
    return json.dumps(context, ensure_ascii=False, indent=1)
