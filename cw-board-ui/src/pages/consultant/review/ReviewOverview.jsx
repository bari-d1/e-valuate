import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { questionBankApi } from "../../../api/questionBankApi.js";
import { color, font, space } from "../../../theme.js";
import { Notice, Panel } from "../companies/shared.jsx";
import { inputCss, useAsync } from "../companies/helpers.js";
import AssemblyPanel from "../questionBank/AssemblyPanel.jsx";
import { SET_STATUS, plural } from "./reviewHelpers.js";

/** Every participant's set at a glance: status, size, time, open decisions and blockers; bulk approval. */
export default function ReviewOverview({ ui, evalId }) {
  const { Badge, Button } = ui;
  const [data, setData] = useState(null);
  const [picked, setPicked] = useState([]);
  const [override, setOverride] = useState("");
  const [results, setResults] = useState(null);
  const { busy, error, run } = useAsync();

  const load = useCallback(() => run(async () => setData(await questionBankApi.review(evalId))), [evalId, run]);
  useEffect(() => {
    load();
  }, [load]);

  const rows = useMemo(() => data?.participants || [], [data]);
  const drafts = rows.filter((r) => r.status === "draft");
  const chosen = rows.filter((r) => picked.includes(r.participant_id));
  const chosenBlocked = chosen.filter((r) => r.blockers.length);
  const needsOverride = chosenBlocked.length > 0;
  const toggle = (id) => setPicked((p) => (p.includes(id) ? p.filter((x) => x !== id) : [...p, id]));
  const allPicked = drafts.length > 0 && drafts.every((r) => picked.includes(r.participant_id));

  const approve = () =>
    run(async () => {
      const r = await questionBankApi.bulkApprove(evalId, picked, needsOverride ? override : null);
      setResults(r.results);
      setPicked([]);
      setOverride("");
      setData(await questionBankApi.review(evalId));
    });

  const th = { ...ui.tdStyle(), fontWeight: font.weight.heavy, whiteSpace: "nowrap" };
  const num = { ...ui.tdStyle(), textAlign: "right", fontVariantNumeric: "tabular-nums" };

  return (
    <div style={{ display: "grid", gap: space.lg, gridTemplateColumns: "minmax(0, 1fr)" }}>
      <AssemblyPanel ui={ui} evalId={evalId} onOptionsChanged={load} onRunFinished={load} showRaterWarnings={false} />

      {error ? <Notice tone="error">{error}</Notice> : null}

      {data === null ? (
        <p style={{ color: color.textMuted }}>Loading…</p>
      ) : (
        <section aria-label="Participants' sets">
          {data.rater_warnings.length ? (
            <div style={{ display: "grid", gap: space.sm, marginBottom: space.md }}>
              {data.rater_warnings.map((w) => (
                <Notice key={`${w.set}-${w.subject_id}`} tone="warn">
                  {w.message} Raters: {w.raters.join(", ")}.
                </Notice>
              ))}
            </div>
          ) : null}

          <div style={ui.tableWrapStyle()}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: font.body, minWidth: 760 }}>
              <thead>
                <tr style={{ background: color.surfaceMuted, textAlign: "left" }}>
                  <th style={th} scope="col">
                    <input
                      type="checkbox"
                      aria-label="Select every draft set"
                      checked={allPicked}
                      disabled={!drafts.length}
                      onChange={() => setPicked(allPicked ? [] : drafts.map((r) => r.participant_id))}
                    />
                  </th>
                  {["Participant", "Status", "Questions", "Minutes", "Open AI decisions", "Coverage gaps", "Needs attention"].map((h) => (
                    <th key={h} style={th} scope="col">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => {
                  const st = SET_STATUS[r.status] || SET_STATUS.draft;
                  return (
                    <tr key={r.participant_id} style={{ borderTop: `1px solid ${color.border}` }}>
                      <td style={ui.tdStyle()}>
                        <input
                          type="checkbox"
                          aria-label={`Select ${r.label}`}
                          checked={picked.includes(r.participant_id)}
                          disabled={r.status !== "draft"}
                          onChange={() => toggle(r.participant_id)}
                        />
                      </td>
                      <td style={ui.tdStyle()}>
                        {r.status === "not_assembled" ? (
                          <span style={{ fontWeight: font.weight.bold }}>{r.label}</span>
                        ) : (
                          <Link to={`/consultant/review/participants/${r.participant_id}`} style={{ fontWeight: font.weight.bold, color: color.primaryText }}>
                            {r.display_code ? `${r.display_code} · ` : ""}
                            {r.label}
                          </Link>
                        )}
                        <div style={{ fontSize: font.small, color: color.textMuted }}>
                          {r.role_label}
                          {r.committees.length ? ` · ${plural(r.committees.length, "committee")}` : ""}
                        </div>
                      </td>
                      <td style={ui.tdStyle()}>
                        <Badge tone={st.tone}>{st.label}</Badge>
                        {r.override_reason ? (
                          <div style={{ fontSize: font.small, color: color.textMuted, marginTop: 2 }} title={r.override_reason}>
                            Approved despite gaps
                          </div>
                        ) : null}
                      </td>
                      <td style={num}>{r.questions ?? "—"}</td>
                      <td style={num}>
                        {r.estimated_minutes == null ? "—" : r.long ? <Badge tone="amber">{`${r.estimated_minutes} · long`}</Badge> : r.estimated_minutes}
                      </td>
                      <td style={num}>{r.open_suggestions || "—"}</td>
                      <td style={num}>{r.coverage_gaps ? <Badge tone="amber">{r.coverage_gaps}</Badge> : "—"}</td>
                      <td style={{ ...ui.tdStyle(), fontSize: 13, maxWidth: 320 }}>
                        {[...r.blockers, ...r.rater_warnings].length ? (
                          <ul style={{ margin: 0, paddingLeft: 16, display: "grid", gap: 2, color: color.text }}>
                            {r.blockers.map((b) => (
                              <li key={b}>{b}</li>
                            ))}
                            {r.rater_warnings.map((w) => (
                              <li key={w} style={{ color: color.textMuted }}>
                                {w}
                              </li>
                            ))}
                          </ul>
                        ) : (
                          <span style={{ color: color.textMuted }}>—</span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <p style={{ margin: `${space.sm}px 0 0`, fontSize: font.small, color: color.textMuted }}>
            Sets over {data.long_set_minutes} minutes are marked long. Only draft sets can be selected for approval.
          </p>

          <Panel style={{ marginTop: space.md }}>
            <div style={{ display: "flex", gap: space.md, flexWrap: "wrap", alignItems: "end" }}>
              <div style={{ flex: "1 1 280px", minWidth: 0, fontSize: 13 }}>
                <strong>{chosen.length ? `${plural(chosen.length, "set")} selected` : "Select draft sets to approve together."}</strong>
                {needsOverride ? (
                  <label style={{ display: "grid", gap: 4, marginTop: space.sm }}>
                    <span>
                      {plural(chosenBlocked.length, "selected set has", "selected sets have")} gaps or open decisions. To approve
                      them anyway, give one reason for the batch:
                    </span>
                    <input value={override} onChange={(e) => setOverride(e.target.value)} style={inputCss()} placeholder="e.g. Scope agreed with the client" />
                  </label>
                ) : null}
              </div>
              <Button disabled={busy || !chosen.length || (needsOverride && !override.trim())} onClick={approve}>
                {busy ? "Approving…" : "Approve selected"}
              </Button>
            </div>
            {results ? (
              <ul style={{ margin: `${space.md}px 0 0`, paddingLeft: 18, fontSize: 13, display: "grid", gap: 4 }} aria-live="polite">
                {results.map((r) => (
                  <li key={r.participant_id}>
                    <strong>{r.label || r.participant_id}</strong>: {r.outcome === "approved" ? "approved" : `not approved. ${r.reason}`}
                  </li>
                ))}
              </ul>
            ) : null}
          </Panel>
        </section>
      )}
    </div>
  );
}
