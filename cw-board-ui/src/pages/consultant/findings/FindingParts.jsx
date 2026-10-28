import React, { useState } from "react";
import { analysisApi } from "../../../api/analysisApi.js";
import { color, radius, space } from "../../../theme.js";
import { inputCss, useAsync } from "../companies/helpers.js";
import { LinkButton, Notice, Panel } from "../companies/shared.jsx";
import { KIND_LABELS, KIND_ORDER, KIND_TONES, ORIGIN_LABELS, STATUS_LABELS, SUPPORT_LABELS, isAccepted } from "./findingsHelpers.js";

/** Findings with their evidence, the consultant's decisions on them, and conclusions. */

function EvidenceList({ ids, evidence }) {
  if (!evidence) return <p style={{ fontSize: 13, color: color.textMuted, margin: 0 }}>Loading…</p>;
  const byId = Object.fromEntries(evidence.map((e) => [e.evidence_id, e]));
  const rows = ids.map((id) => byId[id]).filter(Boolean);
  const hidden = ids.length - rows.length;
  return (
    <div style={{ display: "grid", gap: space.xs }}>
      <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "grid", gap: 4, fontSize: 13 }}>
        {rows.map((e) => (
          <li key={e.evidence_id} style={{ padding: "6px 8px", borderRadius: radius.sm, background: color.surfaceMuted }}>
            <span style={{ color: color.textMuted }}>{e.category}{e.in_progress ? " (form not submitted)" : ""}: </span>
            <strong style={{ whiteSpace: "pre-wrap" }}>{e.value}</strong>
            <div style={{ fontSize: 12, color: color.textMuted }}>{e.question}</div>
          </li>
        ))}
      </ul>
      {hidden ? <span style={{ fontSize: 12, color: color.textMuted }}>{hidden} more answer{hidden === 1 ? "" : "s"} not shown to protect small groups.</span> : null}
    </div>
  );
}

export function FindingCard({ ui, evalId, runId, finding, evidence, onLoadEvidence, onChanged, readOnly }) {
  const { Badge, Button } = ui;
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(finding.statement);
  const [showEvidence, setShowEvidence] = useState(false);
  const { busy, error, run } = useAsync();
  const act = (body) =>
    run(async () => {
      await analysisApi.updateFinding(evalId, runId, finding.finding_id, body);
      setEditing(false);
      await onChanged();
    });
  const rejected = finding.status === "rejected";
  return (
    <li style={{ listStyle: "none", padding: space.md, borderRadius: radius.md, border: `1px solid ${isAccepted(finding) ? "#A7F3D0" : color.border}`, background: rejected ? color.surfaceMuted : color.surface, opacity: rejected ? 0.7 : 1 }}>
      <div style={{ display: "flex", gap: space.xs, flexWrap: "wrap", alignItems: "center" }}>
        <Badge tone={KIND_TONES[finding.kind]}>{KIND_LABELS[finding.kind]}</Badge>
        <Badge tone={finding.support === "conflicting" ? "amber" : "gray"}>{SUPPORT_LABELS[finding.support]}</Badge>
        <span style={{ fontSize: 12, color: color.textMuted }}>
          {ORIGIN_LABELS[finding.origin]} · {STATUS_LABELS[finding.status]}
          {finding.edited_by && finding.status !== "draft" ? ` by ${finding.edited_by}` : ""}
        </span>
      </div>
      {editing ? (
        <div style={{ display: "grid", gap: space.sm, marginTop: space.sm }}>
          <label style={{ display: "grid", gap: 4, fontSize: 13 }}>
            Finding
            <textarea value={text} onChange={(e) => setText(e.target.value)} rows={3} maxLength={4000} style={{ ...inputCss(), resize: "vertical" }} />
          </label>
          <div style={{ display: "flex", gap: space.sm }}>
            <Button disabled={busy || !text.trim()} onClick={() => act({ statement: text, status: "accepted" })}>
              Save and accept
            </Button>
            <Button variant="secondary" disabled={busy} onClick={() => { setText(finding.statement); setEditing(false); }}>
              Cancel
            </Button>
          </div>
        </div>
      ) : (
        <p style={{ margin: `${space.sm}px 0 0`, fontSize: 15, textDecoration: rejected ? "line-through" : "none" }}>{finding.statement}</p>
      )}
      {finding.status === "edited" && finding.original_text ? (
        <details style={{ marginTop: 4, fontSize: 12, color: color.textMuted }}>
          <summary style={{ cursor: "pointer" }}>Original draft</summary>
          {finding.original_text}
        </details>
      ) : null}
      {finding.clauses.length ? (
        <div style={{ marginTop: space.xs, display: "flex", gap: space.xs, flexWrap: "wrap" }}>
          {finding.clauses.map((c) => (
            <span key={c.clause_id} title={c.text} style={{ fontSize: 12, padding: "2px 8px", borderRadius: radius.pill, border: `1px solid ${color.border}` }}>
              {c.label}
              {c.heading ? `: ${c.heading}` : ""}
            </span>
          ))}
        </div>
      ) : null}
      <div style={{ display: "flex", gap: space.md, flexWrap: "wrap", marginTop: space.sm, alignItems: "center" }}>
        {!readOnly && !editing ? (
          <>
            {!isAccepted(finding) ? <Button disabled={busy} onClick={() => act({ status: "accepted" })}>Accept</Button> : null}
            <LinkButton disabled={busy} onClick={() => setEditing(true)}>Edit</LinkButton>
            {!rejected ? (
              <LinkButton danger disabled={busy} onClick={() => act({ status: "rejected" })}>Reject</LinkButton>
            ) : (
              <LinkButton disabled={busy} onClick={() => act({ status: "draft" })}>Restore</LinkButton>
            )}
          </>
        ) : null}
        <LinkButton
          onClick={() => {
            setShowEvidence((s) => !s);
            if (!evidence) onLoadEvidence();
          }}
        >
          {showEvidence ? "Hide evidence" : `Show evidence (${finding.evidence_count})`}
        </LinkButton>
      </div>
      {showEvidence ? (
        <div style={{ marginTop: space.sm }}>
          {finding.evidence_count ? <EvidenceList ids={finding.evidence_ids} evidence={evidence} /> : (
            <span style={{ fontSize: 13, color: color.textMuted }}>No answers linked to this finding.</span>
          )}
        </div>
      ) : null}
      {error ? <Notice tone="error">{error}</Notice> : null}
    </li>
  );
}

export function FindingsList(props) {
  const { findings } = props;
  const order = (f) => [f.status === "rejected" ? 1 : 0, KIND_ORDER.indexOf(f.kind)];
  const sorted = [...findings].sort((a, b) => {
    const [x1, y1] = order(a);
    const [x2, y2] = order(b);
    return x1 - x2 || y1 - y2;
  });
  if (!sorted.length) return <p style={{ margin: 0, color: color.textMuted, fontSize: 13 }}>No findings yet.</p>;
  return (
    <ul style={{ margin: 0, padding: 0, display: "grid", gap: space.sm }}>
      {sorted.map((f) => (
        <FindingCard key={f.finding_id} {...props} finding={f} />
      ))}
    </ul>
  );
}

export function AddFinding({ ui, evalId, runId, subjectId, themes, onAdded }) {
  const { Button } = ui;
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ kind: "observation", support: "moderate", statement: "", theme_code: "" });
  const { busy, error, run } = useAsync();
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));
  if (!open) return <Button variant="secondary" onClick={() => setOpen(true)}>Add a finding</Button>;
  return (
    <Panel style={{ display: "grid", gap: space.sm }}>
      <div style={{ display: "grid", gap: space.sm, gridTemplateColumns: "repeat(auto-fit, minmax(170px, 1fr))" }}>
        <label style={{ display: "grid", gap: 4, fontSize: 13 }}>
          Kind
          <select value={form.kind} onChange={set("kind")} style={inputCss()}>
            {Object.entries(KIND_LABELS).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
          </select>
        </label>
        <label style={{ display: "grid", gap: 4, fontSize: 13 }}>
          Support
          <select value={form.support} onChange={set("support")} style={inputCss()}>
            {Object.entries(SUPPORT_LABELS).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
          </select>
        </label>
        {themes && themes.length ? (
          <label style={{ display: "grid", gap: 4, fontSize: 13 }}>
            Theme
            <select value={form.theme_code} onChange={set("theme_code")} style={inputCss()}>
              <option value="">None</option>
              {themes.map((t) => <option key={t.code} value={t.code}>{t.label}</option>)}
            </select>
          </label>
        ) : null}
      </div>
      <label style={{ display: "grid", gap: 4, fontSize: 13 }}>
        Finding
        <textarea value={form.statement} onChange={set("statement")} rows={3} maxLength={4000} style={{ ...inputCss(), resize: "vertical" }} />
      </label>
      <div style={{ display: "flex", gap: space.sm }}>
        <Button
          disabled={busy || !form.statement.trim()}
          onClick={() =>
            run(async () => {
              await analysisApi.addFinding(evalId, runId, { ...form, theme_code: form.theme_code || null, subject_id: subjectId });
              setForm({ kind: "observation", support: "moderate", statement: "", theme_code: "" });
              setOpen(false);
              await onAdded();
            })
          }
        >
          Add finding
        </Button>
        <Button variant="secondary" disabled={busy} onClick={() => setOpen(false)}>
          Cancel
        </Button>
      </div>
      {error ? <Notice tone="error">{error}</Notice> : null}
    </Panel>
  );
}

export function ConclusionEditor({ ui, evalId, runId, subjectId, conclusion, onChanged, readOnly, allowNoFindings, title }) {
  const { Button, Badge } = ui;
  const [text, setText] = useState(conclusion?.text || "");
  const [none, setNone] = useState(!!conclusion?.no_findings);
  const { busy, error, run } = useAsync();
  const save = (status) =>
    run(async () => {
      await analysisApi.setConclusion(evalId, runId, { subject_id: subjectId, text, no_findings: allowNoFindings ? none : undefined, status });
      await onChanged();
    });
  const accepted = conclusion && (conclusion.status === "accepted" || conclusion.status === "edited");
  return (
    <Panel style={{ display: "grid", gap: space.sm }}>
      <div style={{ display: "flex", gap: space.sm, alignItems: "center", flexWrap: "wrap" }}>
        <strong>{title || "Conclusion"}</strong>
        {conclusion ? <Badge tone={accepted ? "green" : "gray"}>{STATUS_LABELS[conclusion.status]}</Badge> : null}
        {conclusion?.origin === "ai" ? <span style={{ fontSize: 12, color: color.textMuted }}>{ORIGIN_LABELS.ai}</span> : null}
      </div>
      {readOnly ? (
        <p style={{ margin: 0, whiteSpace: "pre-wrap" }}>{conclusion?.text || "None written."}</p>
      ) : (
        <>
          <textarea value={text} onChange={(e) => setText(e.target.value)} rows={4} maxLength={8000} aria-label={title || "Conclusion"} style={{ ...inputCss(), resize: "vertical" }} />
          {allowNoFindings ? (
            <label style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 13 }}>
              <input type="checkbox" checked={none} onChange={(e) => setNone(e.target.checked)} />
              Nothing to report for this subject
            </label>
          ) : null}
          <div style={{ display: "flex", gap: space.sm, flexWrap: "wrap" }}>
            <Button disabled={busy || (!text.trim() && !none)} onClick={() => save("accepted")}>
              Save and accept
            </Button>
            <Button variant="secondary" disabled={busy} onClick={() => save("draft")}>
              Save as draft
            </Button>
          </div>
        </>
      )}
      {error ? <Notice tone="error">{error}</Notice> : null}
    </Panel>
  );
}
