import React, { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { questionBankApi } from "../../../api/questionBankApi.js";
import { color, font, radius, space } from "../../../theme.js";
import { Notice, SectionTitle } from "../companies/shared.jsx";
import { inputCss, useAsync } from "../companies/helpers.js";
import { SET_STATUS, SOURCE_LABELS, plural, shortName } from "./reviewHelpers.js";

/** Every question about one subject across all participants, grouped by bank item, to spot gaps and odd wordings. */
export default function SubjectReview({ ui, evalId }) {
  const { subjectId } = useParams();
  const navigate = useNavigate();
  const { Badge } = ui;
  const [subjects, setSubjects] = useState(null);
  const [loaded, setLoaded] = useState(null);
  const { error, run } = useAsync();

  useEffect(() => {
    run(async () => setSubjects((await questionBankApi.reviewSubjects(evalId)).items));
  }, [evalId, run]);
  const load = useCallback(() => {
    if (!subjectId) return;
    run(async () => setLoaded(await questionBankApi.reviewSubject(evalId, subjectId)));
  }, [evalId, subjectId, run]);
  useEffect(() => {
    load();
  }, [load]);
  const view = loaded && loaded.subject.id === subjectId ? loaded : null;

  return (
    <div style={{ display: "grid", gap: space.lg, gridTemplateColumns: "minmax(0, 1fr)" }}>
      {error ? <Notice tone="error">{error}</Notice> : null}
      <label style={{ display: "flex", gap: space.sm, alignItems: "center", fontSize: 13, flexWrap: "wrap" }}>
        Subject
        <select value={subjectId || ""} onChange={(e) => navigate(`/consultant/review/subjects/${e.target.value}`)} style={inputCss({ width: "auto", minWidth: 0, maxWidth: "100%" })}>
          <option value="" disabled>
            Choose the board, a committee or a person…
          </option>
          {(subjects || []).map((s) => (
            <option key={s.id} value={s.id}>
              {s.label} · {plural(s.questions, "question")}
              {s.too_few_raters ? " · too few raters" : ""}
            </option>
          ))}
        </select>
      </label>

      {!subjectId && subjects ? (
        <ul style={{ margin: 0, padding: 0, listStyle: "none", display: "grid", gap: space.sm, gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))" }}>
          {subjects.map((s) => (
            <li key={s.id} style={{ border: `1px solid ${color.border}`, borderRadius: radius.md, padding: space.md, background: color.surface }}>
              <Link to={`/consultant/review/subjects/${s.id}`} style={{ fontWeight: font.weight.bold, color: color.primaryText }}>
                {s.label}
              </Link>
              <div style={{ fontSize: 13, color: color.textMuted, marginTop: 2 }}>
                {plural(s.questions, "question")} · {plural(s.rater_count, "rater")}
              </div>
              {s.too_few_raters ? (
                <div style={{ marginTop: 4 }}>
                  <Badge tone="amber">Fewer than 3 raters</Badge>
                </div>
              ) : null}
            </li>
          ))}
        </ul>
      ) : null}

      {subjectId && !view ? <p style={{ color: color.textMuted }}>Loading…</p> : null}
      {view ? (
        <>
          <div style={{ display: "flex", gap: space.sm, flexWrap: "wrap", alignItems: "center" }}>
            <h2 style={{ margin: 0, fontSize: font.heading }}>{view.subject.label}</h2>
            <Badge tone="blue">{plural(view.questions, "question")}</Badge>
            <Badge tone={view.too_few_raters ? "amber" : "green"}>{plural(view.rater_count, "rater")}</Badge>
          </div>
          {view.too_few_raters ? (
            <Notice tone="warn">
              {`Only ${plural(view.rater_count, "person", "people")} other than the subject answer${view.rater_count === 1 ? "s" : ""} questions about ${view.subject.label}. Results from fewer than ${view.min_raters} raters can't be reported individually.`}
            </Notice>
          ) : null}
          {view.rater_warnings.map((w) => (
            <Notice key={w.set} tone="warn">
              {w.message} Raters: {w.raters.map(shortName).join(", ")}.
            </Notice>
          ))}
          {view.raters.length ? (
            <p style={{ margin: 0, fontSize: 13, color: color.textMuted }}>Raters: {view.raters.map(shortName).join(", ")}</p>
          ) : null}

          <section aria-label="Questions grouped by bank item" style={{ display: "grid", gap: space.sm }}>
            <SectionTitle hint="Each bank item once, with every participant who gets it and the wording they'll see.">Questions</SectionTitle>
            {view.groups.map((g) => (
              <details key={g.key} open={g.worded_differently} style={{ border: `1px solid ${g.worded_differently ? "#FED7AA" : color.border}`, borderRadius: radius.md, background: color.surface }}>
                <summary style={{ padding: space.md, cursor: "pointer", display: "flex", gap: space.sm, flexWrap: "wrap", alignItems: "baseline" }}>
                  <span style={{ flex: "1 1 320px", minWidth: 0 }}>
                    {g.bank_text || g.entries[0].text}{" "}
                    <span style={{ fontSize: font.small, color: color.textMuted }}>{g.code || SOURCE_LABELS[g.source]}</span>
                  </span>
                  <span style={{ fontSize: 13, color: color.textMuted }}>{plural(g.entries.length, "participant")}</span>
                  {g.worded_differently ? <Badge tone="amber">{`${g.wordings} different wordings`}</Badge> : null}
                </summary>
                <ul style={{ margin: 0, padding: `0 ${space.md}px ${space.md}px`, listStyle: "none", display: "grid", gap: space.xs }}>
                  {g.entries.map((e) => (
                    <li key={e.question_id} style={{ fontSize: 13, display: "grid", gridTemplateColumns: "minmax(120px, 200px) minmax(0, 1fr)", gap: space.sm, borderTop: `1px solid ${color.border}`, paddingTop: space.xs }}>
                      <Link to={`/consultant/review/participants/${e.participant_id}`} style={{ color: color.primaryText, fontWeight: font.weight.bold }}>
                        {shortName(e.label)}
                      </Link>
                      <span>
                        {e.text}{" "}
                        <span style={{ fontSize: font.small, color: color.textMuted }}>
                          {e.text_source !== "bank" ? `${SOURCE_LABELS[e.text_source]} · ` : ""}
                          {(SET_STATUS[e.set_status] || SET_STATUS.draft).label.toLowerCase()}
                        </span>
                      </span>
                    </li>
                  ))}
                </ul>
              </details>
            ))}
            {!view.groups.length ? <p style={{ margin: 0, color: color.textMuted }}>No questions about this subject yet.</p> : null}
          </section>
        </>
      ) : null}
    </div>
  );
}
