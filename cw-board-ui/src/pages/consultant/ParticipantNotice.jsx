import React, { useEffect, useState } from "react";
import { evaluationApi } from "../../api/orgApi.js";
import { color, font, space } from "../../theme.js";
import { inputCss, useAsync } from "./companies/helpers.js";
import { Notice, Panel } from "./companies/shared.jsx";

/**
 * The notice participants see at the start of their form and in their invite email.
 * Empty uses neutral default wording. Whether answers are anonymous isn't decided yet,
 * so the hint warns against promising it.
 */
export default function ParticipantNotice({ ui, evalId }) {
  const { Button } = ui;
  const [evaluation, setEvaluation] = useState(null);
  const [text, setText] = useState("");
  const [editing, setEditing] = useState(false);
  const { busy, error, run } = useAsync();

  useEffect(() => {
    if (!evalId) return;
    run(async () => {
      const e = await evaluationApi.get(evalId);
      setEvaluation(e);
      setText(e.participant_notice || "");
    });
  }, [evalId, run]);

  if (!evalId || !evaluation) return null;
  const current = evaluation.participant_notice || evaluation.participant_notice_default;
  const save = () =>
    run(async () => {
      const e = await evaluationApi.update(evalId, { participant_notice: text.trim() || null });
      setEvaluation(e);
      setText(e.participant_notice || "");
      setEditing(false);
    });

  return (
    <Panel style={{ marginTop: space.md }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: space.md, flexWrap: "wrap", alignItems: "baseline" }}>
        <strong style={{ fontSize: font.body }}>Notice to participants</strong>
        {!editing ? (
          <Button variant="secondary" onClick={() => setEditing(true)} disabled={busy}>
            Edit
          </Button>
        ) : null}
      </div>
      <div style={{ marginTop: 2, fontSize: font.small, color: color.textMuted }}>
        Shown at the start of each participant's form and in their invite email.
        {evaluation.participant_notice ? "" : " This is the default wording."}
      </div>
      {editing ? (
        <div style={{ display: "grid", gap: space.sm, marginTop: space.sm }}>
          <label style={{ display: "grid", gap: 4, fontSize: 13 }}>
            Notice (leave empty for the default wording)
            <textarea
              value={text}
              onChange={(e) => setText(e.target.value)}
              rows={3}
              maxLength={2000}
              placeholder={evaluation.participant_notice_default}
              style={{ ...inputCss(), resize: "vertical" }}
            />
          </label>
          <div style={{ fontSize: font.small, color: color.textMuted }}>
            Don't promise anonymity or confidentiality unless the client has agreed it and the reports keep to it.
          </div>
          <div style={{ display: "flex", gap: space.sm, flexWrap: "wrap" }}>
            <Button onClick={save} disabled={busy}>
              {busy ? "Saving…" : "Save notice"}
            </Button>
            <Button
              variant="secondary"
              onClick={() => {
                setText(evaluation.participant_notice || "");
                setEditing(false);
              }}
              disabled={busy}
            >
              Cancel
            </Button>
          </div>
        </div>
      ) : (
        <p style={{ margin: `${space.sm}px 0 0`, whiteSpace: "pre-wrap" }}>{current}</p>
      )}
      {error ? (
        <div style={{ marginTop: space.sm }}>
          <Notice tone="error">{error}</Notice>
        </div>
      ) : null}
    </Panel>
  );
}
