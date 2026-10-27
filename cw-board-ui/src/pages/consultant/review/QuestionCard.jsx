import React, { forwardRef, useState } from "react";
import { color, font, radius, space } from "../../../theme.js";
import { LinkButton } from "../companies/shared.jsx";
import { inputCss } from "../companies/helpers.js";
import { ANSWER_TYPE_LABELS, nameOf } from "../questionBank/bankHelpers.js";
import { SOURCE_LABELS, hasOpenWording, isPendingNew, origin } from "./reviewHelpers.js";

const small = { fontSize: font.small, color: color.textMuted };
const labelCss = { fontSize: font.small, fontWeight: font.weight.bold, color: color.textMuted, marginBottom: 2 };

function Tag({ children, tone = "gray" }) {
  const t = { gray: [color.surfaceMuted, color.text], blue: [color.primarySoft, color.primaryText] }[tone];
  return (
    <span style={{ fontSize: font.small, padding: "1px 8px", borderRadius: radius.pill, border: `1px solid ${color.border}`, background: t[0], color: t[1] }}>
      {children}
    </span>
  );
}

/** Bank wording and the AI's suggestion side by side, with the choice. */
function Suggestion({ ui, q, editable, onAct, aiOn }) {
  const { Button } = ui;
  const [note, setNote] = useState("");
  const [asking, setAsking] = useState(false);
  return (
    <div style={{ display: "grid", gap: space.sm, marginTop: space.sm }}>
      <div style={{ display: "grid", gap: space.sm, gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))" }}>
        <div style={{ padding: space.sm, border: `1px solid ${color.border}`, borderRadius: radius.sm, background: q.text_source === "bank" ? color.surface : color.surfaceMuted }}>
          <div style={labelCss}>Bank wording{q.text_source === "bank" ? " (in use)" : ""}</div>
          <div>{q.bank_text}</div>
        </div>
        <div style={{ padding: space.sm, border: `1px solid ${color.primarySoftBorder}`, borderRadius: radius.sm, background: color.primarySoft }}>
          <div style={labelCss}>Suggested wording{q.text_source === "ai_tailored" ? " (in use)" : ""}</div>
          <div>{q.ai_text}</div>
          {q.ai_reason ? <div style={{ ...small, marginTop: 4 }}>Why: {q.ai_reason}</div> : null}
        </div>
      </div>
      {editable ? (
        <div style={{ display: "flex", gap: space.sm, flexWrap: "wrap", alignItems: "center" }}>
          <Button variant="secondary" disabled={q.text_source === "bank" && !!q.suggestion_status} onClick={() => onAct("wording", { use: "bank" })}>
            {q.text_source === "bank" && !q.suggestion_status ? "Keep bank wording" : "Use bank"}
          </Button>
          <Button variant="secondary" disabled={q.text_source === "ai_tailored"} onClick={() => onAct("wording", { use: "ai" })}>
            Use suggestion
          </Button>
          {aiOn ? (
            asking ? (
              <>
                <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="Optional note, e.g. make it less leading" style={inputCss({ flex: "1 1 200px", width: "auto" })} />
                <Button variant="secondary" onClick={() => onAct("regenerate", { note }).then(() => setAsking(false))}>
                  Regenerate
                </Button>
              </>
            ) : (
              <LinkButton onClick={() => setAsking(true)}>Ask for another suggestion</LinkButton>
            )
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

function TagEditor({ ui, q, meta, subjects, onAct, onDone }) {
  const { Button } = ui;
  const [subjectId, setSubjectId] = useState(q.subject?.id || "");
  const [theme, setTheme] = useState(q.theme_code || "");
  const [evidence, setEvidence] = useState(q.evidence_source_code || "");
  const id = `tags-${q.id}`;
  return (
    <div style={{ display: "grid", gap: space.sm, gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", alignItems: "end", marginTop: space.sm }}>
      <label style={{ display: "grid", gap: 4, fontSize: 13 }} htmlFor={`${id}-s`}>
        About
        <select id={`${id}-s`} value={subjectId} onChange={(e) => setSubjectId(e.target.value)} style={inputCss()}>
          {subjects.map((s) => (
            <option key={s.id} value={s.id}>
              {s.label}
            </option>
          ))}
        </select>
      </label>
      <label style={{ display: "grid", gap: 4, fontSize: 13 }} htmlFor={`${id}-t`}>
        Theme
        <select id={`${id}-t`} value={theme} onChange={(e) => setTheme(e.target.value)} style={inputCss()}>
          {(meta?.themes || []).map((t) => (
            <option key={t.code} value={t.code}>
              {t.name}
            </option>
          ))}
        </select>
      </label>
      <label style={{ display: "grid", gap: 4, fontSize: 13 }} htmlFor={`${id}-e`}>
        Evidence source
        <select id={`${id}-e`} value={evidence} onChange={(e) => setEvidence(e.target.value)} style={inputCss()}>
          {(meta?.evidence_sources || []).map((t) => (
            <option key={t.code} value={t.code}>
              {t.name}
            </option>
          ))}
        </select>
      </label>
      <div style={{ display: "flex", gap: space.sm }}>
        <Button onClick={() => onAct("tags", { subject_id: subjectId, theme_code: theme, evidence_source_code: evidence }).then(onDone)}>Save tags</Button>
        <Button variant="secondary" onClick={onDone}>
          Cancel
        </Button>
      </div>
    </div>
  );
}

/**
 * One question in a participant's set: final text, subject and tags, why it's included, where it came from,
 * the AI suggestion if any, and the actions (edit, tags, remove or restore, move).
 */
const QuestionCard = forwardRef(function QuestionCard(
  { ui, q, meta, subjects, editable, aiOn, focused, onFocus, onAct, first, last, followsCode },
  ref
) {
  const { Badge, Button } = ui;
  const [mode, setMode] = useState(null); // "edit" | "tags" | "remove"
  const [text, setText] = useState(q.text);
  const [reason, setReason] = useState("");
  const removed = q.status === "removed";
  const pendingNew = isPendingNew(q);
  const rejectedNew = q.text_source === "ai_new" && q.suggestion_status === "rejected";

  return (
    <li
      ref={ref}
      tabIndex={0}
      onFocus={onFocus}
      style={{
        listStyle: "none",
        padding: space.md,
        borderRadius: radius.md,
        border: `1px solid ${focused ? color.focus : pendingNew || hasOpenWording(q) ? color.primarySoftBorder : color.border}`,
        boxShadow: focused ? `0 0 0 2px ${color.primarySoft}` : "none",
        background: removed || rejectedNew ? color.surfaceMuted : color.surface,
        opacity: removed || rejectedNew ? 0.75 : 1,
      }}
    >
      <div style={{ display: "flex", gap: space.sm, alignItems: "flex-start", justifyContent: "space-between", flexWrap: "wrap" }}>
        <div style={{ flex: "1 1 320px", minWidth: 0 }}>
          {mode === "edit" ? (
            <div style={{ display: "grid", gap: space.sm }}>
              <label htmlFor={`text-${q.id}`} style={labelCss}>
                Question text
              </label>
              <textarea id={`text-${q.id}`} value={text} onChange={(e) => setText(e.target.value)} rows={3} style={{ ...inputCss(), resize: "vertical" }} />
              <div style={{ display: "flex", gap: space.sm }}>
                <Button disabled={!text.trim() || text.trim() === q.text} onClick={() => onAct("wording", { use: "edited", text }).then(() => setMode(null))}>
                  Save wording
                </Button>
                <Button variant="secondary" onClick={() => setMode(null)}>
                  Cancel
                </Button>
              </div>
            </div>
          ) : (
            <div style={{ fontSize: 15, color: color.text, textDecoration: removed ? "line-through" : "none" }}>{q.text}</div>
          )}
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: 6, alignItems: "center" }}>
            {q.subject ? <Tag tone="blue">About: {q.subject.label}</Tag> : <Badge tone="red">No subject</Badge>}
            <Tag>{nameOf(meta?.themes, q.theme_code)}</Tag>
            <Tag>{nameOf(meta?.evidence_sources, q.evidence_source_code)}</Tag>
            <Tag>{ANSWER_TYPE_LABELS[q.answer_type] || q.answer_type}</Tag>
            <span style={small}>{origin(q)}</span>
            {q.text_source !== "bank" && q.text_source !== "ai_new" ? <Badge tone="purple">{SOURCE_LABELS[q.text_source]}</Badge> : null}
            {removed ? <Badge tone="gray">{`Removed${q.removed_reason ? `: ${q.removed_reason}` : ""}`}</Badge> : null}
            {rejectedNew ? <Badge tone="gray">Rejected</Badge> : null}
          </div>
          {q.confirm_value ? (
            <div style={{ fontSize: 13, marginTop: 4 }}>
              Stored {q.confirm_value.known_from_label.toLowerCase()}: <strong>{q.confirm_value.value_text}</strong>
            </div>
          ) : null}
          {followsCode ? <div style={{ ...small, marginTop: 4 }}>Follow-up: shown only if the answer to {followsCode} is yes.</div> : null}
          {q.selection_reason ? (
            <details style={{ marginTop: 4 }}>
              <summary style={{ ...small, cursor: "pointer" }}>Why included</summary>
              <div style={{ fontSize: 13, marginTop: 2 }}>{q.selection_reason.replace(/^Included: /, "")}</div>
            </details>
          ) : null}
        </div>
        {editable && mode === null ? (
          <div style={{ display: "flex", gap: 4, flexWrap: "wrap", alignItems: "center" }}>
            {removed ? (
              <LinkButton onClick={() => onAct("restore")}>Restore</LinkButton>
            ) : (
              <>
                <LinkButton onClick={() => { setText(q.text); setMode("edit"); }}>Edit</LinkButton>
                <LinkButton onClick={() => setMode("tags")}>Tags</LinkButton>
                <LinkButton danger onClick={() => setMode("remove")}>Remove</LinkButton>
              </>
            )}
            <span aria-hidden style={{ color: color.border }}>|</span>
            <LinkButton disabled={first} title="Move up within the section" onClick={() => onAct("move", { direction: "up" })}>
              ↑<span style={{ position: "absolute", width: 1, height: 1, overflow: "hidden", clip: "rect(0 0 0 0)" }}> Move up</span>
            </LinkButton>
            <LinkButton disabled={last} title="Move down within the section" onClick={() => onAct("move", { direction: "down" })}>
              ↓<span style={{ position: "absolute", width: 1, height: 1, overflow: "hidden", clip: "rect(0 0 0 0)" }}> Move down</span>
            </LinkButton>
          </div>
        ) : null}
      </div>

      {mode === "tags" ? <TagEditor ui={ui} q={q} meta={meta} subjects={subjects} onAct={onAct} onDone={() => setMode(null)} /> : null}
      {mode === "remove" ? (
        <div style={{ display: "flex", gap: space.sm, flexWrap: "wrap", alignItems: "center", marginTop: space.sm }}>
          <input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Reason (optional)" aria-label="Reason for removing" style={inputCss({ flex: "1 1 220px", width: "auto" })} />
          <Button variant="danger" onClick={() => onAct("remove", { reason }).then(() => setMode(null))}>
            Remove
          </Button>
          <Button variant="secondary" onClick={() => setMode(null)}>
            Cancel
          </Button>
        </div>
      ) : null}

      {/* Read-only sets only show a suggestion that was actually used */}
      {q.ai_text && q.text_source !== "ai_new" && !removed && mode === null && (editable || q.text_source === "ai_tailored") ? (
        <Suggestion ui={ui} q={q} editable={editable} onAct={onAct} aiOn={aiOn} />
      ) : null}

      {q.text_source === "ai_new" ? (
        <div style={{ marginTop: space.sm, padding: space.sm, borderLeft: `3px solid ${color.primarySoftBorder}`, fontSize: 13 }}>
          <div>Why proposed: {q.ai_reason}</div>
          {q.ai_fact_key ? <div style={small}>Responds to the confirmed fact: {q.ai_fact_key.replace(/_/g, " ")}</div> : null}
          {editable && pendingNew ? (
            <div style={{ display: "flex", gap: space.sm, marginTop: space.sm }}>
              <Button onClick={() => onAct("acceptNew")}>Accept</Button>
              <Button variant="danger" onClick={() => onAct("rejectNew")}>
                Reject
              </Button>
            </div>
          ) : null}
        </div>
      ) : null}
    </li>
  );
});

export default QuestionCard;
