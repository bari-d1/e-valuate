import React, { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { orgApi } from "../../../api/orgApi.js";
import { color, font, space } from "../../../theme.js";
import { Notice, Panel, SectionTitle } from "./shared.jsx";
import { formatDate, useAsync } from "./helpers.js";

const STATUS = {
  draft: { label: "Draft", tone: "gray" },
  in_review: { label: "In review", tone: "blue" },
  live: { label: "Live", tone: "green" },
  closed: { label: "Closed", tone: "purple" },
};

export default function EvaluationsTab({ ui, org }) {
  const { Badge, Button } = ui;
  const navigate = useNavigate();
  const [items, setItems] = useState(null);
  const { error, run } = useAsync();

  const load = useCallback(
    () =>
      run(async () => {
        const all = (await orgApi.evaluations()).items;
        setItems(all.filter((e) => e.organisation_id === org.organisation_id));
      }),
    [org.organisation_id, run]
  );
  useEffect(() => {
    load();
  }, [load]);

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", gap: space.md, flexWrap: "wrap", alignItems: "flex-start" }}>
        <SectionTitle hint="Every evaluation for this company reuses its profile and governance codes.">Evaluations</SectionTitle>
        <Button onClick={() => navigate(`/consultant/evaluations/create?organisation=${encodeURIComponent(org.organisation_id)}`)}>
          New evaluation
        </Button>
      </div>
      {error ? <Notice tone="error">{error}</Notice> : null}
      {items === null ? (
        <p style={{ color: color.textMuted }}>Loading…</p>
      ) : items.length === 0 ? (
        <Panel>
          <p style={{ margin: 0, color: color.textMuted }}>No evaluations for {org.name} yet.</p>
        </Panel>
      ) : (
        <div style={ui.tableWrapStyle()}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: font.body }}>
            <thead>
              <tr style={{ background: color.surfaceMuted, textAlign: "left" }}>
                {["Evaluation", "Status", "Review period", "Deadline"].map((h) => (
                  <th key={h} style={{ ...ui.tdStyle(), fontWeight: font.weight.heavy }}>
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {items.map((e) => {
                const st = STATUS[e.status] || STATUS.draft;
                return (
                  <tr key={e.evaluation_id} style={{ borderTop: `1px solid ${color.border}` }}>
                    <td style={ui.tdStyle()}>
                      <div style={{ fontWeight: font.weight.bold, color: color.text }}>{e.name || `${e.year} evaluation`}</div>
                      <div style={{ fontSize: font.small, color: color.textMuted }}>{e.evaluation_id}</div>
                    </td>
                    <td style={ui.tdStyle()}>
                      <Badge tone={st.tone}>{st.label}</Badge>
                    </td>
                    <td style={ui.tdStyle()}>
                      {e.review_period_start || e.review_period_end
                        ? `${formatDate(e.review_period_start)} – ${formatDate(e.review_period_end)}`
                        : "—"}
                    </td>
                    <td style={ui.tdStyle()}>{formatDate(e.deadline)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
