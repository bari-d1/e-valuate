"""
Prompt for proposing organisation profile facts and committees from one chunk
of one client document. The model only PROPOSES; a consultant confirms.
Every proposal must quote the document verbatim; the caller discards any
proposal whose quote isn't found in the document text.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List

SYSTEM_PROMPT = """You extract facts about a company from its own documents for a board evaluation consultancy.

Rules:
1. Only state what the document text says. Never guess, estimate, calculate or use outside knowledge.
2. If the text doesn't state something, leave it out. Do not output nulls or placeholders for missing facts.
3. Do not infer personality, performance, opinions or intentions of any person or of the board.
4. Every fact and committee needs "source_excerpt": a short quote (one sentence or less, at most 300 characters)
   copied character-for-character from the document text that states it. Do not paraphrase, fix typos or join
   separate passages. If you can't quote it, leave the item out.
5. For committees, copy the committee name, the chair and each member's name exactly as written. Do not add titles
   that aren't in the text and do not expand initials.
6. Use only the fact keys listed by the user, with the value shape given for each key.
7. Reply with JSON only, matching the requested schema. No commentary."""

RESPONSE_SCHEMA = {
    "facts": [
        {"key": "<one of the allowed keys>", "value": "<shape given for that key>", "source_excerpt": "<verbatim quote>"}
    ],
    "committees": [
        {
            "name": "<as written>",
            "committee_type": "audit | risk | remuneration | nomination | finance | governance | other",
            "chair_name": "<as written, or null if not stated>",
            "member_names": ["<as written>"],
            "source_excerpt": "<verbatim quote>",
        }
    ],
}

_SHAPES = {
    "text": "a string",
    "number": "a whole number",
    "list": "a list of strings",
    "object": "an object with whole-number fields",
}


def describe_keys(registry: List[Dict[str, Any]]) -> str:
    lines = []
    for f in registry:
        shape = _SHAPES[f["type"]]
        if f["type"] == "object":
            shape += " (" + ", ".join(x["key"] for x in f["fields"]) + "; include only counts the text states)"
        lines.append(f'- {f["key"]}: {f["label"]}. Value: {shape}. {f.get("help", "")}'.rstrip())
    return "\n".join(lines)


def build_user_prompt(registry: List[Dict[str, Any]], *, doc_type: str, filename: str, part: str, text: str) -> str:
    return (
        "Allowed fact keys:\n"
        f"{describe_keys(registry)}\n\n"
        "Reply with JSON in this shape (omit anything the text doesn't state):\n"
        f"{json.dumps(RESPONSE_SCHEMA, indent=2)}\n\n"
        f"Document type: {doc_type}\nDocument: {filename} ({part})\n\n"
        "DOCUMENT TEXT START\n"
        f"{text}\n"
        "DOCUMENT TEXT END"
    )
