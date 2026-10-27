# Question bank

The firm's evaluation methodology, held as data: approved question items, what each one is about, who answers it, and the deterministic rules that decide which participant gets which item about which subject. AI does not choose questions. Later, assembly will use AI only to phrase the items selected here.

| File | What it is |
|---|---|
| `draft_bank.json` | The draft bank: 246 items, every one `draft`, every tag `suggested`. This is the source of truth and what the loader reads. |
| `draft_bank.csv` | The same items flattened for review in a spreadsheet, with each rule written out in plain English. Regenerate it after editing the JSON (see below). |

The historical form PDFs are **not** in the repo. Four of them carried a real director's name in their header. They are referred to only as "NED peer assessment (BE 3B), named copy 1–4", and no name from them appears in the fixture.

## Load and regenerate

From `cw_board_evaluation/`:

```bash
python scripts/seed_reference_data.py            # subject types, themes, evidence sources, codes
python scripts/governance/load_clauses.py        # clauses, so governance references resolve
python scripts/question_bank/load_bank.py        # loads draft_bank.json
python scripts/question_bank/load_bank.py --check            # validate only, nothing saved
python scripts/question_bank/load_bank.py other_bank.json    # another fixture in the same format
python scripts/question_bank/export_csv.py       # rewrite draft_bank.csv from draft_bank.json
```

Loading is idempotent by `(code, version)`. An item that is already in the database is left alone, so edits made in the app are never overwritten. `--update-drafts` refreshes items that are still drafts. Every item is validated (content, both rules, tag codes) and its governance references are resolved. The loader lists anything that doesn't load and exits 1 if any item failed.

## How the draft was made

Source: 18 Google Forms (PDF) from a 2022 insurance-sector evaluation. Transcribed by hand as a one-off authoring step; no AI API was used.

1. **Extract.** Every question was taken with its answer format, options, section heading, source form and item number. Admin fields (email, name, designation, date of appointment, "committees you belong to") were dropped. Each form's dropped fields are listed under `source_forms` in the JSON.
2. **De-duplicate.** Identical items were merged; each merged item keeps every source in `source_refs` (form and item number, never a person's name):
   - the five NED peer forms are identical apart from the header, giving one 16-item template (`PEER-NED-*`);
   - the ED and MD/CEO peer forms ask the same 20 items plus a grading line, giving `PEER-EXEC-*`;
   - the four committee forms share items 1–19, 21 and the closing comments, giving a 21-item core (`COM-CORE-*`), plus five committee-specific items each;
   - questions repeated across the self-assessments were merged: skills from four forms into `DIR-SELF-02`, tenure into `DIR-SELF-01`, the NAICOM disclosure question from three forms into `ROLE-SELF-01`, and six shared MD/CEO and ED items into `EXEC-SELF-*`.
3. **Template hard-coded facts.** Wording tied to the 2022 client is now a placeholder, filled from confirmed facts at selection time (see below).
4. **Mark what the system already knows.** Items that ask for a profile or organisation fact have `known_from` set. `skip` means the item is not asked once the fact is confirmed; `confirm` means the respondent is shown the stored value to confirm.
5. **Tag.** Every item has suggested subject types, subject binding, respondent rule, activation rule, theme, evidence source and governance clause references. Each tag has a one-line reason in `tag_notes` for the consultant's review.
6. **Answer formats.** The forms used about a dozen different scales, several printed as checkboxes by mistake. Every rating is now one of two 1–5 scales: quality (Poor … Excellent) or agreement (Strongly disagree … Strongly agree). The agreement scale keeps "Don't know" where the original had it. Each source reference keeps the original options under `original_answer`. Clear yes/no questions that were printed as short-answer fields (the INED questions) are now yes/no.

Code prefixes: `DIR-SELF` (every director about themselves), `BOARD-EFF/DYN/STR/RISK/GEN` (whole board, Parts A–D), `CHAIR-SELF`, `ROLE-SELF` (chair, MD/CEO and EDs), `EXEC-SELF`, `CEO-SELF`, `ED-SELF`, `INED-IND`, `CHAIR-PEER`, `PEER-EXEC`, `PEER-NED`, `COM-CORE`, `COM-AUDIT`, `COM-SAC` (statutory audit committee), `COM-ERMG`, `COM-FIN`, `SEC`.

## Counts

| Source forms | Items on the forms | Bank items after merging |
|---|---:|---:|
| Whole board (BE 5) | 42 | 42 (`DIR-SELF` 7, `BOARD-*` 35) |
| Chairman's self-assessment (BE 1) | 10 | 7 (`CHAIR-SELF`); 3 merged into `DIR-SELF-01`, `DIR-SELF-02`, `ROLE-SELF-01` |
| MD/CEO self-assessment + ED self-assessment | 20 | 11 (`EXEC-SELF` 5, `CEO-SELF` 3, `ED-SELF` 3); the rest merged into `DIR-SELF-02` and `ROLE-SELF-01` |
| Shared by chair, MD/CEO and EDs | | 1 (`ROLE-SELF-01`) |
| Independent non-executive directors | 9 | 9 (`INED-IND`) |
| Chairman peer assessment | 28 | 28 (`CHAIR-PEER`) |
| ED peer + MD/CEO peer (BE 6B) | 42 | 21 (`PEER-EXEC`) |
| NED peer (BE 3B), generic + four named copies | 80 | 16 (`PEER-NED`) |
| Four committee forms (BE 4A) | 104 | 41 (`COM-CORE` 21, `COM-AUDIT`/`COM-SAC`/`COM-ERMG`/`COM-FIN` 5 each) |
| Secretariat questionnaire | 70 | 70 (`SEC`) |
| **Total** | **405** | **246** |

Answer types: 87 rating, 72 comment, 64 yes/no, 13 multiple choice, 10 single choice. Evidence: 127 perception, 84 organisational fact, 35 role self-evidence. 35 items have an activation rule. 177 items carry 221 suggested clause references (NCCG 2018 and NAICOM 2021).

## Templated items

| Item | Placeholder | Was |
|---|---|---|
| `BOARD-EFF-01` | `{board_composition.women}` | "Your Board has only one female member…". Asked only when the confirmed count is at most 1 under NCCG 2018. |
| `BOARD-STR-04`, `CHAIR-SELF-05`, `EXEC-SELF-02`, `EXEC-SELF-03`, `EXEC-SELF-04`, `ED-SELF-03` | `{review_year}` | "2022" |
| `COM-CORE-05`, `COM-CORE-19` | options relative to the year under review | options "2022 / 2021 / 2020 / 2019" |

An item whose placeholder fact isn't confirmed is shown as blocked in the preview, naming the missing fact. It is never asked with a gap in it.

## Items the system already knows (`known_from`)

| Item | Fact | Behaviour |
|---|---|---|
| `DIR-SELF-01`, `INED-IND-09` | `tenure_years` (from the confirmed appointment date) | skip |
| `DIR-SELF-02` | `expertise` | confirm |
| `CEO-SELF-01` | `other_board_roles` | confirm |
| `ED-SELF-01` | `committee_types` (from confirmed committee memberships) | confirm |
| `INED-IND-01` – `INED-IND-08` | the eight independence facts (`holds_company_shares` … `participates_in_share_or_incentive_scheme`) | skip once yes or no is confirmed; "unknown" is still asked |
| `COM-CORE-03` | `committee_member_count` (from confirmed memberships) | skip |
| `SEC-04`, `SEC-05`, `SEC-06` | `board_size`, `board_composition.executive_directors`, `board_composition.non_executive_directors` | confirm |

## Open questions for the consultant

- **Scales.** Is normalising every rating to 1–5 acceptable, given the original 3- and 4-point scales and the mix of "adequate" and "excellent" wording?
- **Thresholds.** Should `BOARD-EFF-01` fire at 1 woman or fewer, or at a different number?
- **Statutory audit committee.** `COM-SAC-*` items are told apart from a board audit committee by the word "statutory" in the committee's name, because both have the committee type `audit`. Is a separate committee type better?
- **Enterprise risk management and governance committee.** Its items are split by topic: remuneration policy goes to remuneration or governance committees, succession to nomination or governance committees, and its roles list to governance or risk committees. Check this matches how clients name their committees.
- **`COM-SAC-01`** says "the head of the committee … not below AGM". It probably means the head of internal audit (NAICOM 5.0 iii).
- **`PEER-EXEC-21`**, the supervising officer's grading: who supervises whom? The draft assumes the MD/CEO grades EDs and the chair grades the MD/CEO.
- **`COM-CORE-10`** had a stray sentence ("Committee is intolerant of mediocrity in management") that looks like a separate item. It is left out.
- **`COM-CORE-19`**: the EDs' last KPI assessment is asked on every committee form. Should it go to the remuneration or governance committee only?
- **Overlaps kept on purpose** (different respondents): `BOARD-DYN-12` with the chair peer items, `CHAIR-SELF-07` with `BOARD-RISK-04`, the whole-board meeting questions with the secretariat's, and `CHAIR-SELF-02` with `CEO-SELF-02`.
- **Secretariat follow-ups.** "If so, …" questions are separate items whose `guidance` names the question they follow. The rule language doesn't branch on answers, so assembly needs to handle these.
- **Length.** With every draft item, a VAL-001-style board gives each director about 64–96 minutes of questions (see the preview). The historical forms were just as long when added together; the consultant may want to trim.
- **`INED-IND-06`** asks about the last three years, but the profile fact `senior_service_with_regulator` has no time window.

## Fixture format (for the client's Assessment Intelligence Map)

The client's own methodology ("Document 2: Assessment Intelligence Map") can be transcribed into this shape and loaded with the same loader. A fixture is one JSON object:

```json
{
  "format": "cw-question-bank",
  "format_version": 1,
  "bank": "short-name-for-this-bank",
  "description": "Where the items came from",
  "source_forms": [{"form_id": "AIM", "name": "Assessment Intelligence Map", "items_before": 0, "bank_items": 0, "admin_fields_dropped": []}],
  "items": [ ... ]
}
```

`source_forms` is information only. Each item:

| Field | Required | Meaning |
|---|---|---|
| `code` | yes | Stable code: capital letters and digits in hyphenated parts, ending in a 2–3 digit number, e.g. `BOARD-EFF-01`. |
| `version` | yes | Whole number from 1. `(code, version)` is the identity the loader uses. |
| `status` | yes | `draft`, `approved` or `retired`. |
| `text` | yes | The question as the methodology words it. May contain `{placeholders}`. |
| `answer_type` | yes | `rating`, `yesno`, `comment`, `single_select` or `multi_select`. |
| `options` | select types | List of at least two option texts. |
| `scale` | rating | `{"min": 1, "max": 5, "labels": {"1": "Poor", …}, "dont_know": true}`; `dont_know` is optional. |
| `subject_types` | yes | Any of `BOARD`, `CHAIR`, `MD_CEO`, `ED`, `NED`, `INED`, `COMMITTEE`, `COMPANY_SECRETARY`. |
| `subject_binding` | yes | `none` (the board, or the secretariat as a function), `self` (the respondent), `each_subject_instance` (every person or committee of those types), or `respondent_committees` (each committee the respondent sits on). |
| `respondent_rule` | no | Who answers (rule language below). Empty means anyone. |
| `activation_rule` | no | When the item applies at all, e.g. a sector or code. |
| `theme_code`, `evidence_source_code` | yes | Codes from the taxonomy (`/api/v1/taxonomy`). |
| `known_from` | no | A fact key (below) whose confirmed value answers the item. |
| `known_from_behaviour` | no | `skip` (default) or `confirm`. |
| `placeholders` | if used | Fact keys used as `{key}` in the text or options. Every one used must be listed. |
| `guidance` | no | Notes for later AI phrasing, e.g. "for an ED, ask about their own division". |
| `governance_refs` | no | `[{"code": "NCCG_2018", "reference": "7.2.1"}]`, with references exactly as printed in the clause library. Optional `"status": "confirmed"`; the default is `suggested`. |
| `source_refs` | no | Where the item came from: `[{"form_id", "form", "item", "section", "original_text", "original_answer"}]`. Never a person's name. |
| `tag_notes` | no | `{"theme": {"status": "suggested", "reason": "…"}, …}` for `subject_types`, `subject_binding`, `respondent_rule`, `activation_rule`, `theme`, `evidence_source`, `governance_refs`. |
| `weight`, `sort_order`, `review_notes` | no | Number ≥ 0 (default 1), whole number, free text. |

### Rule language

A rule is empty (always true), a combinator, or one condition (an object with exactly one key). Unknown conditions are errors, never silently false. When the data needed to decide is missing, for example a participant's role isn't confirmed, the item is reported as blocked rather than left out.

```json
{"all": [ ... ]}   {"any": [ ... ]}   {"not": { ... }}
```

| Condition | Argument | True when |
|---|---|---|
| `respondent.role` | `["chair", "md_ceo", "ed", "ned", "ined", "company_secretary"]` | the respondent's confirmed governance role is listed |
| `respondent.is_subject` / `respondent.is_not_subject` | `true` | the subject is / isn't the respondent |
| `respondent.is_member_of_subject_committee` | `true` | the respondent sits on the subject committee |
| `respondent.chairs_subject_committee` | `true` | the respondent chairs it |
| `subject.type` | subject type codes | the subject is one of these |
| `subject.committee_type` | `["audit", "risk", "remuneration", "nomination", "finance", "governance", "other"]` | the subject committee has one of these types |
| `subject.committee_name_contains` | words | the subject committee's name contains one (case-insensitive) |
| `org.sector` | sector keys, e.g. `["insurance"]` | the company's sector is listed |
| `org.has_code` | e.g. `"NAICOM_2021"` | the evaluation is assessed against that code |
| `evaluation.scope_includes` | a subject type code | that subject type is in the evaluation's scope |
| `fact.known` / `fact.unknown` | a fact key | the fact has / hasn't a confirmed value (a tristate "unknown" counts as not known) |
| `fact.at_least` / `fact.at_most` | `{"key": "board_size", "value": 5}` | the confirmed number is ≥ / ≤ the value |

Fact keys: any organisation fact (`board_size`, `board_composition`, and its fields as `board_composition.women` etc.), any board member profile fact (`governance_role`, `board_appointment_date`, `expertise`, the independence facts, …), and derived values: `tenure_years` and `committee_types` for a person, `committee_member_count` for a committee, `review_year` for the evaluation. Person facts are read from the subject when the subject is a person, otherwise from the respondent. `POST /api/v1/question-bank/rules/validate` checks a rule and returns its plain-English reading. `GET /api/v1/question-bank/meta` lists every condition and fact key.

Example (`PEER-NED-04`): every other director rates each NED and INED.

```json
{
  "code": "PEER-NED-04", "version": 1, "status": "draft",
  "text": "Exhibits independent judgement in decision-making and board deliberations",
  "answer_type": "rating",
  "scale": {"min": 1, "max": 5, "labels": {"1": "Poor", "2": "Average", "3": "Good", "4": "Very good", "5": "Excellent"}},
  "subject_types": ["NED", "INED"], "subject_binding": "each_subject_instance",
  "respondent_rule": {"all": [{"respondent.role": ["chair", "md_ceo", "ed", "ned", "ined"]}, {"respondent.is_not_subject": true}]},
  "activation_rule": null,
  "theme_code": "INDEPENDENCE", "evidence_source_code": "PERCEPTION",
  "governance_refs": [{"code": "NCCG_2018", "reference": "6"}]
}
```
