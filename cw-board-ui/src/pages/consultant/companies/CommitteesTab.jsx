import React, { useCallback, useEffect, useState } from "react";
import { SOURCE_LABELS, orgApi } from "../../../api/orgApi.js";
import { color, font, space } from "../../../theme.js";
import { Excerpt, LinkButton, Notice, Panel, SectionTitle } from "./shared.jsx";
import { inputCss, useAsync } from "./helpers.js";

const TYPE_LABELS = {
  audit: "Audit",
  risk: "Risk",
  remuneration: "Remuneration",
  nomination: "Nomination",
  finance: "Finance",
  governance: "Governance",
  other: "Other",
};

function CommitteeForm({ ui, initial, busy, submitLabel, onSubmit, onCancel, showSource = true }) {
  const { Button, Field } = ui;
  const [name, setName] = useState(initial?.name || "");
  const [type, setType] = useState(initial?.committee_type || "other");
  const [chair, setChair] = useState(initial?.chair_name || "");
  const [members, setMembers] = useState((initial?.member_names || []).join("\n"));
  const [source, setSource] = useState(initial?.source || "client");
  return (
    <div style={{ display: "grid", gap: space.sm, marginTop: space.sm }}>
      <div style={{ display: "grid", gap: space.sm, gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))" }}>
        <Field label="Committee name">
          <input value={name} onChange={(e) => setName(e.target.value)} style={inputCss()} />
        </Field>
        <Field label="Type">
          <select value={type} onChange={(e) => setType(e.target.value)} style={inputCss()}>
            {Object.entries(TYPE_LABELS).map(([k, v]) => (
              <option key={k} value={k}>
                {v}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Chair">
          <input value={chair} onChange={(e) => setChair(e.target.value)} style={inputCss()} placeholder="As written in the documents" />
        </Field>
      </div>
      <Field label="Members" hint="One name per line, as written in the documents.">
        <textarea value={members} onChange={(e) => setMembers(e.target.value)} rows={4} style={inputCss({ resize: "vertical" })} />
      </Field>
      {showSource ? (
        <Field label="Where does this come from?">
          <select value={source} onChange={(e) => setSource(e.target.value)} style={inputCss({ maxWidth: 260 })}>
            <option value="client">Client (supplied by the company)</option>
            <option value="public">Public source</option>
            <option value="consultant">Consultant's own judgement</option>
          </select>
        </Field>
      ) : null}
      <div style={{ display: "flex", gap: space.sm, flexWrap: "wrap" }}>
        <Button
          disabled={busy || !name.trim()}
          onClick={() =>
            onSubmit({
              name: name.trim(),
              committee_type: type,
              chair_name: chair.trim() || null,
              member_names: members.split("\n").map((s) => s.trim()).filter(Boolean),
              source,
            })
          }
        >
          {busy ? "Saving…" : submitLabel}
        </Button>
        <Button variant="secondary" onClick={onCancel} disabled={busy}>
          Cancel
        </Button>
      </div>
    </div>
  );
}

function CommitteeCard({ ui, org, c, docNames, onChanged }) {
  const { Badge, Button } = ui;
  const { busy, error, run } = useAsync();
  const [editing, setEditing] = useState(false);
  const id = org.organisation_id;
  const proposed = c.status === "proposed";
  const act = (fn) =>
    run(async () => {
      await fn();
      setEditing(false);
      await onChanged();
    });

  return (
    <Panel highlight={proposed}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: space.sm, flexWrap: "wrap", alignItems: "center" }}>
        <h3 style={{ margin: 0, fontSize: font.body, fontWeight: font.weight.heavy, color: color.text }}>{c.name}</h3>
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
          {proposed ? <Badge tone="amber">Proposed</Badge> : <Badge tone="green">Confirmed</Badge>}
          <Badge tone="gray">{TYPE_LABELS[c.committee_type] || c.committee_type}</Badge>
          <Badge tone={{ public: "blue", client: "purple" }[c.source] || "gray"}>{SOURCE_LABELS[c.source] || c.source}</Badge>
        </div>
      </div>
      <dl style={{ margin: `${space.sm}px 0 0`, display: "grid", gridTemplateColumns: "auto 1fr", gap: "4px 12px", fontSize: 13 }}>
        <dt style={{ color: color.textMuted }}>Chair</dt>
        <dd style={{ margin: 0, color: color.text }}>{c.chair_name || "—"}</dd>
        <dt style={{ color: color.textMuted }}>Members</dt>
        <dd style={{ margin: 0, color: color.text }}>{c.member_names.length ? c.member_names.join(", ") : "—"}</dd>
      </dl>
      {c.source_excerpt ? <Excerpt text={c.source_excerpt} filename={docNames[c.source_document_id]} /> : null}

      {editing ? (
        <CommitteeForm
          ui={ui}
          initial={c}
          busy={busy}
          submitLabel={proposed ? "Confirm with these details" : "Save"}
          onCancel={() => setEditing(false)}
          onSubmit={(data) => act(() => (proposed ? orgApi.confirmCommittee(id, c.committee_id, data) : orgApi.updateCommittee(id, c.committee_id, data)))}
        />
      ) : proposed ? (
        <div style={{ display: "flex", gap: space.sm, flexWrap: "wrap", marginTop: space.sm }}>
          <Button onClick={() => act(() => orgApi.confirmCommittee(id, c.committee_id))} disabled={busy}>
            Confirm
          </Button>
          <Button variant="secondary" onClick={() => setEditing(true)} disabled={busy}>
            Edit
          </Button>
          <Button variant="danger" onClick={() => act(() => orgApi.rejectCommittee(id, c.committee_id))} disabled={busy}>
            Reject
          </Button>
        </div>
      ) : (
        <div style={{ display: "flex", gap: space.md, marginTop: space.sm }}>
          <LinkButton onClick={() => setEditing(true)} disabled={busy}>
            Edit
          </LinkButton>
          <LinkButton danger disabled={busy} onClick={() => window.confirm(`Delete ${c.name}?`) && act(() => orgApi.deleteCommittee(id, c.committee_id))}>
            Delete
          </LinkButton>
        </div>
      )}
      {error ? (
        <div style={{ marginTop: space.sm }}>
          <Notice tone="error">{error}</Notice>
        </div>
      ) : null}
    </Panel>
  );
}

export default function CommitteesTab({ ui, org, reloadOrg }) {
  const { Button } = ui;
  const [items, setItems] = useState(null);
  const [docNames, setDocNames] = useState({});
  const [adding, setAdding] = useState(false);
  const { busy, error, run } = useAsync();
  const id = org.organisation_id;

  const load = useCallback(
    () =>
      run(async () => {
        const [c, d] = await Promise.all([orgApi.committees(id), orgApi.documents(id)]);
        setItems(c.items.filter((x) => x.status !== "rejected"));
        setDocNames(Object.fromEntries(d.items.map((x) => [x.document_id, x.filename])));
      }),
    [id, run]
  );
  useEffect(() => {
    load();
  }, [load]);
  const refresh = async () => {
    await load();
    await reloadOrg();
  };

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", gap: space.md, flexWrap: "wrap", alignItems: "flex-start" }}>
        <SectionTitle hint="Names exactly as written in the company's documents. Linking members to participants comes later.">
          Committees
        </SectionTitle>
        {!adding ? (
          <Button variant="secondary" onClick={() => setAdding(true)}>
            Add committee
          </Button>
        ) : null}
      </div>

      {error ? <Notice tone="error">{error}</Notice> : null}

      {adding ? (
        <Panel style={{ marginBottom: space.md }}>
          <CommitteeForm
            ui={ui}
            busy={busy}
            submitLabel="Add committee"
            onCancel={() => setAdding(false)}
            onSubmit={(data) =>
              run(async () => {
                await orgApi.addCommittee(id, data);
                setAdding(false);
                await refresh();
              })
            }
          />
        </Panel>
      ) : null}

      {items === null ? (
        <p style={{ color: color.textMuted }}>Loading…</p>
      ) : items.length === 0 ? (
        <Panel>
          <p style={{ margin: 0, color: color.textMuted }}>No committees yet.</p>
        </Panel>
      ) : (
        <div style={{ display: "grid", gap: space.md, gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))" }}>
          {items.map((c) => (
            <CommitteeCard key={c.committee_id} ui={ui} org={org} c={c} docNames={docNames} onChanged={refresh} />
          ))}
        </div>
      )}
    </div>
  );
}
