import React, { useEffect, useState } from "react";
import { questionBankApi } from "../../../api/questionBankApi.js";
import { color, font, radius, space } from "../../../theme.js";
import { Notice, Panel, SectionTitle } from "../companies/shared.jsx";
import { useAsync } from "../companies/helpers.js";
import { ANSWER_TYPE_LABELS } from "./bankHelpers.js";

/** Read-only view of one participant's assembled draft set. Editing and approval come later. */

const SOURCE_LABELS = {
  bank: "Bank wording",
  ai_tailored: "AI wording chosen",
  consultant_edited: "Edited by consultant",
  ai_new: "AI new question",
};

function Wording({ q }) {
  const label = { fontSize: font.small, fontWeight: font.weight.bold, color: color.textMuted, marginBottom: 2 };
  return (
    <div style={{ display: "grid", gap: space.sm, gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))" }}>
      <div>
        <div style={label}>{q.text_source === "ai_new" ? "Suggested question" : "Bank text"}</div>
        <div>{q.text_source === "ai_new" ? q.text : q.bank_text}</div>
      </div>
      {q.ai_text && q.text_source !== "ai_new" ? (
        <div style={{ borderLeft: `3px solid ${color.primarySoftBorder}`, paddingLeft: space.sm }}>
          <div style={label}>AI suggestion</div>
          <div>{q.ai_text}</div>
          {q.ai_reason ? <div style={{ fontSize: 13, color: color.textMuted, marginTop: 2 }}>Why: {q.ai_reason}</div> : null}
        </div>
      ) : null}
      {q.text_source === "ai_new" ? (
        <div style={{ borderLeft: `3px solid ${color.primarySoftBorder}`, paddingLeft: space.sm }}>
          <div style={label}>Why suggested</div>
          <div style={{ fontSize: 13 }}>{q.ai_reason}</div>
          <div style={{ fontSize: 13, color: color.textMuted }}>Responds to: {q.ai_fact_key}</div>
        </div>
      ) : null}
    </div>
  );
}

function QuestionRow({ ui, q, codeById }) {
  const { Badge } = ui;
  return (
    <li style={{ borderTop: `1px solid ${color.border}`, padding: `${space.sm}px 0` }}>
      <div style={{ display: "flex", gap: space.sm, flexWrap: "wrap", alignItems: "center", marginBottom: 4 }}>
        {q.bank_item_code ? <strong style={{ fontVariantNumeric: "tabular-nums" }}>{q.bank_item_code}</strong> : null}
        {q.subject ? <span style={{ fontSize: 13, color: color.textMuted }}>About {q.subject.label}</span> : null}
        <span style={{ fontSize: font.small, color: color.textMuted }}>{ANSWER_TYPE_LABELS[q.answer_type] || q.answer_type}</span>
        {q.text_source !== "bank" ? <Badge tone="purple">{SOURCE_LABELS[q.text_source]}</Badge> : null}
        {q.suggestion_status === "pending" ? <Badge tone="amber">Awaiting decision</Badge> : null}
      </div>
      <Wording q={q} />
      {q.confirm_value ? (
        <div style={{ fontSize: 13, marginTop: 4 }}>
          Stored {q.confirm_value.known_from_label.toLowerCase()}: <strong>{q.confirm_value.value_text}</strong>
        </div>
      ) : null}
      {q.depends_on_question_id ? (
        <div style={{ fontSize: 13, color: color.textMuted, marginTop: 4 }}>
          Follow-up: shown only if the answer to {codeById[q.depends_on_question_id] || "the previous question"} is yes.
        </div>
      ) : null}
    </li>
  );
}

export default function AssembledSet({ ui, evalId, participantId, refreshKey }) {
  const { Badge } = ui;
  const [data, setData] = useState(null);
  const { error, run } = useAsync();

  useEffect(() => {
    run(async () => setData(await questionBankApi.questionSet(evalId, participantId)));
  }, [evalId, participantId, refreshKey, run]);

  if (error) return <Notice tone="error">{error}</Notice>;
  if (!data) return <p style={{ color: color.textMuted }}>Loading…</p>;
  if (!data.set) return <Notice tone="info">No assembled set yet. Use “Assemble drafts” above.</Notice>;

  const s = data.set;
  const summary = s.summary || {};
  const codeById = Object.fromEntries(data.sections.flatMap((sec) => sec.questions.map((q) => [q.id, q.bank_item_code])));
  const gaps = summary.coverage_gaps || [];
  const dropped = summary.ai?.dropped || [];

  return (
    <div style={{ display: "grid", gap: space.md, gridTemplateColumns: "minmax(0, 1fr)" }}>
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
        <Badge tone={{ draft: "amber", approved: "green", locked: "gray" }[s.status]}>
          {s.status[0].toUpperCase() + s.status.slice(1)}
        </Badge>
        <Badge tone="blue">{summary.counts?.questions ?? 0} questions</Badge>
        <Badge tone="blue">~{s.estimated_minutes} min</Badge>
        {summary.counts?.skipped_known ? <Badge tone="gray">{summary.counts.skipped_known} skipped (already known)</Badge> : null}
        {summary.counts?.follow_ups ? <Badge tone="gray">{summary.counts.follow_ups} follow-ups</Badge> : null}
        <Badge tone={summary.ai?.enabled ? "purple" : "gray"}>{summary.ai?.enabled ? `AI: ${summary.ai.tailored} suggestions` : "AI off: bank text"}</Badge>
      </div>

      {gaps.length ? (
        <Notice tone="warn">
          Coverage gaps (approval needs an override reason):
          <ul style={{ margin: "4px 0 0", paddingLeft: 18 }}>
            {gaps.map((g) => (
              <li key={g.subject_key}>{g.message}</li>
            ))}
          </ul>
        </Notice>
      ) : null}

      {data.sections.map((sec) => (
        <details key={sec.key} style={{ border: `1px solid ${color.border}`, borderRadius: radius.md, background: color.surface }}>
          <summary style={{ padding: space.md, cursor: "pointer", fontWeight: font.weight.bold }}>
            {sec.label} <span style={{ fontWeight: font.weight.regular, color: color.textMuted }}>· {sec.questions.length}</span>
          </summary>
          <ul style={{ listStyle: "none", margin: 0, padding: `0 ${space.md}px ${space.sm}px` }}>
            {sec.questions.map((q) => (
              <QuestionRow key={q.id} ui={ui} q={q} codeById={codeById} />
            ))}
          </ul>
        </details>
      ))}

      {summary.skipped_known?.length ? (
        <section>
          <SectionTitle hint="Left out because a confirmed fact already answers them.">Skipped: already known</SectionTitle>
          <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13, display: "grid", gap: 4 }}>
            {summary.skipped_known.map((k, n) => (
              <li key={`${k.code}-${n}`}>
                <strong>{k.code}</strong> about {k.subject}: {k.known_from} is {k.value}
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {dropped.length ? (
        <details>
          <summary style={{ cursor: "pointer", fontWeight: font.weight.bold }}>AI suggestions dropped by the checks ({dropped.length})</summary>
          <Panel style={{ marginTop: space.sm }}>
            <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13, display: "grid", gap: 4 }}>
              {dropped.map((d, n) => (
                <li key={n}>
                  “{d.text}” <span style={{ color: color.danger }}>({d.dropped_because})</span>
                </li>
              ))}
            </ul>
          </Panel>
        </details>
      ) : null}
    </div>
  );
}
