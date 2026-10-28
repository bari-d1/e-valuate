import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, NavLink, Navigate, Route, Routes, useParams } from "react-router-dom";
import { analysisApi } from "../../../api/analysisApi.js";
import { color, font, radius, space } from "../../../theme.js";
import { inputCss, useAsync } from "../companies/helpers.js";
import { Notice, Panel } from "../companies/shared.jsx";
import { ScoreBars, SelfPeerChart } from "./Charts.jsx";
import { AddFinding, ConclusionEditor, FindingsList } from "./FindingParts.jsx";
import { KIND_LABELS, ROLE_LABELS, fmt, isAccepted, plural } from "./findingsHelpers.js";

/**
 * Findings: run the analysis of an assembled evaluation, read the results per subject (the board,
 * committees, each director, the secretariat), and decide the findings and conclusions.
 * Respondents are never named: only their category.
 */

const tabStyle = ({ isActive }) => ({
  padding: "6px 12px",
  borderRadius: radius.sm,
  border: `1px solid ${isActive ? color.primarySoftBorder : "transparent"}`,
  background: isActive ? color.primarySoft : "transparent",
  color: isActive ? color.primaryText : color.text,
  fontWeight: font.weight.bold,
  fontSize: font.body,
  textDecoration: "none",
});

function Section({ title, hint, children }) {
  return (
    <section style={{ display: "grid", gap: space.sm }}>
      <div>
        <h3 style={{ margin: 0, fontSize: 15, fontWeight: font.weight.heavy }}>{title}</h3>
        {hint ? <p style={{ margin: "2px 0 0", fontSize: 13, color: color.textMuted }}>{hint}</p> : null}
      </div>
      {children}
    </section>
  );
}

// ----------------------------
// Overview
// ----------------------------

function RunControls({ ui, evalId, runs, aiAvailable, current, onStarted, onSelect }) {
  const { Button, Badge } = ui;
  const [minRaters, setMinRaters] = useState(current?.settings?.min_raters ?? 3);
  const [unsubmitted, setUnsubmitted] = useState(false);
  const [ai, setAi] = useState(false);
  const { busy, error, run } = useAsync();
  const running = runs.some((r) => r.status === "running");
  return (
    <Panel style={{ display: "grid", gap: space.md }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: space.md, flexWrap: "wrap", alignItems: "center" }}>
        <div style={{ fontSize: 13 }}>
          {current ? (
            <>
              <strong>Analysis of {new Date(current.created_at).toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}</strong>{" "}
              <Badge tone={current.status === "done" ? (current.completed_at ? "green" : "blue") : current.status === "failed" ? "red" : "amber"}>
                {current.completed_at ? "Complete" : { done: "Ready to review", running: "Running…", failed: "Failed" }[current.status]}
              </Badge>
              <div style={{ color: color.textMuted, marginTop: 2 }}>
                At least {current.settings.min_raters} people for results about a director or a group ·{" "}
                {current.settings.include_unsubmitted ? "includes forms not yet submitted" : "submitted forms only"}
                {current.respondents ? ` · ${plural(current.respondents.included, "respondent")}` : ""}
                {current.settings.ai_used ? " · AI drafts included" : ""}
              </div>
              {current.error ? <div style={{ color: color.danger }}>{current.error}</div> : null}
            </>
          ) : (
            <strong>No analysis yet.</strong>
          )}
        </div>
        {runs.length > 1 ? (
          <label style={{ display: "flex", gap: 6, alignItems: "center", fontSize: 13 }}>
            Run
            <select value={current?.run_id || ""} onChange={(e) => onSelect(e.target.value)} style={inputCss({ width: "auto" })}>
              {runs.map((r) => (
                <option key={r.run_id} value={r.run_id}>
                  {new Date(r.created_at).toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}
                  {r.completed_at ? " (complete)" : ""}
                </option>
              ))}
            </select>
          </label>
        ) : null}
      </div>
      <div style={{ display: "flex", gap: space.md, flexWrap: "wrap", alignItems: "end", fontSize: 13 }}>
        <label style={{ display: "grid", gap: 4 }}>
          Minimum people per result
          <input type="number" min={2} max={10} value={minRaters} onChange={(e) => setMinRaters(Number(e.target.value))} style={inputCss({ width: 90 })} />
        </label>
        <label style={{ display: "flex", gap: 6, alignItems: "center", minHeight: 38 }}>
          <input type="checkbox" checked={unsubmitted} onChange={(e) => setUnsubmitted(e.target.checked)} />
          Include forms not yet submitted
        </label>
        {aiAvailable ? (
          <label style={{ display: "flex", gap: 6, alignItems: "center", minHeight: 38 }}>
            <input type="checkbox" checked={ai} onChange={(e) => setAi(e.target.checked)} />
            Ask AI for draft findings
          </label>
        ) : (
          <span style={{ color: color.textMuted, minHeight: 38, display: "flex", alignItems: "center" }}>AI drafting is switched off.</span>
        )}
        <Button
          disabled={busy || running}
          onClick={() =>
            run(async () => {
              const r = await analysisApi.start(evalId, { min_raters: minRaters, include_unsubmitted: unsubmitted, ai });
              await onStarted(r.run_id);
            })
          }
        >
          {running ? "Running…" : current ? "Re-run analysis" : "Run analysis"}
        </Button>
      </div>
      {current && runs.length > 1 && current.status === "done" ? (
        <span style={{ fontSize: 13 }}>
          Re-running keeps earlier runs. <Link to="/consultant/findings/compare" style={{ color: color.primaryText }}>Compare runs</Link>
        </span>
      ) : null}
      {error ? <Notice tone="error">{error}</Notice> : null}
    </Panel>
  );
}

function SubjectCard({ ui, s, counts }) {
  const { Badge } = ui;
  const themes = Object.values(s.themes).filter((t) => !t.suppressed);
  const c = counts || { draft: 0, accepted: 0 };
  return (
    <li style={{ listStyle: "none" }}>
      <Link
        to={`/consultant/findings/subjects/${s.subject_id}`}
        style={{ display: "grid", gap: space.sm, padding: space.md, borderRadius: radius.md, border: `1px solid ${color.border}`, background: color.surface, color: color.text, textDecoration: "none", height: "100%", boxSizing: "border-box" }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", gap: space.sm, alignItems: "flex-start" }}>
          <div>
            <div style={{ fontWeight: font.weight.heavy }}>{s.name}</div>
            <div style={{ fontSize: 12, color: color.textMuted }}>
              {ROLE_LABELS[s.type]} · {s.completion.answered} of {s.completion.eligible} answered
            </div>
          </div>
          <span style={{ fontSize: 12, color: color.textMuted, whiteSpace: "nowrap" }}>
            {c.accepted} accepted · {c.draft} draft
          </span>
        </div>
        {themes.length ? (
          <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "grid", gap: 2, fontSize: 13 }}>
            {themes.slice(0, 4).map((t) => (
              <li key={t.theme_code} style={{ display: "flex", justifyContent: "space-between", gap: space.sm }}>
                <span>{t.label}</span>
                <strong style={{ color: t.mean <= 2.5 ? color.danger : t.mean >= 4.2 ? "#047857" : color.text }}>{fmt(t.mean)}</strong>
              </li>
            ))}
            {themes.length > 4 ? <li style={{ color: color.textMuted }}>and {themes.length - 4} more</li> : null}
          </ul>
        ) : (
          <span style={{ fontSize: 13, color: color.textMuted }}>{s.facts.length ? `${plural(s.facts.length, "factual answer")}` : "No scores"}</span>
        )}
        <div style={{ display: "flex", gap: space.xs, flexWrap: "wrap" }}>
          {s.small_sample ? <Badge tone="amber">Small sample</Badge> : null}
          {s.suppressed.length ? <Badge tone="gray">{plural(s.suppressed.length, "result")} withheld</Badge> : null}
          {s.facts.some((f) => f.check && !f.check.met) ? <Badge tone="red">Compliance gap</Badge> : null}
          {s.self_peer.some((x) => x.flagged) ? <Badge tone="purple">Self/peer gap</Badge> : null}
        </div>
      </Link>
    </li>
  );
}

function Overview({ ui, ctx }) {
  const { evalId, runs, current, detail, aiAvailable, select, reload } = ctx;
  const results = detail?.results;
  return (
    <div style={{ display: "grid", gap: space.lg, gridTemplateColumns: "minmax(0, 1fr)" }}>
      <RunControls
        ui={ui}
        evalId={evalId}
        runs={runs}
        aiAvailable={aiAvailable}
        current={current}
        onSelect={select}
        onStarted={async (id) => {
          await reload(id);
        }}
      />
      {results ? (
        <>
          {results.include_unsubmitted ? (
            <Notice>This run includes answers from forms that haven't been submitted yet ({plural(results.respondents.in_progress, "person", "people")}). They may still change.</Notice>
          ) : null}
          <ul style={{ margin: 0, padding: 0, display: "grid", gap: space.md, gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))" }}>
            {results.order.map((sid) => (
              <SubjectCard key={sid} ui={ui} s={results.subjects[sid]} counts={detail.finding_counts?.[sid]} />
            ))}
          </ul>
          {results.ai ? (
            <details style={{ fontSize: 13 }}>
              <summary style={{ cursor: "pointer" }}>
                AI drafts: {results.ai.kept} kept, {results.ai.dropped.length} dropped by the checks
              </summary>
              <ul style={{ paddingLeft: 18, color: color.textMuted }}>
                {results.ai.dropped.map((d, i) => (
                  <li key={i}>
                    <span style={{ color: color.text }}>{d.subject}</span>: {d.reason}
                    {d.statement ? ` (“${d.statement.slice(0, 140)}”)` : ""}
                  </li>
                ))}
              </ul>
            </details>
          ) : null}
        </>
      ) : current?.status === "running" ? (
        <p style={{ color: color.textMuted }}>Analysing the answers…</p>
      ) : null}
    </div>
  );
}

// ----------------------------
// One subject
// ----------------------------

function SubjectView({ ui, ctx }) {
  const { subjectId } = useParams();
  const { evalId, current, detail, conclusions, reloadDetail } = ctx;
  const [findings, setFindings] = useState(null);
  const [evidence, setEvidence] = useState(null);
  const { error, run } = useAsync();
  const s = detail?.results?.subjects?.[subjectId];
  const runId = current?.run_id;
  const readOnly = !!current?.completed_at;

  const loadFindings = useCallback(
    () => run(async () => setFindings((await analysisApi.findings(evalId, runId, subjectId)).findings)),
    [evalId, runId, subjectId, run]
  );
  useEffect(() => {
    if (runId && s) loadFindings();
  }, [runId, s, loadFindings]);
  const loadEvidence = () => run(async () => setEvidence((await analysisApi.evidence(evalId, runId, subjectId)).evidence));
  const changed = async () => {
    await loadFindings();
    await reloadDetail();
  };

  if (!s) return detail ? <Notice>That subject isn't in this analysis.</Notice> : <p style={{ color: color.textMuted }}>Loading…</p>;
  const themes = Object.entries(s.themes).map(([code, t]) => ({ key: code, label: t.label, mean: t.mean, raters: t.raters, consensus: t.consensus, distribution: t.distribution, suppressed: t.suppressed }));
  const conclusion = conclusions.find((c) => c.subject_id === subjectId);
  const comments = Object.entries(s.comments);
  return (
    <div style={{ display: "grid", gap: space.xl, gridTemplateColumns: "minmax(0, 1fr)" }}>
      <div>
        <Link to="/consultant/findings" style={{ fontSize: 13, color: color.primaryText }}>← All subjects</Link>
        <h2 style={{ margin: `${space.sm}px 0 0`, fontSize: 20 }}>{s.name}</h2>
        <div style={{ fontSize: 13, color: color.textMuted }}>
          {ROLE_LABELS[s.type]} · {s.completion.answered} of {s.completion.eligible} people answered about {s.kind === "person" ? "them" : "it"}
        </div>
      </div>
      {s.notice ? <Notice>{s.notice}</Notice> : null}
      {s.suppressed.length ? (
        <Notice>
          Some results are withheld to protect a small group: {s.suppressed.map((x) => x.what).join(", ")}. {s.suppressed[0].reason}
        </Notice>
      ) : null}
      {s.in_progress_included ? <Notice>Includes answers from forms that haven't been submitted yet.</Notice> : null}

      {themes.length ? (
        <Section title="Scores by theme" hint="Average rating on a 1 to 5 scale from people other than the subject. Tap a bar for the spread of ratings.">
          <ScoreBars rows={themes} />
          {Object.values(s.themes).some((t) => t.split) ? (
            <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13, color: color.textMuted }}>
              {Object.values(s.themes).filter((t) => t.split).map((t) => (
                <li key={t.theme_code}>
                  <span style={{ color: color.text }}>{t.label}</span>:{" "}
                  {t.split.groups ? t.split.groups.map((g) => `${g.label} ${fmt(g.mean)} (${g.raters})`).join(" · ") : t.split.suppressed}
                </li>
              ))}
            </ul>
          ) : null}
        </Section>
      ) : null}

      {s.self_peer.length ? (
        <Section title="Self versus colleagues" hint="The core statements: the subject's own rating against colleagues' average. A gap of 1 point or more is flagged.">
          <SelfPeerChart rows={s.self_peer} />
        </Section>
      ) : null}

      {s.choices.length ? (
        <Section title="Yes/no and choice questions">
          <ul style={{ margin: 0, padding: 0, listStyle: "none", display: "grid", gap: space.sm, fontSize: 13 }}>
            {s.choices.map((c) => (
              <li key={c.code}>
                <div style={{ fontWeight: font.weight.bold }}>{c.question}</div>
                <div style={{ color: color.textMuted }}>
                  {c.suppressed || Object.entries(c.counts).map(([k, v]) => `${k}: ${v} (${c.percentages[k]}%)`).join(" · ")}
                </div>
              </li>
            ))}
          </ul>
        </Section>
      ) : null}

      {s.facts.length || s.profile_facts?.length ? (
        <Section title="Facts and compliance checks" hint="Factual answers are listed, never averaged. A check appears where good practice expects a particular answer under a governance clause.">
          <ul style={{ margin: 0, padding: 0, listStyle: "none", display: "grid", gap: space.sm, fontSize: 13 }}>
            {[...s.facts].sort((a, b) => (b.check && !b.check.met) - (a.check && !a.check.met)).map((f) => (
              <li key={f.code} style={{ padding: space.sm, borderRadius: radius.sm, border: `1px solid ${f.check && !f.check.met ? color.dangerBorder : color.border}` }}>
                <div style={{ fontWeight: font.weight.bold }}>{f.question}</div>
                <div>{f.answers.map((a) => `${a.value} (${a.category})`).join("; ")}</div>
                {f.check ? (
                  <div style={{ color: f.check.met ? "#047857" : color.danger, fontWeight: font.weight.bold }}>
                    {f.check.met ? "Meets" : "Falls short of"} good practice (expected “{f.check.expected}”)
                  </div>
                ) : null}
                {f.clauses.length ? (
                  <div style={{ color: color.textMuted }}>{f.clauses.map((c) => `${c.label}${c.heading ? `: ${c.heading}` : ""}`).join(" · ")}</div>
                ) : null}
              </li>
            ))}
            {(s.profile_facts || []).map((f) => (
              <li key={f.label} style={{ padding: space.sm, borderRadius: radius.sm, border: `1px solid ${color.border}` }}>
                <span style={{ fontWeight: font.weight.bold }}>{f.label}</span>: {f.value}
                <span style={{ color: color.textMuted }}> · {f.source}</span>
              </li>
            ))}
          </ul>
        </Section>
      ) : null}

      {comments.length || s.comments_suppressed ? (
        <Section title="Comments" hint="Grouped by theme, with the respondent's category only.">
          {s.comments_suppressed ? <Notice>{s.comments_suppressed}</Notice> : null}
          {comments.map(([code, list]) => (
            <div key={code}>
              <div style={{ fontWeight: font.weight.bold, fontSize: 13 }}>{s.themes[code]?.label || ctx.themeName(code)}</div>
              <ul style={{ margin: "4px 0 0", paddingLeft: 18, fontSize: 14, display: "grid", gap: 4 }}>
                {list.map((c) => (
                  <li key={c.evidence_id}>
                    “{c.text}” <span style={{ color: color.textMuted, fontSize: 12 }}>· {c.category}</span>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </Section>
      ) : null}

      <Section title="Findings" hint="Drafts from the numbers (and from AI, when switched on). Accept, edit or reject each one; nothing goes in the report until it's accepted.">
        {error ? <Notice tone="error">{error}</Notice> : null}
        {findings ? (
          <FindingsList ui={ui} evalId={evalId} runId={runId} findings={findings} evidence={evidence} onLoadEvidence={loadEvidence} onChanged={changed} readOnly={readOnly} />
        ) : (
          <p style={{ color: color.textMuted }}>Loading…</p>
        )}
        {!readOnly ? (
          <AddFinding ui={ui} evalId={evalId} runId={runId} subjectId={subjectId} themes={themes.map((t) => ({ code: t.key, label: t.label }))} onAdded={changed} />
        ) : null}
      </Section>

      <ConclusionEditor
        key={`${runId}-${subjectId}-${conclusion?.conclusion_id || "new"}`}
        ui={ui}
        evalId={evalId}
        runId={runId}
        subjectId={subjectId}
        conclusion={conclusion}
        onChanged={reloadDetail}
        readOnly={readOnly}
        allowNoFindings
        title={`Conclusion for ${s.name}`}
      />
    </div>
  );
}

// ----------------------------
// Overall
// ----------------------------

function OverallView({ ui, ctx }) {
  const { Button } = ui;
  const { evalId, current, detail, conclusions, reloadDetail } = ctx;
  const [all, setAll] = useState(null);
  const { busy, error, run } = useAsync();
  const runId = current?.run_id;
  useEffect(() => {
    if (runId && detail) run(async () => setAll((await analysisApi.findings(evalId, runId)).findings));
  }, [evalId, runId, detail, run]);
  if (!detail?.results) return <p style={{ color: color.textMuted }}>Run the analysis first.</p>;
  const overall = conclusions.find((c) => !c.subject_id);
  const res = detail.results;
  const readOnly = !!current.completed_at;
  return (
    <div style={{ display: "grid", gap: space.xl, gridTemplateColumns: "minmax(0, 1fr)" }}>
      <ConclusionEditor
        key={`${runId}-overall-${overall?.conclusion_id || "new"}`}
        ui={ui}
        evalId={evalId}
        runId={runId}
        subjectId={null}
        conclusion={overall}
        onChanged={reloadDetail}
        readOnly={readOnly}
        title="Overall conclusion"
      />
      <Section title="Accepted findings by subject">
        {all ? (
          <ul style={{ margin: 0, padding: 0, listStyle: "none", display: "grid", gap: space.md }}>
            {res.order.map((sid) => {
              const fs = all.filter((f) => f.subject_id === sid && isAccepted(f));
              const c = conclusions.find((x) => x.subject_id === sid);
              return (
                <li key={sid}>
                  <Link to={`/consultant/findings/subjects/${sid}`} style={{ fontWeight: font.weight.bold, color: color.primaryText }}>
                    {res.subjects[sid].name}
                  </Link>
                  {fs.length ? (
                    <ul style={{ margin: "4px 0 0", paddingLeft: 18, fontSize: 14, display: "grid", gap: 2 }}>
                      {fs.map((f) => (
                        <li key={f.finding_id}>
                          <span style={{ color: color.textMuted }}>{KIND_LABELS[f.kind]}: </span>
                          {f.statement}
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <div style={{ fontSize: 13, color: color.textMuted }}>
                      {c?.no_findings ? "Nothing to report." : "No accepted findings yet."}
                    </div>
                  )}
                </li>
              );
            })}
          </ul>
        ) : (
          <p style={{ color: color.textMuted }}>Loading…</p>
        )}
      </Section>
      <Panel style={{ display: "grid", gap: space.sm }}>
        {current.completed_at ? (
          <strong style={{ color: "#047857" }}>
            Analysis marked complete by {current.completed_by} on {new Date(current.completed_at).toLocaleDateString("en-GB")}.
          </strong>
        ) : (
          <>
            {detail.blockers.length ? (
              <>
                <strong>Before marking the analysis complete:</strong>
                <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13 }}>
                  {detail.blockers.map((b) => <li key={b}>{b}</li>)}
                </ul>
              </>
            ) : (
              <strong>Every subject has an accepted finding or a note, and the overall conclusion is accepted.</strong>
            )}
            <div>
              <Button
                disabled={busy || detail.blockers.length > 0}
                onClick={() => run(async () => { await analysisApi.complete(evalId, runId); await reloadDetail(); })}
              >
                Mark analysis complete
              </Button>
            </div>
          </>
        )}
        {error ? <Notice tone="error">{error}</Notice> : null}
      </Panel>
    </div>
  );
}

// ----------------------------
// Comparing runs
// ----------------------------

function CompareView({ ui, ctx }) {
  const { evalId, runs } = ctx;
  const done = runs.filter((r) => r.status === "done");
  const [picked, setPicked] = useState({ old: "", new: "" });
  // Until the consultant picks, compare the two latest finished runs (the list may still be loading)
  const oldId = picked.old || done[1]?.run_id || "";
  const newId = picked.new || done[0]?.run_id || "";
  const setOldId = (v) => setPicked((p) => ({ ...p, old: v }));
  const setNewId = (v) => setPicked((p) => ({ ...p, new: v }));
  const [data, setData] = useState(null);
  const { error, run } = useAsync();
  useEffect(() => {
    if (oldId && newId && oldId !== newId) run(async () => setData(await analysisApi.compare(evalId, oldId, newId)));
  }, [evalId, oldId, newId, run]);
  if (done.length < 2) return <Notice>Compare needs two finished runs. Re-run the analysis after late answers to compare.</Notice>;
  const label = (r) => new Date(r.created_at).toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
  const pick = (value, set) => (
    <select value={value} onChange={(e) => set(e.target.value)} style={inputCss({ width: "auto" })}>
      {done.map((r) => <option key={r.run_id} value={r.run_id}>{label(r)}</option>)}
    </select>
  );
  const cell = (x) => (!x ? "—" : x.suppressed ? `withheld (${x.raters})` : `${fmt(x.mean)} (${x.raters})`);
  return (
    <div style={{ display: "grid", gap: space.lg, gridTemplateColumns: "minmax(0, 1fr)" }}>
      <div style={{ display: "flex", gap: space.md, flexWrap: "wrap", alignItems: "center", fontSize: 13 }}>
        <label style={{ display: "flex", gap: 6, alignItems: "center" }}>Earlier {pick(oldId, setOldId)}</label>
        <label style={{ display: "flex", gap: 6, alignItems: "center" }}>Later {pick(newId, setNewId)}</label>
      </div>
      {error ? <Notice tone="error">{error}</Notice> : null}
      {data ? (
        <>
          <p style={{ margin: 0, fontSize: 14 }}>
            Respondents {data.respondents.before} → {data.respondents.after} · answers used {data.evidence_rows.before} → {data.evidence_rows.after}
          </p>
          <div style={ui.tableWrapStyle()}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 14 }}>
              <thead>
                <tr style={{ background: color.surfaceMuted, textAlign: "left" }}>
                  {["Subject", "Theme", "Earlier (raters)", "Later (raters)"].map((h) => <th key={h} scope="col" style={ui.tdStyle()}>{h}</th>)}
                </tr>
              </thead>
              <tbody>
                {data.changes.map((c, i) => (
                  <tr key={i} style={{ borderTop: `1px solid ${color.border}` }}>
                    <td style={ui.tdStyle()}>{c.subject}</td>
                    <td style={ui.tdStyle()}>{c.what}</td>
                    <td style={ui.tdStyle()}>{cell(c.before)}</td>
                    <td style={ui.tdStyle()}>{cell(c.after)}</td>
                  </tr>
                ))}
                {!data.changes.length ? (
                  <tr><td colSpan={4} style={{ ...ui.tdStyle(), color: color.textMuted }}>No changes in the results.</td></tr>
                ) : null}
              </tbody>
            </table>
          </div>
          <p style={{ margin: 0, fontSize: 13, color: color.textMuted }}>
            Drafted from the numbers:{" "}
            {Object.entries(data.computed_findings).map(([k, v]) => `${KIND_LABELS[k]} ${v.before} → ${v.after}`).join(" · ")}
          </p>
        </>
      ) : null}
    </div>
  );
}

// ----------------------------
// Page
// ----------------------------

export default function FindingsPage({ ui, evalId }) {
  const { Card } = ui;
  const [runs, setRuns] = useState([]);
  const [aiAvailable, setAiAvailable] = useState(false);
  const [selected, setSelected] = useState(null);
  const [detail, setDetail] = useState(null);
  const [conclusions, setConclusions] = useState([]);
  const [legacy, setLegacy] = useState("");
  const [themeNames, setThemeNames] = useState({});
  const { error, run } = useAsync();
  const timer = useRef(null);

  const current = useMemo(() => runs.find((r) => r.run_id === selected) || runs[0] || null, [runs, selected]);

  const loadRuns = useCallback(async () => {
    try {
      const r = await analysisApi.runs(evalId);
      setRuns(r.runs);
      setAiAvailable(r.ai_available);
      setLegacy("");
      return r.runs;
    } catch (e) {
      if (e.status === 409) {
        setLegacy(e.message);
        return [];
      }
      throw e;
    }
  }, [evalId]);

  const loadDetail = useCallback(
    async (runId) => {
      if (!runId) return;
      const d = await analysisApi.run(evalId, runId);
      setDetail(d);
      if (d.status === "done") {
        setConclusions((await analysisApi.conclusions(evalId, runId)).conclusions);
        const names = {};
        Object.values(d.results.subjects).forEach((s) => Object.values(s.themes).forEach((t) => (names[t.theme_code] = t.label)));
        setThemeNames(names);
      }
    },
    [evalId]
  );

  const reload = useCallback(
    (runId) =>
      run(async () => {
        const list = await loadRuns();
        const id = runId || selected || list[0]?.run_id;
        if (runId) setSelected(runId);
        await loadDetail(id);
      }),
    [run, loadRuns, loadDetail, selected]
  );

  useEffect(() => {
    if (evalId) reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [evalId]);

  // Poll while a run is in progress
  useEffect(() => {
    clearTimeout(timer.current);
    if (current?.status === "running") timer.current = setTimeout(() => reload(current.run_id), 1500);
    return () => clearTimeout(timer.current);
  }, [current, reload]);

  const ctx = {
    evalId,
    runs,
    current: current && detail && detail.run_id === current.run_id ? { ...current, ...detail } : current,
    detail: detail && current && detail.run_id === current.run_id ? detail : null,
    conclusions,
    aiAvailable,
    themeName: (code) => themeNames[code] || "General",
    select: (id) => {
      setSelected(id);
      run(() => loadDetail(id));
    },
    reload,
    reloadDetail: () => run(async () => { await loadRuns(); await loadDetail(current?.run_id); }),
  };

  return (
    <Card title="Findings" subtitle="What the answers show, subject by subject: scores, self versus colleagues, facts and compliance, and the findings that go into the report.">
      {!evalId ? <Notice>Choose an evaluation first.</Notice> : null}
      {legacy ? <Notice>{legacy}</Notice> : null}
      {error ? <Notice tone="error">{error}</Notice> : null}
      {evalId && !legacy ? (
        <>
          <nav aria-label="Findings views" style={{ display: "flex", gap: space.xs, flexWrap: "wrap", marginBottom: space.lg }}>
            <NavLink to="/consultant/findings" end style={tabStyle}>Subjects</NavLink>
            <NavLink to="/consultant/findings/overall" style={tabStyle}>Overall</NavLink>
            <NavLink to="/consultant/findings/compare" style={tabStyle}>Compare runs</NavLink>
          </nav>
          <Routes>
            <Route index element={<Overview ui={ui} ctx={ctx} />} />
            <Route path="subjects/:subjectId" element={<SubjectView ui={ui} ctx={ctx} />} />
            <Route path="overall" element={<OverallView ui={ui} ctx={ctx} />} />
            <Route path="compare" element={<CompareView ui={ui} ctx={ctx} />} />
            <Route path="*" element={<Navigate to="/consultant/findings" replace />} />
          </Routes>
        </>
      ) : null}
    </Card>
  );
}
