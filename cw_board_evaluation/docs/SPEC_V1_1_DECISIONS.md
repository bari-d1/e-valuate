# Methodology spec v1.1: four analysis and reporting decisions

For the Architecture & Philosophy Register. Four places where the analysis and
report code broke rules in the client's methodology spec (v1.1), what was decided,
and where it lives. Implemented November 2026 in four stacked PRs (#22 to #25).

Clause references: AT04 is the spec's acceptance test number. The other rules are
quoted as stated in the spec; their clause numbers are marked *to confirm* and
should be filled in from the spec document.

## 1. Questionnaire answers never establish compliance

**Rule (spec v1.1, clause to confirm):** a regulatory obligation must never be
inferred from a questionnaire response alone; self-reported practice is not
compliance.

**Decision:** the finding kind `compliance_gap` is replaced by `practice_gap`:
"self-reported practice differs from the expected answer; needs verification".
The computed statement says the answer is self-reported and must be checked
against the company's documents, and never uses "compliance", "breach" or
"non-compliant". AI drafts of this kind must rest on a factual answer and may
not state a compliance conclusion. The clause and evidence links are kept, so the
consultant can see which governance clause the expected answer comes from.

**Where:** `app/services/analysis.py` (`draft_computed_findings`),
`app/services/analysis_ai.py` (`validate`), `ai/prompts/analysis_synthesis.py`,
migration `d1a6f0c3e8b2`.

## 2. Score thresholds are configuration the client approves, not methodology

**Rule (spec v1.1, clause to confirm):** scoring and thresholds are reserved for
the client; a high mean must never be treated as effectiveness.

**Decision:** the strength, concern and self/peer-gap thresholds (4.2, 4.5, 2.5,
1.0) stay only as defaults. Each run records the thresholds it used in
`analysis_runs.settings["thresholds"]`, can be started with others, and carries
`settings["thresholds_status"] = "unapproved"`. Computed strengths, concerns and
gaps from an unapproved run are shown, in the Findings UI and in the report, as
"Draft signal, thresholds not approved". The statistics (mean, spread, consensus,
distribution, suppression) are unchanged.

**Open:** there is no approval step yet, so every run is unapproved until the
client's sign-off flow exists.

**Where:** `app/domain/analysis_rules.py` (`resolve_thresholds`, `thresholds`),
migration `e5c2a7d40f19`.

## 3. No approved finding without evidence

**Rule (spec v1.1, acceptance test AT04):** a finding without supporting evidence
IDs can't be approved.

**Decision:** consultants' findings are created as drafts. A finding can only
become `accepted` or `edited` while at least one `finding_evidence` row links it
to the run's evidence. Evidence can be linked and unlinked after creation (same run
only), and unlinking the last piece of an approved finding sends it back to
draft with a note. Completion counts only approved findings backed by evidence.
Findings approved without evidence before this change were moved to draft with a
note recording why and their earlier status; nothing was deleted.

**Where:** `app/services/analysis.py` (`update_finding`, `link_evidence`,
`unlink_evidence`, `completion_blockers`), `findings.note`, migration
`f7d3b9e2a614`.

## 4. The report is built from approved findings only

**Rule (spec v1.1, clause to confirm):** report content must come from approved
findings and cited evidence only, and every finding must be traceable.

**Decision:** report generation reads the latest analysis run marked complete
(none: a clear 409, no report). It includes only approved findings that cite
evidence and approved conclusions, grouped by subject in the analysis order, each
finding with its kind, statement, support, theme, clauses and evidence references
(evidence id, question, respondent category and per-run pseudonym). `summary_json`
records the run id, the finding and conclusion ids used, the run's settings
(including thresholds and their status) and when the report was made. The demo
analytics and placeholder regulatory text are gone from report generation.

No respondent is named. Because individual directors are both subjects and
respondents, they appear in the report by role ("the chair", "executive director
A"), and names in statements and question text are replaced the same way. The
finding id keeps every statement traceable to the approved original.

Each finding carries `theme_code`, so a grouping by dimension can be added later
without changing the shape (`grouped_by` is `"subject"` today).

**Open:** AI polishing of an executive summary is not built. It would need a check
that the polished text introduces no finding of its own; until then the report
contains no AI-written text.

**Where:** `app/services/reporting.py`, `app/services/docx_exporter.py`,
`cw-board-ui/src/pages/consultant/GenerateReport.jsx`. Reports saved in the
earlier layout still display and export.
