import React, { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { SECTOR_OPTIONS, orgApi, sectorFromOption, sectorLabel } from "../../../api/orgApi.js";
import { color, font, space } from "../../../theme.js";
import { Notice, Panel } from "./shared.jsx";
import { formatDate, inputCss, useAsync } from "./helpers.js";

function ProfileBadge({ ui, status }) {
  const { Badge } = ui;
  return status === "reviewed" ? <Badge tone="green">Reviewed</Badge> : <Badge tone="amber">Draft</Badge>;
}

export default function CompaniesListPage({ ui }) {
  const { Card, Button, Field } = ui;
  const navigate = useNavigate();
  const { busy, error, run } = useAsync();
  const [items, setItems] = useState(null);
  const [adding, setAdding] = useState(false);
  const [name, setName] = useState("");
  const [sector, setSector] = useState("");

  const load = useCallback(() => run(async () => setItems((await orgApi.list()).items)), [run]);
  useEffect(() => {
    load();
  }, [load]);

  const create = () =>
    run(async () => {
      const org = await orgApi.create({ name: name.trim(), ...sectorFromOption(sector) });
      navigate(`/consultant/companies/${org.organisation_id}/documents`);
    });

  return (
    <Card
      title="Companies"
      subtitle="Each client company is set up once: its documents, profile and governance codes are reused by every year's evaluation."
      right={
        !adding ? (
          <Button onClick={() => setAdding(true)} disabled={busy}>
            Add company
          </Button>
        ) : null
      }
    >
      {error ? (
        <div style={{ marginBottom: space.md }}>
          <Notice tone="error">{error}</Notice>
        </div>
      ) : null}

      {adding ? (
        <Panel style={{ marginBottom: space.lg }}>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              if (name.trim()) create();
            }}
            style={{ display: "grid", gap: space.md, gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", alignItems: "end" }}
          >
            <Field label="Company name">
              <input value={name} onChange={(e) => setName(e.target.value)} style={inputCss()} maxLength={255} autoFocus autoComplete="off" />
            </Field>
            <Field label="Sector" hint="Sets the default governance codes. You can change it later.">
              <select value={sector} onChange={(e) => setSector(e.target.value)} style={inputCss()}>
                <option value="">Not sure yet</option>
                {SECTOR_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
            </Field>
            <div style={{ display: "flex", gap: space.sm, flexWrap: "wrap" }}>
              <Button onClick={create} disabled={busy || !name.trim()}>
                {busy ? "Adding…" : "Add company"}
              </Button>
              <Button variant="secondary" onClick={() => setAdding(false)} disabled={busy}>
                Cancel
              </Button>
            </div>
          </form>
        </Panel>
      ) : null}

      {items === null ? (
        <p style={{ color: color.textMuted }}>Loading…</p>
      ) : items.length === 0 ? (
        <Panel>
          <p style={{ margin: 0, color: color.textMuted }}>No companies yet. Add the first one to get started.</p>
        </Panel>
      ) : (
        <div style={ui.tableWrapStyle()}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: font.body }}>
            <thead>
              <tr style={{ background: color.surfaceMuted, textAlign: "left" }}>
                {["Company", "Sector", "Profile", "Latest evaluation"].map((h) => (
                  <th key={h} style={{ ...ui.tdStyle(), fontWeight: font.weight.heavy }}>
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {items.map((o) => (
                <tr key={o.organisation_id} style={{ borderTop: `1px solid ${color.border}` }}>
                  <td style={ui.tdStyle()}>
                    <a
                      href={`/consultant/companies/${o.organisation_id}/documents`}
                      onClick={(e) => {
                        e.preventDefault();
                        navigate(`/consultant/companies/${o.organisation_id}/documents`);
                      }}
                      style={{ fontWeight: font.weight.bold, color: color.primaryText }}
                    >
                      {o.name}
                    </a>
                  </td>
                  <td style={ui.tdStyle()}>{sectorLabel(o.sector_key, o.sector_sub_type)}</td>
                  <td style={ui.tdStyle()}>
                    <ProfileBadge ui={ui} status={o.profile_status} />
                  </td>
                  <td style={ui.tdStyle()}>
                    {o.latest_evaluation ? (
                      <span>
                        {o.latest_evaluation.name || o.latest_evaluation.evaluation_id}
                        <span style={{ color: color.textMuted }}> · {formatDate(o.latest_evaluation.created_at)}</span>
                      </span>
                    ) : (
                      <span style={{ color: color.textMuted }}>None yet</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}
