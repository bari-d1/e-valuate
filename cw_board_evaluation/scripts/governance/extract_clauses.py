"""
One-off ingestion: extract numbered clauses from governance code PDFs into
reviewable JSON fixtures (reference/governance/<CODE>.json).

Supported codes: NCCG_2018, NAICOM_2021. The PDFs are NOT part of the repo;
point --source-dir at the folder that holds them (searched recursively).

Requires PyMuPDF, which is only needed for this script (app/services/
document_text.py does not read PDFs):
    pip install pymupdf

Usage (from cw_board_evaluation/):
    python scripts/governance/extract_clauses.py --source-dir "~/Downloads/CORPORATE GOVERNANCE CODES"

Each fixture holds the clauses (reference as printed, parent, level, heading,
full text, sort order, cross-code citation) plus a `checks` section: counts
per part/section, a comparison with the document's table of contents, and
anything that looks truncated, merged or mis-numbered. Nothing is guessed:
anomalies are listed for a person to review.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter, OrderedDict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = ROOT / "reference" / "governance"

SOURCES = {
    "NCCG_2018": "Nigerian-Code-of-Corporate-Governance-2018.pdf",
    "NAICOM_2021": "NAICOM-CORPORATE-GOVERNANCE-GUIDELINES.pdf",
}

ROMAN = re.compile(r"^[ivxlc]+$", re.I)


# ----------------------------
# Shared helpers
# ----------------------------

def find_pdf(source_dir: Path, filename: str) -> Path:
    matches = sorted(source_dir.rglob(filename))
    if not matches:
        sys.exit(f"Could not find {filename} under {source_dir}")
    return matches[0]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def page_lines(path: Path, drop_line) -> List[Tuple[int, str]]:
    """All text lines as (page_number, line), minus headers/footers chosen by drop_line."""
    import pymupdf  # one-off dependency, see module docstring

    doc = pymupdf.open(path)
    out: List[Tuple[int, str]] = []
    for pno in range(doc.page_count):
        for raw in doc[pno].get_text().splitlines():
            line = raw.strip()
            if not line or drop_line(line):
                continue
            out.append((pno + 1, line))
    return out


ENUM_START = re.compile(r"^(\([a-z]{1,3}\)|[a-z]\.|[ivx]{1,5}\.|[A-Z]\.)(\s|$)")


def join_lines(lines: List[str]) -> str:
    """Join wrapped lines into text; list items ((a), i., A.) start on a new line."""
    text = ""
    for line in lines:
        if not text:
            text = line
        elif ENUM_START.match(line):
            text = text.rstrip() + "\n" + line
        elif text.endswith("-") and not text.endswith(" -"):
            text = text + line  # hyphenated word split across lines
        else:
            text = text + " " + line
    text = re.sub(r"[ \t]+", " ", text)
    # an enumerator on its own line followed by its text: "i.\nThe ..." -> "i. The ..."
    text = re.sub(r"(^|\n)(\([a-z]{1,3}\)|[a-z]\.|[ivx]{1,5}\.|[A-Z]\.) ?\n", r"\1\2 ", text)
    return text.strip()


def norm_heading(s: str) -> str:
    s = s.lower().replace("&", "and").replace("organisational", "organizational")
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def quality_flags(clauses: List[dict]) -> List[dict]:
    """Heuristic review list: possibly truncated, merged or stray text."""
    flags = []
    for c in clauses:
        t = c["text"]
        if c["level"] in ("part",):
            continue
        if t and not re.search(r"[.;:)\]\"”’]\s*$", t) and not t.endswith("and") and not t.endswith("or"):
            flags.append({"reference": c["reference"], "issue": "text does not end with punctuation (possibly truncated)", "tail": t[-80:]})
        if len(t) > 2500:
            flags.append({"reference": c["reference"], "issue": f"very long text ({len(t)} chars; possibly merged clauses)"})
        stray = re.findall(r"(?:^|\n)([a-z]\.|[ivx]{1,5}\.)\s*$", t)
        if stray:
            flags.append({"reference": c["reference"], "issue": f"ends with a bare list marker {stray[-1]!r} (stray text in the source)"})
        if c["level"] not in ("part", "principle", "section") and not t and not c.get("heading"):
            flags.append({"reference": c["reference"], "issue": "empty clause"})
    return flags


# ----------------------------
# NCCG 2018: Part > Principle > Recommended practice (> practice)
# ----------------------------

def nccg_toc(lines: List[Tuple[int, str]]) -> Dict[str, object]:
    """Parts, principles and section-11 sub-headings from the table of contents."""
    parts, principles, sub = OrderedDict(), OrderedDict(), OrderedDict()
    toc = []
    for _, line in lines:
        if line.startswith("List of Abbreviations"):
            break
        toc.append(re.sub(r"\s*\.{3,}.*$", "", line).strip())
    i = 0
    while i < len(toc):
        line = toc[i]
        m = re.match(r"^Part ([A-G])\.\s*(.+)$", line)
        if m:
            parts[f"Part {m.group(1)}"] = m.group(2).strip()
        m = re.match(r"^(\d{1,2})\.$", line)
        if m and i + 1 < len(toc):
            principles[m.group(1)] = toc[i + 1]
            i += 1
        m = re.match(r"^(\d{1,2}\.\d)\s+(.+)$", line)
        if m:
            sub[m.group(1)] = m.group(2).strip()
        i += 1
    return {"parts": parts, "principles": principles, "sub_headings": sub}


def nccg_successors(last: Optional[List[int]], principle: int) -> List[List[int]]:
    if not last:
        return [[principle, 1]]
    cands = [last + [1]]
    for depth in range(len(last), 1, -1):
        cands.append(last[: depth - 1] + [last[depth - 1] + 1])
    return cands


def extract_nccg(pdf: Path) -> dict:
    def drop(line: str) -> bool:
        return bool(re.fullmatch(r"\d{1,3}", line) or ROMAN.fullmatch(line))

    lines = page_lines(pdf, drop)
    toc = nccg_toc(lines)

    # Body starts at the first "Part A." after the abbreviations list (Introduction A-E is skipped).
    start = next(i for i, (_, l) in enumerate(lines) if l.startswith("List of Abbreviations"))
    start = next(i for i in range(start, len(lines)) if re.match(r"^Part A\.", lines[i][1]))
    body = lines[start:]

    clauses: List[dict] = []
    anomalies: List[dict] = []
    current: Optional[dict] = None
    buf: List[str] = []
    part_ref: Optional[str] = None
    principle: Optional[int] = None
    last_practice: Optional[List[int]] = None
    expecting = None  # "part_heading" | "principle_heading"
    in_practices = False

    def flush():
        nonlocal buf
        if current is not None and buf:
            current["_lines"].extend(buf)
        buf = []

    def new_clause(**kw) -> dict:
        nonlocal current
        flush()
        c = {"_lines": [], "heading": None, "cites": None, **kw}
        clauses.append(c)
        current = c
        return c

    i = 0
    while i < len(body):
        page, line = body[i]

        if expecting == "part_heading":
            current["heading"] = line
            expecting = None
            i += 1
            continue
        if expecting == "principle_heading":
            # Headings are one line (as in the table of contents). Principle 29 (Definitions) has no
            # "Principle 29:" statement, so the heading must not run on until one appears.
            expecting = None
            if not line.startswith("Principle "):
                current["heading"] = line
                i += 1
                continue

        m = re.match(r"^Part ([A-G])\.\s*(.*)$", line)
        if m:
            part_ref = f"Part {m.group(1)}"
            new_clause(reference=part_ref, parent=None, level="part", page=page)
            if m.group(2).strip():
                current["heading"] = m.group(2).strip()
            else:
                expecting = "part_heading"
            in_practices = False
            i += 1
            continue

        m = re.fullmatch(r"(\d{1,2})\.", line)
        if m and (principle is None or int(m.group(1)) == principle + 1):
            principle = int(m.group(1))
            last_practice = None
            in_practices = False
            new_clause(reference=str(principle), parent=part_ref, level="principle", page=page)
            expecting = "principle_heading"
            i += 1
            continue

        m = re.match(r"^Principle (\d{1,2}):\s*(.*)$", line)
        if m and principle is not None and int(m.group(1)) == principle:
            if m.group(2):
                buf.append(m.group(2))
            i += 1
            continue

        if re.match(r"^Recommended Practices\s*$", line):
            in_practices = True
            i += 1
            continue

        m = re.match(r"^(\d{1,2}(?:\.\d{1,2}){1,3})\.?(?:\s+(.*))?$", line)
        if m and principle is not None:
            nums = [int(x) for x in m.group(1).split(".")]
            if nums[0] == principle and nums in nccg_successors(last_practice, principle):
                last_practice = nums
                parent_ref = str(principle) if len(nums) == 2 else ".".join(map(str, nums[:-1]))
                new_clause(reference=m.group(1), parent=parent_ref, level="practice", page=page)
                if m.group(2):
                    buf.append(m.group(2))
                i += 1
                continue
            if nums[0] == principle or (len(nums) >= 2 and nums[0] <= 29):
                anomalies.append({
                    "page": page,
                    "line": line[:120],
                    "issue": f"numbered line {m.group(1)} is out of sequence after "
                             f"{'.'.join(map(str, last_practice)) if last_practice else principle}; kept as text of "
                             f"{current['reference'] if current else '?'}",
                })

        buf.append(line)
        i += 1
    flush()

    # Practices whose only text is a short title and which have children are sub-headings (e.g. "11.1 Board Committees").
    children = Counter(c["parent"] for c in clauses)
    for c in clauses:
        text = join_lines(c.pop("_lines"))
        if c["level"] == "practice" and children[c["reference"]] and len(text) < 80 and not re.search(r"[.;:]$", text):
            c["heading"], text = text, ""
        c["text"] = text

    return finish("NCCG_2018", pdf, clauses, anomalies, nccg_checks(clauses, toc))


def nccg_checks(clauses: List[dict], toc: Dict[str, object]) -> dict:
    by_ref = {c["reference"]: c for c in clauses}
    parts = [c for c in clauses if c["level"] == "part"]
    principles = [c for c in clauses if c["level"] == "principle"]

    def part_of(c):
        while c and c["level"] != "part":
            c = by_ref.get(c["parent"])
        return c["reference"] if c else None

    counts = OrderedDict()
    for p in parts:
        counts[p["reference"]] = {"heading": p["heading"], "principles": 0, "practices": 0}
    for c in clauses:
        if c["level"] in ("principle", "practice"):
            counts[part_of(c)]["principles" if c["level"] == "principle" else "practices"] += 1

    mismatches = []
    for ref, title in toc["parts"].items():
        got = by_ref.get(ref)
        if not got:
            mismatches.append({"toc": f"{ref} {title}", "issue": "missing from extracted clauses"})
        elif norm_heading(got["heading"] or "") != norm_heading(title):
            mismatches.append({"toc": f"{ref} {title}", "extracted": got["heading"], "issue": "heading differs"})
    for ref, title in toc["principles"].items():
        got = by_ref.get(ref)
        if not got:
            mismatches.append({"toc": f"{ref}. {title}", "issue": "missing from extracted clauses"})
        elif norm_heading(got["heading"] or "") != norm_heading(title):
            mismatches.append({"toc": f"{ref}. {title}", "extracted": got["heading"], "issue": "heading differs"})
    for ref, title in toc["sub_headings"].items():
        got = by_ref.get(ref)
        if not got:
            mismatches.append({"toc": f"{ref} {title}", "issue": "missing from extracted clauses"})
        elif norm_heading(got["heading"] or got["text"][:80]) != norm_heading(title):
            mismatches.append({"toc": f"{ref} {title}", "extracted": got["heading"] or got["text"][:80], "issue": "heading differs"})
    extra = [c["reference"] for c in principles if c["reference"] not in toc["principles"]]

    return {
        "toc": {
            "parts": len(toc["parts"]),
            "principles": len(toc["principles"]),
            "section_11_sub_headings": len(toc["sub_headings"]),
        },
        "extracted": {
            "parts": len(parts),
            "principles": len(principles),
            "practices": sum(1 for c in clauses if c["level"] == "practice"),
        },
        "counts_by_part": counts,
        "toc_mismatches": mismatches,
        "principles_not_in_toc": extra,
        "skipped": ["Introduction A-E (Authority, Aims and Objectives, Code Philosophy, Monitoring, Structure): "
                    "explanatory text before Part A, not numbered clauses"],
    }


# ----------------------------
# NAICOM 2021: Section > Subsection
# ----------------------------

NAICOM_HEADER = re.compile(r"^Corporate Governance Guidelines for Insurance and Reinsurance Companies\s+\d+\s*\|\s*P\s*a\s*g\s*e\s*$")

# Page 15 is a scanned image with no text layer. Typed text transcribed from it:
NAICOM_SCANNED = [
    {
        "reference": "12.0",
        "heading": "Enforcement and Sanctions",
        "text": "The non-compliance with the NCCG 2018 and this Guideline shall be a violation of Section 49(1) (b) "
                "of the National Insurance Commission Act 1997 and attracts penalty under section 49(5) of the Act.",
    },
    {
        "reference": "13.0",
        "heading": "Scope and Effective Date of the Guidelines",
        "text": "This Guideline applies to ALL Insurance and Reinsurance Companies. The Application of the Guidelines "
                "shall be effective from 1st June, 2021.",
    },
]
NAICOM_SCANNED_NOTE = (
    "Transcribed from the scanned page 15 (no text layer). The effective date '1st June' is handwritten. "
    "The page ends: 'This Guidelines is issued by the National Insurance Commission on the 17th day of March 2021' "
    "(date handwritten)."
)


def naicom_toc(lines: List[Tuple[int, str]]) -> "OrderedDict[str, str]":
    toc: "OrderedDict[str, str]" = OrderedDict()
    seen = False
    for _, line in lines:
        if line.startswith("Table of Contents"):
            seen = True
            continue
        if seen:
            m = re.match(r"^(\d{1,2}\.\d{1,2})\s+(.+?)\.?$", line)
            if not m:
                break
            toc[m.group(1)] = m.group(2).strip()
    return toc


def extract_naicom(pdf: Path) -> dict:
    lines = page_lines(pdf, lambda l: bool(NAICOM_HEADER.match(l)))
    toc = naicom_toc(lines)
    start = next(i for i, (_, l) in enumerate(lines) if re.match(r"^1\.0\s+INTRODUCTION", l))
    body = lines[start:]

    clauses: List[dict] = []
    anomalies: List[dict] = []
    current: Optional[dict] = None
    section: Optional[int] = None

    for page, line in body:
        m = re.match(r"^(\d{1,2})\.\s?0\.?\s+(\S.*)$", line)
        if m and (section is None or int(m.group(1)) == section + 1):
            section = int(m.group(1))
            printed = re.match(r"^(\d{1,2}\.\s?0\.?)", line).group(1)
            ref = f"{section}.0"
            current = {"reference": ref, "parent": None, "level": "section", "heading": m.group(2).strip(),
                       "page": page, "_lines": [], "cites": None}
            if printed.replace(" ", "").rstrip(".") != ref or " " in printed:
                current["printed_reference"] = printed.strip()
            clauses.append(current)
            continue

        m = re.match(r"^(\d{1,2})\.(\d{2}|[1-9])\s+(\S.*)$", line)
        if m and section is not None and int(m.group(1)) == section and m.group(3)[:1].isupper():
            current = {"reference": f"{m.group(1)}.{m.group(2)}", "parent": f"{section}.0", "level": "subsection",
                       "heading": m.group(3).strip(), "page": page, "_lines": [], "cites": None}
            clauses.append(current)
            continue

        if current is None:
            anomalies.append({"page": page, "line": line[:120], "issue": "text before the first section"})
            continue
        current["_lines"].append(line)

    for c in clauses:
        c["text"] = join_lines(c.pop("_lines"))

    last_section = max(int(c["reference"].split(".")[0]) for c in clauses if c["level"] == "section")
    for i, s in enumerate(NAICOM_SCANNED):
        clauses.append({**s, "parent": None, "level": "section", "page": 15, "cites": None,
                        "extraction_note": NAICOM_SCANNED_NOTE})
    if last_section != 11:
        anomalies.append({"issue": f"expected text-layer sections to end at 11.0, got {last_section}.0"})

    # Citations of NCCG principles/practices: "In addition to (the provision of) Principle 2.7 of the NCCG 2018"
    unresolved_mentions = []
    for c in clauses:
        refs = re.findall(r"Principle\s+(\d{1,2}(?:\.\d{1,2}){0,3})\s+of\s+(?:the\s+)?NCCG", c["text"])
        if len(refs) == 1:
            c["cites"] = f"NCCG_2018:{refs[0]}"
        elif len(refs) > 1:
            c["cites"] = f"NCCG_2018:{refs[0]}"
            anomalies.append({"reference": c["reference"], "issue": f"cites several NCCG clauses {refs}; only the first is stored"})
        if "NCCG" in c["text"] and not refs:
            unresolved_mentions.append(c["reference"])

    return finish("NAICOM_2021", pdf, clauses, anomalies, naicom_checks(clauses, toc, unresolved_mentions))


def naicom_checks(clauses: List[dict], toc: "OrderedDict[str, str]", general_mentions: List[str]) -> dict:
    by_ref = {c["reference"]: c for c in clauses}
    mismatches = []
    for ref, title in toc.items():
        got = by_ref.get(ref)
        if not got:
            mismatches.append({"toc": f"{ref} {title}", "issue": "missing from extracted clauses"})
        elif norm_heading(got["heading"] or "") != norm_heading(title):
            mismatches.append({"toc": f"{ref} {title}", "extracted": got["heading"], "issue": "heading differs"})
    extra = [c["reference"] for c in clauses if c["reference"] not in toc]

    counts = OrderedDict()
    for c in clauses:
        if c["level"] == "section":
            counts[c["reference"]] = {"heading": c["heading"], "subsections": 0}
    for c in clauses:
        if c["level"] == "subsection":
            counts[c["parent"]]["subsections"] += 1

    renumbered = [{"reference": c["reference"], "printed": c["printed_reference"]} for c in clauses if c.get("printed_reference")]
    return {
        "toc": {"entries": len(toc)},
        "extracted": {
            "sections": sum(1 for c in clauses if c["level"] == "section"),
            "subsections": sum(1 for c in clauses if c["level"] == "subsection"),
        },
        "counts_by_section": counts,
        "toc_mismatches": mismatches,
        "not_in_toc": extra,
        "references_normalised": renumbered,
        "numbering_notes": [
            "Section 2.0 numbers its subsections 2.01-2.06 and then 2.1, 2.2 (as printed and as in the table of "
            "contents); references are kept exactly as printed.",
        ],
        "general_nccg_mentions_without_clause_number": general_mentions,
    }


# ----------------------------
# Output
# ----------------------------

def finish(code: str, pdf: Path, clauses: List[dict], anomalies: List[dict], checks: dict) -> dict:
    out = []
    for n, c in enumerate(clauses, start=1):
        row = OrderedDict(
            reference=c["reference"],
            parent_reference=c["parent"],
            level=c["level"],
            heading=c.get("heading"),
            text=c["text"],
            sort_order=n * 10,
            page=c.get("page"),
            cites=c.get("cites"),
        )
        for k in ("printed_reference", "extraction_note"):
            if c.get(k):
                row[k] = c[k]
        out.append(row)
    refs = Counter(c["reference"] for c in out)
    dupes = [r for r, k in refs.items() if k > 1]
    if dupes:
        anomalies.append({"issue": f"duplicate references {dupes}"})
    orphans = [c["reference"] for c in out if c["parent_reference"] and c["parent_reference"] not in refs]
    if orphans:
        anomalies.append({"issue": f"clauses whose parent is missing: {orphans}"})

    checks["numbering_gaps"] = numbering_gaps(out)
    checks["review"] = quality_flags(out)
    checks["sequence_anomalies"] = anomalies
    return OrderedDict(
        code=code,
        source_filename=pdf.name,
        source_sha256=sha256(pdf),
        extracted_with="scripts/governance/extract_clauses.py (PyMuPDF)",
        clause_count=len(out),
        checks=checks,
        clauses=out,
    )


def numbering_gaps(clauses: List[dict]) -> List[dict]:
    """Children of each parent should be numbered 1..n with no gaps (NCCG-style dotted references)."""
    kids: Dict[Optional[str], List[int]] = {}
    for c in clauses:
        ref = c["reference"]
        if c["level"] == "practice" and re.fullmatch(r"\d+(\.\d+)+", ref):
            kids.setdefault(c["parent_reference"], []).append(int(ref.rsplit(".", 1)[1]))
    gaps = []
    for parent, nums in kids.items():
        expected = list(range(1, max(nums) + 1))
        if sorted(nums) != expected:
            gaps.append({"parent": parent, "children": nums, "missing": sorted(set(expected) - set(nums))})
    return gaps


EXTRACTORS = {"NCCG_2018": extract_nccg, "NAICOM_2021": extract_naicom}


def resolve_citations(fixtures: Dict[str, dict]) -> None:
    """Record, per fixture, any citation whose target clause doesn't exist in the cited code's fixture."""
    for code, fx in fixtures.items():
        unresolved = []
        resolved = []
        for c in fx["clauses"]:
            if not c["cites"]:
                continue
            target_code, target_ref = c["cites"].split(":", 1)
            target = fixtures.get(target_code)
            ok = bool(target) and any(t["reference"] == target_ref for t in target["clauses"])
            (resolved if ok else unresolved).append({"reference": c["reference"], "cites": c["cites"]})
        fx["checks"]["citations"] = {"resolved": resolved, "unresolved": unresolved}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source-dir", required=True, type=Path)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--codes", nargs="+", default=list(EXTRACTORS), choices=list(EXTRACTORS))
    args = ap.parse_args()

    source_dir = args.source_dir.expanduser()
    fixtures = {code: EXTRACTORS[code](find_pdf(source_dir, SOURCES[code])) for code in args.codes}
    resolve_citations(fixtures)

    args.out.mkdir(parents=True, exist_ok=True)
    for code, fx in fixtures.items():
        path = args.out / f"{code}.json"
        path.write_text(json.dumps(fx, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        chk = fx["checks"]
        print(f"{code}: {fx['clause_count']} clauses -> {path.relative_to(ROOT)}")
        print(f"   extracted {chk['extracted']} | toc {chk['toc']}")
        print(f"   toc mismatches: {len(chk['toc_mismatches'])} | review flags: {len(chk['review'])} | "
              f"sequence anomalies: {len(chk['sequence_anomalies'])} | numbering gaps: "
              f"{len(chk['numbering_gaps'])} | citations: "
              f"{len(chk['citations']['resolved'])} resolved, {len(chk['citations']['unresolved'])} unresolved")


if __name__ == "__main__":
    main()
