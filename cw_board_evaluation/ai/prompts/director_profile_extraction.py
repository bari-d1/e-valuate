"""
Prompt for proposing a board member's profile facts from one chunk of one of
their documents (CV, director profile). The model only PROPOSES; a consultant
confirms. Every proposal must quote the document verbatim; the caller discards
any proposal whose quote isn't found in the document text.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List

SYSTEM_PROMPT = """You extract facts about ONE board member from documents about them, for a board evaluation consultancy.

Rules:
1. Only state what the document text says about this person. Never guess, estimate, calculate or use outside knowledge.
2. If the text doesn't state something, leave it out. Do not output placeholders.
3. Every fact needs "source_excerpt": a short quote (one sentence or less, at most 300 characters) copied
   character-for-character from the document text that states it. Do not paraphrase. If you can't quote it, leave it out.
4. Independence facts: answer "yes" or "no" ONLY when the text explicitly says so (for example "holds no shares in
   the Company"). If the text doesn't say so explicitly, leave that fact out: it stays unknown.
5. personality_notes: only copy, word for word, what the document literally says about the person's style or manner.
   Never describe or characterise the person yourself. If nothing is said, leave it out.
6. governance_role: only when the text states their role on THIS board.
7. Dates as YYYY-MM-DD only when the document gives the day, month and year. If it gives only a month and year
   (e.g. "joined the Board in July 2020"), leave the date out: never fill in a day.
8. Use only the fact keys listed by the user, with the value shape given for each key.
9. Reply with JSON only, matching the requested schema. No commentary."""

RESPONSE_SCHEMA = {
    "facts": [
        {"key": "<one of the allowed keys>", "value": "<shape given for that key>", "source_excerpt": "<verbatim quote>"}
    ]
}

_SHAPES = {
    "choice": "one of: {options}",
    "date": "a date as YYYY-MM-DD",
    "text": "a string",
    "list": "a list of strings",
    "tristate": 'an object {{"answer": "yes" or "no", "detail": "<optional short detail>"}}',
}


def describe_keys(registry: List[Dict[str, Any]]) -> str:
    lines = []
    for f in registry:
        shape = _SHAPES[f["type"]]
        if f["type"] == "choice":
            shape = shape.format(options=", ".join(o["key"] for o in f["options"]))
        else:
            shape = shape.format()
        lines.append(f'- {f["key"]}: {f["label"]}. Value: {shape}. {f.get("help", "")}'.rstrip())
    return "\n".join(lines)


def build_user_prompt(registry: List[Dict[str, Any]], *, person: str, filename: str, part: str, text: str) -> str:
    return (
        f"The person: {person}\n\n"
        "Allowed fact keys:\n"
        f"{describe_keys(registry)}\n\n"
        "Reply with JSON in this shape (omit anything the text doesn't state):\n"
        f"{json.dumps(RESPONSE_SCHEMA, indent=2)}\n\n"
        f"Document: {filename} ({part})\n\n"
        "DOCUMENT TEXT START\n"
        f"{text}\n"
        "DOCUMENT TEXT END"
    )
