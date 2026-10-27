import React, { useCallback, useEffect, useState } from "react";
import { questionBankApi } from "../../../api/questionBankApi.js";
import { color, font, space } from "../../../theme.js";
import { Notice, Panel, SectionTitle } from "../companies/shared.jsx";
import { inputCss, useAsync } from "../companies/helpers.js";
import { formatDateTime } from "../../../utils/format.js";

const RUN_TONE = { queued: "gray", running: "blue", done: "green", failed: "red" };

/** Peer mode, the "Assemble drafts" action, run status and evaluation-wide rater warnings. */
export default function AssemblyPanel({ ui, evalId, onOptionsChanged, onRunFinished, showRaterWarnings = true }) {
  const { Badge, Button, Field } = ui;
  const [options, setOptions] = useState(null);
  const [available, setAvailable] = useState([]);
  const [latest, setLatest] = useState(null);
  const { busy, error, run } = useAsync();

  const loadRuns = useCallback(async () => {
    const r = await questionBankApi.runs(evalId);
    setLatest(r.items[0] || null);
    return r.items[0] || null;
  }, [evalId]);

  useEffect(() => {
    run(async () => {
      const o = await questionBankApi.options(evalId);
      setOptions(o.options);
      setAvailable(o.available);
      await loadRuns();
    });
  }, [evalId, loadRuns, run]);

  // Poll while a run is queued or running
  const pending = latest && (latest.status === "queued" || latest.status === "running");
  useEffect(() => {
    if (!pending) return undefined;
    const t = setTimeout(async () => {
      try {
        const r = await loadRuns();
        if (r && r.status !== "queued" && r.status !== "running") onRunFinished();
      } catch {
        /* the next poll retries */
      }
    }, 2000);
    return () => clearTimeout(t);
  }, [pending, latest, loadRuns, onRunFinished]);

  const peer = available.find((o) => o.key === "peer_mode");
  const assembled = (latest?.results || []).filter((r) => r.outcome === "assembled");
  const skipped = (latest?.results || []).filter((r) => r.outcome === "skipped");

  return (
    <section>
      <SectionTitle hint="Builds one draft question set per ready participant from approved bank items. Nothing is sent to participants.">
        Assembled drafts
      </SectionTitle>
      <Panel>
        <div style={{ display: "grid", gap: space.md }}>
          <div style={{ display: "flex", gap: space.md, flexWrap: "wrap", alignItems: "end" }}>
            {peer && options ? (
              <div style={{ flex: "1 1 260px", minWidth: 0 }}>
                <Field label={peer.label}>
                  <select
                    value={options.peer_mode}
                    disabled={busy}
                    onChange={(e) =>
                      run(async () => {
                        const o = await questionBankApi.setOptions(evalId, { peer_mode: e.target.value });
                        setOptions(o.options);
                        onOptionsChanged();
                      })
                    }
                    style={inputCss()}
                  >
                    {peer.values.map((v) => (
                      <option key={v.key} value={v.key}>
                        {v.label}
                      </option>
                    ))}
                  </select>
                </Field>
              </div>
            ) : null}
            <Button
              disabled={busy || pending}
              onClick={() =>
                run(async () => {
                  setLatest(await questionBankApi.assemble(evalId));
                })
              }
            >
              {pending ? "Assembling…" : "Assemble drafts"}
            </Button>
          </div>

          {error ? <Notice tone="error">{error}</Notice> : null}

          {latest ? (
            <div style={{ fontSize: 13, display: "grid", gap: space.sm }}>
              <div style={{ display: "flex", gap: space.sm, flexWrap: "wrap", alignItems: "center" }}>
                <Badge tone={RUN_TONE[latest.status]}>{latest.status[0].toUpperCase() + latest.status.slice(1)}</Badge>
                <span style={{ color: color.textMuted }}>
                  Started {formatDateTime(latest.created_at)}
                  {latest.requested_by ? ` by ${latest.requested_by}` : ""} · AI {latest.ai_enabled ? "on" : "off"}
                </span>
              </div>
              {latest.error ? <Notice tone="error">{latest.error}</Notice> : null}
              {latest.status === "done" ? (
                <div>
                  <strong>{assembled.length}</strong> set{assembled.length === 1 ? "" : "s"} assembled
                  {skipped.length ? (
                    <>
                      , <strong>{skipped.length}</strong> skipped:
                      <ul style={{ margin: "4px 0 0", paddingLeft: 18 }}>
                        {skipped.map((r) => (
                          <li key={r.participant_id}>
                            {r.label}: {r.reasons.join(" ")}
                          </li>
                        ))}
                      </ul>
                    </>
                  ) : null}
                </div>
              ) : null}
              {(showRaterWarnings ? latest.rater_warnings || [] : []).map((w) => (
                <Notice key={`${w.set}-${w.subject_key}`} tone="warn">
                  {w.message} Raters: {w.raters.join(", ")}.
                </Notice>
              ))}
            </div>
          ) : (
            <p style={{ margin: 0, fontSize: 13, color: color.textMuted }}>Not assembled yet.</p>
          )}
          <p style={{ margin: 0, fontSize: font.small, color: color.textMuted }}>
            Re-running replaces draft sets but keeps consultant edits. Approved and locked sets never change.
          </p>
        </div>
      </Panel>
    </section>
  );
}
