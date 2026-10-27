import React, { useCallback, useEffect, useMemo, useState } from "react";
import { orgApi } from "../../../api/orgApi.js";
import { color, font, space } from "../../../theme.js";
import { Excerpt, LinkButton, Notice, Panel, SectionTitle, SourceTag } from "./shared.jsx";
import { formatDate, inputCss, useAsync } from "./helpers.js";

// ----------------------------
// Values
// ----------------------------

function formatValue(spec, value) {
  if (value === null || value === undefined) return "—";
  if (spec.type === "list") return (value || []).join(", ");
  if (spec.type === "object") {
    return spec.fields
      .filter((f) => value[f.key] !== undefined && value[f.key] !== null)
      .map((f) => `${f.label}: ${value[f.key]}`)
      .join(" · ");
  }
  return String(value);
}

function toForm(spec, value) {
  if (spec.type === "list") return (value || []).join("\n");
  if (spec.type === "object") return Object.fromEntries(spec.fields.map((f) => [f.key, value && value[f.key] != null ? String(value[f.key]) : ""]));
  if (value === null || value === undefined) return "";
  return String(value);
}

function fromForm(spec, form) {
  if (spec.type === "list") return form.split("\n").map((s) => s.trim()).filter(Boolean);
  if (spec.type === "number") return form === "" ? null : Number(form);
  if (spec.type === "object") {
    const out = {};
    for (const f of spec.fields) if (form[f.key] !== "") out[f.key] = Number(form[f.key]);
    return out;
  }
  return form;
}

function ValueInput({ spec, form, setForm, idPrefix }) {
  if (spec.type === "text")
    return <textarea id={`${idPrefix}-value`} value={form} onChange={(e) => setForm(e.target.value)} rows={3} style={inputCss({ resize: "vertical" })} />;
  if (spec.type === "number")
    return <input id={`${idPrefix}-value`} type="number" min={0} step={1} inputMode="numeric" value={form} onChange={(e) => setForm(e.target.value)} style={inputCss({ maxWidth: 160 })} />;
  if (spec.type === "list")
    return <textarea id={`${idPrefix}-value`} value={form} onChange={(e) => setForm(e.target.value)} rows={3} placeholder="One per line" style={inputCss({ resize: "vertical" })} />;
  return (
    <div style={{ display: "grid", gap: space.sm, gridTemplateColumns: "repeat(auto-fill, minmax(150px, 1fr))" }}>
      {spec.fields.map((f) => (
        <label key={f.key} style={{ fontSize: font.small, color: color.textMuted }}>
          {f.label}
          <input
            type="number"
            min={0}
            step={1}
            inputMode="numeric"
            value={form[f.key]}
            onChange={(e) => setForm({ ...form, [f.key]: e.target.value })}
            style={inputCss({ marginTop: 2 })}
          />
        </label>
      ))}
    </div>
  );
}

function FactEditor({ ui, spec, initial, initialSource = "consultant", showSource = true, submitLabel, onSubmit, onCancel, busy }) {
  const { Button } = ui;
  const [form, setForm] = useState(() => toForm(spec, initial));
  const [source, setSource] = useState(initialSource);
  const idPrefix = `fact-${spec.key}`;
  return (
    <div style={{ marginTop: space.sm, display: "grid", gap: space.sm }}>
      <div>
        {spec.type !== "object" ? (
          <label htmlFor={`${idPrefix}-value`} style={{ display: "block", fontSize: 13, fontWeight: font.weight.bold, color: color.text, marginBottom: 4 }}>
            {spec.label}
          </label>
        ) : null}
        <ValueInput spec={spec} form={form} setForm={setForm} idPrefix={idPrefix} />
        {spec.help ? <div style={{ marginTop: 2, fontSize: font.small, color: color.textMuted }}>{spec.help}</div> : null}
      </div>
      {showSource ? (
        <label style={{ fontSize: 13, fontWeight: font.weight.bold, color: color.text, maxWidth: 260 }}>
          Where does this come from?
          <select value={source} onChange={(e) => setSource(e.target.value)} style={inputCss({ marginTop: 4 })}>
            <option value="client">Client (supplied by the company)</option>
            <option value="public">Public source</option>
            <option value="consultant">Consultant's own judgement</option>
          </select>
        </label>
      ) : null}
      <div style={{ display: "flex", gap: space.sm, flexWrap: "wrap" }}>
        <Button onClick={() => onSubmit(fromForm(spec, form), source)} disabled={busy}>
          {busy ? "Saving…" : submitLabel}
        </Button>
        <Button variant="secondary" onClick={onCancel} disabled={busy}>
          Cancel
        </Button>
      </div>
    </div>
  );
}

// ----------------------------
// One fact row
// ----------------------------

function FactRow({ ui, org, spec, confirmed, proposal, docNames, onChanged }) {
  const { Badge, Button } = ui;
  const { busy, error, run } = useAsync();
  const [mode, setMode] = useState(null); // "add" | "edit" | "edit-proposal"
  const id = org.organisation_id;

  const act = (fn) =>
    run(async () => {
      await fn();
      setMode(null);
      await onChanged();
    });

  return (
    <div style={{ padding: `${space.md}px 0`, borderTop: `1px solid ${color.border}` }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: space.md, alignItems: "flex-start", flexWrap: "wrap" }}>
        <div style={{ minWidth: 0, flex: "1 1 260px" }}>
          <div style={{ fontWeight: font.weight.heavy, color: color.text }}>{spec.label}</div>
          {confirmed ? (
            <div style={{ marginTop: 4 }}>
              <span style={{ color: color.text, whiteSpace: "pre-wrap" }}>{formatValue(spec, confirmed.value)}</span>{" "}
              <SourceTag ui={ui} source={confirmed.source} />
              {confirmed.source_excerpt ? <Excerpt text={confirmed.source_excerpt} filename={docNames[confirmed.source_document_id]} /> : null}
              {confirmed.note ? <div style={{ marginTop: 4, fontSize: font.small, color: color.textMuted }}>{confirmed.note}</div> : null}
            </div>
          ) : (
            <div style={{ marginTop: 4, color: color.textMuted, fontSize: 13 }}>Not entered</div>
          )}
        </div>
        {mode === null ? (
          <div style={{ display: "flex", gap: space.md, alignItems: "center" }}>
            {confirmed ? (
              <>
                <LinkButton onClick={() => setMode("edit")} disabled={busy}>
                  Edit
                </LinkButton>
                <LinkButton
                  danger
                  disabled={busy}
                  onClick={() => window.confirm(`Delete ${spec.label}?`) && act(() => orgApi.deleteFact(id, confirmed.fact_id))}
                >
                  Delete
                </LinkButton>
              </>
            ) : (
              <LinkButton onClick={() => setMode("add")} disabled={busy}>
                Add
              </LinkButton>
            )}
          </div>
        ) : null}
      </div>

      {mode === "add" ? (
        <FactEditor ui={ui} spec={spec} busy={busy} submitLabel="Save" onCancel={() => setMode(null)}
          onSubmit={(value, source) => act(() => orgApi.addFact(id, { key: spec.key, value, source }))} />
      ) : null}
      {mode === "edit" && confirmed ? (
        <FactEditor ui={ui} spec={spec} busy={busy} submitLabel="Save" initial={confirmed.value} initialSource={confirmed.source}
          onCancel={() => setMode(null)}
          onSubmit={(value, source) => act(() => orgApi.updateFact(id, confirmed.fact_id, { value, source }))} />
      ) : null}

      {proposal ? (
        <Panel highlight style={{ marginTop: space.sm }}>
          <div style={{ display: "flex", gap: space.sm, alignItems: "center", flexWrap: "wrap" }}>
            <Badge tone="amber">Proposed</Badge>
            <span style={{ fontWeight: font.weight.bold, color: color.text, whiteSpace: "pre-wrap" }}>{formatValue(spec, proposal.value)}</span>
            <SourceTag ui={ui} source={proposal.source} />
          </div>
          <Excerpt text={proposal.source_excerpt} filename={docNames[proposal.source_document_id]} />
          {proposal.note ? <div style={{ marginTop: 4, fontSize: font.small, color: color.textMuted }}>{proposal.note}</div> : null}
          {confirmed ? (
            <div style={{ marginTop: 4, fontSize: font.small, color: color.textMuted }}>Confirming replaces the current value.</div>
          ) : null}
          {mode === "edit-proposal" ? (
            <FactEditor ui={ui} spec={spec} busy={busy} submitLabel="Confirm with this value" initial={proposal.value}
              initialSource={proposal.source} onCancel={() => setMode(null)}
              onSubmit={(value, source) => act(() => orgApi.confirmFact(id, proposal.fact_id, { value, source }))} />
          ) : (
            <div style={{ display: "flex", gap: space.sm, flexWrap: "wrap", marginTop: space.sm }}>
              <Button onClick={() => act(() => orgApi.confirmFact(id, proposal.fact_id))} disabled={busy}>
                Confirm
              </Button>
              <Button variant="secondary" onClick={() => setMode("edit-proposal")} disabled={busy}>
                Edit
              </Button>
              <Button variant="danger" onClick={() => act(() => orgApi.rejectFact(id, proposal.fact_id))} disabled={busy}>
                Reject
              </Button>
            </div>
          )}
        </Panel>
      ) : null}

      {error ? (
        <div style={{ marginTop: space.sm }}>
          <Notice tone="error">{error}</Notice>
        </div>
      ) : null}
    </div>
  );
}

// ----------------------------
// Tab
// ----------------------------

export default function ProfileTab({ ui, org, registry, reloadOrg }) {
  const { Button } = ui;
  const [facts, setFacts] = useState(null);
  const [docNames, setDocNames] = useState({});
  const { busy, error, run } = useAsync();
  const id = org.organisation_id;

  const load = useCallback(
    () =>
      run(async () => {
        const [f, d] = await Promise.all([orgApi.facts(id), orgApi.documents(id)]);
        setFacts(f.items);
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

  const openFacts = (facts || []).filter((f) => f.status === "proposed").length;
  const openCommittees = org.open_proposals ? org.open_proposals.committees : 0;
  const blocked = openFacts + openCommittees > 0;
  const alreadyReviewed = org.profile_status === "reviewed";
  const reason = blocked
    ? `Resolve the ${openFacts + openCommittees} open proposal${openFacts + openCommittees === 1 ? "" : "s"} first` +
      (openCommittees ? ` (${openCommittees} on the Committees tab).` : ".")
    : "";

  const byKey = useMemo(() => {
    const m = {};
    for (const f of facts || []) {
      m[f.key] = m[f.key] || {};
      if (f.status === "confirmed") m[f.key].confirmed = f;
      if (f.status === "proposed") m[f.key].proposal = f;
    }
    return m;
  }, [facts]);

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", gap: space.md, flexWrap: "wrap", alignItems: "flex-start" }}>
        <SectionTitle hint="Only record what the documents or the client say. Every fact shows where it came from.">
          Profile
        </SectionTitle>
        <div style={{ display: "grid", justifyItems: "end", gap: 4 }}>
          <Button onClick={() => run(async () => { await orgApi.markReviewed(id); await refresh(); })} disabled={busy || blocked || alreadyReviewed} title={reason || (alreadyReviewed ? "Already reviewed. Any change sets it back to draft." : undefined)}>
            Mark profile reviewed
          </Button>
          <span style={{ fontSize: font.small, color: blocked ? "#92400E" : color.textMuted }}>
            {blocked
              ? reason
              : org.profile_status === "reviewed"
              ? `Reviewed ${formatDate(org.profile_reviewed_at)} (version ${org.profile_version})`
              : "Any change to a confirmed fact sets the profile back to draft."}
          </span>
        </div>
      </div>

      {error ? (
        <div style={{ margin: `${space.sm}px 0` }}>
          <Notice tone="error">{error}</Notice>
        </div>
      ) : null}

      {facts === null ? (
        <p style={{ color: color.textMuted }}>Loading…</p>
      ) : (
        registry.groups.map((g) => (
          <section key={g.key} style={{ marginTop: space.lg }} aria-labelledby={`group-${g.key}`}>
            <h3 id={`group-${g.key}`} style={{ margin: 0, fontSize: 12, fontWeight: font.weight.heavy, letterSpacing: 0.6, textTransform: "uppercase", color: color.textMuted }}>
              {g.label}
            </h3>
            {registry.facts
              .filter((s) => s.group === g.key)
              .map((spec) => (
                <FactRow
                  key={spec.key}
                  ui={ui}
                  org={org}
                  spec={spec}
                  confirmed={byKey[spec.key] && byKey[spec.key].confirmed}
                  proposal={byKey[spec.key] && byKey[spec.key].proposal}
                  docNames={docNames}
                  onChanged={refresh}
                />
              ))}
          </section>
        ))
      )}
      <Panel style={{ marginTop: space.lg, background: color.surfaceMuted }}>
        <span style={{ fontSize: 13, color: color.textMuted }}>
          Sources: <b>Public</b> = public information · <b>Client</b> = supplied by the company · <b>Consultant</b> = your own judgement.
        </span>
      </Panel>
    </div>
  );
}
