import React, { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { boardApi } from "../../../api/orgApi.js";
import { color, font, space } from "../../../theme.js";
import { Notice, Panel, SectionTitle } from "./shared.jsx";
import { inputCss, useAsync } from "./helpers.js";
import { roleLabel, useMemberRegistry } from "./boardHelpers.js";

function AddMember({ ui, org, onAdded, onCancel }) {
  const { Button, Field } = ui;
  const { busy, error, run } = useAsync();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");

  const save = () =>
    run(async () => {
      const m = await boardApi.create(org.organisation_id, {
        full_name: name.trim(),
        email: email.trim() || null,
        display_code: code.trim() || null,
      });
      onAdded(m);
    });

  return (
    <Panel style={{ marginBottom: space.md }}>
      {error ? (
        <div style={{ marginBottom: space.sm }}>
          <Notice tone="error">{error}</Notice>
        </div>
      ) : null}
      <div style={{ display: "grid", gap: space.md, gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", alignItems: "end" }}>
        <Field label="Full name">
          <input value={name} onChange={(e) => setName(e.target.value)} style={inputCss()} maxLength={255} autoComplete="off" />
        </Field>
        <Field label="Email" hint="Optional. Used when they're invited.">
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} style={inputCss()} maxLength={255} autoComplete="off" />
        </Field>
        <Field label="Display code" hint="Optional, e.g. P001. Shown next to their name.">
          <input value={code} onChange={(e) => setCode(e.target.value)} style={inputCss({ textTransform: "uppercase" })} maxLength={32} />
        </Field>
      </div>
      <div style={{ display: "flex", gap: space.sm, flexWrap: "wrap", marginTop: space.md }}>
        <Button onClick={save} disabled={busy || !name.trim()}>
          {busy ? "Adding…" : "Add board member"}
        </Button>
        <Button variant="secondary" onClick={onCancel} disabled={busy}>
          Cancel
        </Button>
      </div>
    </Panel>
  );
}

// Active members first, then by surname (the last word of the name), so titles like "Dr." don't decide the order
function bySurname(a, b) {
  if (a.active !== b.active) return a.active ? -1 : 1;
  const surname = (m) => (m.full_name || "").trim().split(/\s+/).pop().toLowerCase();
  return surname(a).localeCompare(surname(b)) || (a.full_name || "").localeCompare(b.full_name || "");
}

function Committees({ items }) {
  if (!items.length) return <span style={{ color: color.textMuted }}>—</span>;
  return (
    <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "grid", gap: 2 }}>
      {items.map((c) => (
        <li key={c.membership_id}>
          {c.committee_name}
          {c.membership_role === "chair" ? (
            <span style={{ marginLeft: 6, fontSize: font.small, fontWeight: font.weight.heavy, color: color.primaryText }}>Chair</span>
          ) : null}
        </li>
      ))}
    </ul>
  );
}

export default function BoardTab({ ui, org, refreshKey }) {
  const { Badge, Button } = ui;
  const [items, setItems] = useState(null);
  const [adding, setAdding] = useState(false);
  const { error, run } = useAsync();
  const registry = useMemberRegistry(run);
  const id = org.organisation_id;

  const load = useCallback(() => run(async () => setItems((await boardApi.list(id)).items)), [id, run]);
  useEffect(() => {
    load();
  }, [load, refreshKey]);

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", gap: space.md, flexWrap: "wrap", alignItems: "flex-start" }}>
        <SectionTitle hint="Each director's profile is reviewed once and reused by every evaluation of this company.">Board</SectionTitle>
        {!adding ? <Button onClick={() => setAdding(true)}>Add board member</Button> : null}
      </div>

      {error ? <Notice tone="error">{error}</Notice> : null}

      {adding ? (
        <AddMember
          ui={ui}
          org={org}
          onCancel={() => setAdding(false)}
          onAdded={async () => {
            setAdding(false);
            await load();
          }}
        />
      ) : null}

      {items === null ? (
        <p style={{ color: color.textMuted }}>Loading…</p>
      ) : items.length === 0 ? (
        <Panel>
          <p style={{ margin: 0, color: color.textMuted }}>No board members yet. Add them here, or they're created from an evaluation's participants.</p>
        </Panel>
      ) : (
        <div style={ui.tableWrapStyle()}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: font.body, minWidth: 640 }}>
            <thead>
              <tr style={{ background: color.surfaceMuted, textAlign: "left" }}>
                {["Board member", "Role", "Committees", "Profile"].map((h) => (
                  <th key={h} scope="col" style={{ ...ui.tdStyle(), fontWeight: font.weight.heavy }}>
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {[...items].sort(bySurname).map((m) => (
                <tr key={m.board_member_id} style={{ borderTop: `1px solid ${color.border}`, opacity: m.active ? 1 : 0.6 }}>
                  <td style={ui.tdStyle()}>
                    <Link to={`/consultant/companies/${id}/board/${m.board_member_id}`} style={{ fontWeight: font.weight.bold, color: color.primaryText }}>
                      {m.display_code ? <span style={{ fontVariantNumeric: "tabular-nums" }}>{m.display_code} · </span> : null}
                      {m.full_name}
                    </Link>
                    <div style={{ fontSize: font.small, color: color.textMuted, overflowWrap: "break-word" }}>{m.email || "No email"}</div>
                    {m.problems.length ? (
                      <ul aria-label="To check" style={{ listStyle: "none", margin: "4px 0 0", padding: 0, display: "flex", flexWrap: "wrap", gap: 4 }}>
                        {m.problems.map((p) => (
                          <li key={p}>
                            <Badge tone="amber">{p}</Badge>
                          </li>
                        ))}
                      </ul>
                    ) : null}
                  </td>
                  <td style={ui.tdStyle()}>
                    {m.governance_role ? roleLabel(registry, m.governance_role) : <span style={{ color: color.textMuted }}>Not confirmed</span>}
                  </td>
                  <td style={ui.tdStyle()}>
                    <Committees items={m.committees} />
                  </td>
                  <td style={ui.tdStyle()}>
                    <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                      {m.profile_status === "reviewed" ? <Badge tone="green">Reviewed v{m.profile_version}</Badge> : <Badge tone="gray">Draft</Badge>}
                      {!m.active ? <Badge tone="gray">Inactive</Badge> : null}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
