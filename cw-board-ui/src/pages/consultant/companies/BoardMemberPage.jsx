import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { boardApi, downloadDocument } from "../../../api/orgApi.js";
import { color, font, space } from "../../../theme.js";
import { DroppedItems, Excerpt, LinkButton, Notice, Panel, ParticipantCorrections, SectionTitle, SourceTag } from "./shared.jsx";
import { formatDate, inputCss, useAsync, visuallyHidden } from "./helpers.js";
import { TRISTATE, roleLabel, useMemberRegistry } from "./boardHelpers.js";

// ----------------------------
// Values
// ----------------------------

function formatValue(spec, value) {
  if (value === null || value === undefined) return "—";
  if (spec.type === "choice") return (spec.options.find((o) => o.key === value) || {}).label || value;
  if (spec.type === "date") return formatDate(value);
  if (spec.type === "list") return (value || []).join(", ");
  if (spec.type === "tristate") {
    const label = (TRISTATE.find((t) => t.key === value.answer) || TRISTATE[2]).label;
    return value.detail ? `${label} (${value.detail})` : label;
  }
  return String(value);
}

function toForm(spec, value) {
  if (spec.type === "list") return (value || []).join("\n");
  if (spec.type === "tristate") return { answer: (value && value.answer) || "unknown", detail: (value && value.detail) || "" };
  if (value === null || value === undefined) return spec.type === "choice" ? spec.options[0].key : "";
  return String(value);
}

function fromForm(spec, form) {
  if (spec.type === "list") return form.split("\n").map((s) => s.trim()).filter(Boolean);
  if (spec.type === "tristate") return form.detail.trim() ? { answer: form.answer, detail: form.detail.trim() } : { answer: form.answer };
  return form;
}

function ValueInput({ spec, form, setForm, idPrefix }) {
  const id = `${idPrefix}-value`;
  if (spec.type === "choice")
    return (
      <select id={id} value={form} onChange={(e) => setForm(e.target.value)} style={inputCss({ maxWidth: 360 })}>
        {spec.options.map((o) => (
          <option key={o.key} value={o.key}>
            {o.label}
          </option>
        ))}
      </select>
    );
  if (spec.type === "date")
    return <input id={id} type="date" value={form} onChange={(e) => setForm(e.target.value)} style={inputCss({ maxWidth: 200 })} />;
  if (spec.type === "list")
    return <textarea id={id} value={form} onChange={(e) => setForm(e.target.value)} rows={3} placeholder="One per line" style={inputCss({ resize: "vertical" })} />;
  if (spec.type === "tristate")
    return (
      <div style={{ display: "grid", gap: space.sm }}>
        <div role="radiogroup" aria-labelledby={`${idPrefix}-label`} style={{ display: "flex", gap: space.md, flexWrap: "wrap" }}>
          {TRISTATE.map((t) => (
            <label key={t.key} style={{ display: "inline-flex", gap: 6, alignItems: "center", fontSize: font.body, color: color.text }}>
              <input type="radio" name={id} checked={form.answer === t.key} onChange={() => setForm({ ...form, answer: t.key })} />
              {t.label}
            </label>
          ))}
        </div>
        <input
          aria-label="Detail (optional)"
          placeholder="Detail (optional)"
          value={form.detail}
          onChange={(e) => setForm({ ...form, detail: e.target.value })}
          style={inputCss()}
        />
      </div>
    );
  return <textarea id={id} value={form} onChange={(e) => setForm(e.target.value)} rows={3} style={inputCss({ resize: "vertical" })} />;
}

function FactEditor({ ui, spec, initial, initialSource = "client", submitLabel, onSubmit, onCancel, busy }) {
  const { Button } = ui;
  const [form, setForm] = useState(() => toForm(spec, initial));
  const [source, setSource] = useState(initialSource);
  const idPrefix = `member-fact-${spec.key}`;
  return (
    <div style={{ marginTop: space.sm, display: "grid", gap: space.sm }}>
      <div>
        <label
          id={`${idPrefix}-label`}
          htmlFor={spec.type === "tristate" ? undefined : `${idPrefix}-value`}
          style={{ display: "block", fontSize: 13, fontWeight: font.weight.bold, color: color.text, marginBottom: 4 }}
        >
          {spec.label}
        </label>
        <ValueInput spec={spec} form={form} setForm={setForm} idPrefix={idPrefix} />
        {spec.help ? <div style={{ marginTop: 2, fontSize: font.small, color: color.textMuted }}>{spec.help}</div> : null}
      </div>
      <label style={{ fontSize: 13, fontWeight: font.weight.bold, color: color.text, maxWidth: 260 }}>
        Where does this come from?
        <select value={source} onChange={(e) => setSource(e.target.value)} style={inputCss({ marginTop: 4 })}>
          <option value="client">Client (supplied by the company)</option>
          <option value="public">Public source</option>
          <option value="consultant">Consultant's own judgement</option>
        </select>
      </label>
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
// One fact (list layout, or a compact row for the independence grid)
// ----------------------------

function useFactActions(orgId, memberId, onChanged) {
  const { busy, error, run } = useAsync();
  const [mode, setMode] = useState(null); // "add" | "edit" | "edit-proposal" | "fix:<fact id>"
  const act = (fn) =>
    run(async () => {
      await fn();
      setMode(null);
      await onChanged();
    });
  return { busy, error, mode, setMode, act, api: (name, ...args) => boardApi[name](orgId, memberId, ...args) };
}

function Proposal({ ui, spec, proposal, confirmed, docNames, f }) {
  const { Badge, Button } = ui;
  return (
    <Panel highlight style={{ marginTop: space.sm }}>
      <div style={{ display: "flex", gap: space.sm, alignItems: "center", flexWrap: "wrap" }}>
        <Badge tone="amber">Proposed</Badge>
        <span style={{ fontWeight: font.weight.bold, color: color.text, whiteSpace: "pre-wrap" }}>{formatValue(spec, proposal.value)}</span>
        <SourceTag ui={ui} source={proposal.source} />
      </div>
      <Excerpt text={proposal.source_excerpt} filename={docNames[proposal.source_document_id]} />
      {proposal.note ? <div style={{ marginTop: 4, fontSize: font.small, color: color.textMuted }}>{proposal.note}</div> : null}
      {confirmed ? <div style={{ marginTop: 4, fontSize: font.small, color: color.textMuted }}>Confirming replaces the current value.</div> : null}
      {f.mode === "edit-proposal" ? (
        <FactEditor ui={ui} spec={spec} busy={f.busy} submitLabel="Confirm with this value" initial={proposal.value}
          initialSource={proposal.source} onCancel={() => f.setMode(null)}
          onSubmit={(value, source) => f.act(() => f.api("confirmFact", proposal.fact_id, { value, source }))} />
      ) : (
        <div style={{ display: "flex", gap: space.sm, flexWrap: "wrap", marginTop: space.sm }}>
          <Button onClick={() => f.act(() => f.api("confirmFact", proposal.fact_id))} disabled={f.busy}>
            Confirm
          </Button>
          <Button variant="secondary" onClick={() => f.setMode("edit-proposal")} disabled={f.busy}>
            Edit
          </Button>
          <Button variant="danger" onClick={() => f.act(() => f.api("rejectFact", proposal.fact_id))} disabled={f.busy}>
            Reject
          </Button>
        </div>
      )}
    </Panel>
  );
}

function FactBody({ ui, spec, confirmed, proposal, corrections, docNames, f }) {
  return (
    <>
      {f.mode === "add" ? (
        <FactEditor ui={ui} spec={spec} busy={f.busy} submitLabel="Save" onCancel={() => f.setMode(null)}
          onSubmit={(value, source) => f.act(() => f.api("addFact", { key: spec.key, value, source }))} />
      ) : null}
      {f.mode === "edit" && confirmed ? (
        <FactEditor ui={ui} spec={spec} busy={f.busy} submitLabel="Save" initial={confirmed.value} initialSource={confirmed.source}
          onCancel={() => f.setMode(null)}
          onSubmit={(value, source) => f.act(() => f.api("updateFact", confirmed.fact_id, { value, source }))} />
      ) : null}
      {proposal ? <Proposal ui={ui} spec={spec} proposal={proposal} confirmed={confirmed} docNames={docNames} f={f} /> : null}
      <ParticipantCorrections
        ui={ui}
        items={corrections}
        busy={f.busy}
        editingId={f.mode && f.mode.startsWith("fix:") ? f.mode.slice(4) : null}
        onEdit={(factId) => f.setMode(`fix:${factId}`)}
        onDismiss={(p) => f.act(() => f.api("rejectFact", p.fact_id))}
        renderEditor={(p) => (
          <FactEditor ui={ui} spec={spec} busy={f.busy} submitLabel="Confirm this value" initial={confirmed ? confirmed.value : undefined}
            initialSource="client" onCancel={() => f.setMode(null)}
            onSubmit={(value, source) => f.act(() => f.api("confirmFact", p.fact_id, { value, source }))} />
        )}
      />
      {f.error ? (
        <div style={{ marginTop: space.sm }}>
          <Notice tone="error">{f.error}</Notice>
        </div>
      ) : null}
    </>
  );
}

function FactActions({ spec, confirmed, f }) {
  if (f.mode !== null) return null;
  return (
    <div style={{ display: "flex", gap: space.md, alignItems: "center" }}>
      {confirmed ? (
        <>
          <LinkButton onClick={() => f.setMode("edit")} disabled={f.busy}>
            Edit
          </LinkButton>
          <LinkButton danger disabled={f.busy}
            onClick={() => window.confirm(`Delete ${spec.label}?`) && f.act(() => f.api("deleteFact", confirmed.fact_id))}>
            Delete
          </LinkButton>
        </>
      ) : (
        <LinkButton onClick={() => f.setMode("add")} disabled={f.busy}>
          {spec.type === "tristate" ? "Set" : "Add"}
        </LinkButton>
      )}
    </div>
  );
}

function FactRow({ ui, orgId, memberId, spec, confirmed, proposal, corrections, docNames, onChanged }) {
  const f = useFactActions(orgId, memberId, onChanged);
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
        <FactActions spec={spec} confirmed={confirmed} f={f} />
      </div>
      <FactBody ui={ui} spec={spec} confirmed={confirmed} proposal={proposal} corrections={corrections} docNames={docNames} f={f} />
    </div>
  );
}

/** Participants' corrections to things the profile doesn't hold as a fact (e.g. their committees): dismiss once dealt with. */
function OtherCorrections({ ui, orgId, memberId, registry, facts, onChanged }) {
  const f = useFactActions(orgId, memberId, onChanged);
  const known = new Set(registry.facts.map((s) => s.key));
  const items = facts.filter((x) => x.status === "proposed" && x.origin === "participant" && !known.has(x.key));
  if (!items.length) return null;
  return (
    <Panel style={{ marginTop: space.lg }}>
      <SectionTitle hint="Update the committees or other records yourself, then dismiss the correction.">Other corrections from the participant</SectionTitle>
      <ParticipantCorrections ui={ui} items={items} busy={f.busy} onDismiss={(p) => f.act(() => f.api("rejectFact", p.fact_id))} />
      {f.error ? <Notice tone="error">{f.error}</Notice> : null}
    </Panel>
  );
}

function IndependenceRow({ ui, orgId, memberId, spec, confirmed, proposal, corrections, docNames, onChanged }) {
  const { Badge } = ui;
  const f = useFactActions(orgId, memberId, onChanged);
  const answer = confirmed ? confirmed.value.answer : "unknown";
  const tone = { yes: "red", no: "green", unknown: "gray" }[answer];
  const open = f.mode !== null || proposal || (corrections && corrections.length) || f.error;
  return (
    <>
      <tr style={{ borderTop: `1px solid ${color.border}` }}>
        <th scope="row" style={{ ...ui.tdStyle(), fontWeight: font.weight.medium, textAlign: "left" }}>
          {spec.label}
          {confirmed && confirmed.value.detail ? (
            <div style={{ fontSize: font.small, color: color.textMuted }}>{confirmed.value.detail}</div>
          ) : null}
        </th>
        <td style={ui.tdStyle()}>
          <Badge tone={tone}>{formatValue(spec, { answer })}</Badge>
        </td>
        <td style={ui.tdStyle()}>{confirmed ? <SourceTag ui={ui} source={confirmed.source} /> : null}</td>
        <td style={ui.tdStyle()}>
          <FactActions spec={spec} confirmed={confirmed} f={f} />
        </td>
      </tr>
      {open ? (
        <tr>
          <td colSpan={4} style={{ ...ui.tdStyle(), paddingTop: 0 }}>
            {confirmed && confirmed.source_excerpt ? <Excerpt text={confirmed.source_excerpt} filename={docNames[confirmed.source_document_id]} /> : null}
            <FactBody ui={ui} spec={spec} confirmed={confirmed} proposal={proposal} corrections={corrections} docNames={docNames} f={f} />
          </td>
        </tr>
      ) : null}
    </>
  );
}

// ----------------------------
// Sections
// ----------------------------

function EditMember({ ui, orgId, member, onSaved, onCancel }) {
  const { Button, Field } = ui;
  const { busy, error, run } = useAsync();
  const [name, setName] = useState(member.full_name);
  const [email, setEmail] = useState(member.email || "");
  const [code, setCode] = useState(member.display_code || "");
  const save = () =>
    run(async () =>
      onSaved(
        await boardApi.update(orgId, member.board_member_id, {
          full_name: name.trim(),
          email: email.trim() || null,
          display_code: code.trim() || null,
        })
      )
    );
  return (
    <Panel style={{ marginTop: space.md }}>
      {error ? (
        <div style={{ marginBottom: space.sm }}>
          <Notice tone="error">{error}</Notice>
        </div>
      ) : null}
      <div style={{ display: "grid", gap: space.md, gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", alignItems: "end" }}>
        <Field label="Full name">
          <input value={name} onChange={(e) => setName(e.target.value)} style={inputCss()} maxLength={255} />
        </Field>
        <Field label="Email">
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} style={inputCss()} maxLength={255} />
        </Field>
        <Field label="Display code">
          <input value={code} onChange={(e) => setCode(e.target.value)} style={inputCss({ textTransform: "uppercase" })} maxLength={32} />
        </Field>
      </div>
      <div style={{ display: "flex", gap: space.sm, flexWrap: "wrap", marginTop: space.md }}>
        <Button onClick={save} disabled={busy || !name.trim()}>
          {busy ? "Saving…" : "Save"}
        </Button>
        <Button variant="secondary" onClick={onCancel} disabled={busy}>
          Cancel
        </Button>
      </div>
    </Panel>
  );
}

function Documents({ ui, orgId, member, docs, onChanged }) {
  const { Button, Badge } = ui;
  const input = useRef(null);
  const { busy, error, run } = useAsync();
  const [summary, setSummary] = useState(null);
  const mId = member.board_member_id;
  const readable = docs.filter((d) => d.extraction_status === "done").length;

  return (
    <Panel>
      <SectionTitle hint="CVs and director profiles for this person. PDF, Word (.docx) or text, up to 25 MB.">Documents</SectionTitle>
      {docs.length ? (
        <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "grid", gap: space.sm }}>
          {docs.map((d) => (
            <li key={d.document_id} style={{ display: "flex", gap: space.md, justifyContent: "space-between", flexWrap: "wrap", alignItems: "center", borderTop: `1px solid ${color.border}`, paddingTop: space.sm }}>
              <div style={{ minWidth: 0 }}>
                <div style={{ fontWeight: font.weight.bold, color: color.text, wordBreak: "break-word" }}>{d.filename}</div>
                <div style={{ display: "flex", gap: space.sm, alignItems: "center", flexWrap: "wrap", marginTop: 2, fontSize: font.small, color: color.textMuted }}>
                  {d.extraction_status === "done" ? <Badge tone="green">Text read</Badge> : d.extraction_status === "failed" ? <Badge tone="red">Couldn't read text</Badge> : <Badge tone="gray">Waiting</Badge>}
                  {formatDate(d.uploaded_at)}
                </div>
              </div>
              <div style={{ display: "flex", gap: space.md }}>
                <LinkButton onClick={() => run(() => downloadDocument(orgId, d.document_id, d.filename))} disabled={busy}>
                  Download
                </LinkButton>
                <LinkButton danger disabled={busy}
                  onClick={() => window.confirm(`Delete "${d.filename}"? The stored file is deleted too.`) && run(async () => { await boardApi.deleteDocument(orgId, mId, d.document_id); await onChanged(); })}>
                  Delete
                </LinkButton>
              </div>
            </li>
          ))}
        </ul>
      ) : (
        <p style={{ margin: 0, color: color.textMuted, fontSize: 13 }}>No documents yet.</p>
      )}

      <div style={{ display: "flex", gap: space.sm, flexWrap: "wrap", alignItems: "center", marginTop: space.md }}>
        <label htmlFor="member-upload" style={visuallyHidden}>
          Upload a document for {member.full_name}
        </label>
        <input
          id="member-upload"
          ref={input}
          type="file"
          accept=".pdf,.docx,.txt,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/plain"
          style={{ display: "none" }}
          onChange={(e) => {
            const file = e.target.files && e.target.files[0];
            e.target.value = "";
            if (file) run(async () => { await boardApi.upload(orgId, mId, file); await onChanged(); });
          }}
        />
        <Button variant="secondary" onClick={() => input.current && input.current.click()} disabled={busy}>
          {busy ? "Working…" : "Upload"}
        </Button>
        {member.ai_extraction_enabled ? (
          <Button
            onClick={() => run(async () => { setSummary(await boardApi.extract(orgId, mId)); await onChanged(); })}
            disabled={busy || readable === 0}
            title={readable === 0 ? "Upload a document with readable text first" : undefined}
          >
            Extract profile
          </Button>
        ) : null}
      </div>
      {member.ai_extraction_enabled ? (
        <p style={{ margin: `${space.sm}px 0 0`, fontSize: font.small, color: color.textMuted }}>
          AI proposes facts, each with a quote from the document. Independence stays unknown unless a document says so explicitly. Nothing is saved until you confirm it.
        </p>
      ) : null}
      {summary ? (
        <div style={{ marginTop: space.sm }}>
          <Notice tone="success">
            {`Proposed ${summary.facts_added} new and updated ${summary.facts_updated} fact(s).`}
            {summary.skipped.length ? `\nSkipped: ${summary.skipped.map((s) => `${s.filename}: ${s.reason}`).join("; ")}` : ""}
          </Notice>
          <DroppedItems items={summary.discarded} />
        </div>
      ) : null}
      {error ? (
        <div style={{ marginTop: space.sm }}>
          <Notice tone="error">{error}</Notice>
        </div>
      ) : null}
    </Panel>
  );
}

function ProposedCommittees({ ui, orgId, items, onChanged }) {
  const { Badge, Button } = ui;
  const { busy, error, run } = useAsync();
  if (!items.length) return null;
  return (
    <Panel highlight style={{ marginTop: space.md }}>
      <SectionTitle hint="Matched by name from the company's committees. Confirm or reject each link.">Proposed committee links</SectionTitle>
      <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "grid", gap: space.sm }}>
        {items.map((c) => (
          <li key={c.membership_id} style={{ display: "flex", gap: space.sm, alignItems: "center", flexWrap: "wrap" }}>
            <span style={{ fontWeight: font.weight.bold, color: color.text }}>{c.committee_name}</span>
            <Badge tone={c.membership_role === "chair" ? "blue" : "gray"}>{c.membership_role === "chair" ? "Chair" : "Member"}</Badge>
            <Button onClick={() => run(async () => { await boardApi.confirmMembership(orgId, c.membership_id); await onChanged(); })} disabled={busy}>
              Confirm
            </Button>
            <Button variant="danger" onClick={() => run(async () => { await boardApi.rejectMembership(orgId, c.membership_id); await onChanged(); })} disabled={busy}>
              Reject
            </Button>
          </li>
        ))}
      </ul>
      {error ? (
        <div style={{ marginTop: space.sm }}>
          <Notice tone="error">{error}</Notice>
        </div>
      ) : null}
    </Panel>
  );
}

// ----------------------------
// Page
// ----------------------------

export default function BoardMemberPage({ ui, org, memberId }) {
  const { Badge, Button } = ui;
  const orgId = org.organisation_id;
  const { busy, error, run } = useAsync();
  const registry = useMemberRegistry(run);
  const [member, setMember] = useState(null);
  const [facts, setFacts] = useState(null);
  const [docs, setDocs] = useState([]);
  const [editing, setEditing] = useState(false);

  const load = useCallback(
    () =>
      run(async () => {
        const [m, f, d] = await Promise.all([
          boardApi.get(orgId, memberId),
          boardApi.facts(orgId, memberId),
          boardApi.documents(orgId, memberId),
        ]);
        setMember(m);
        setFacts(f.items);
        setDocs(d.items);
      }),
    [orgId, memberId, run]
  );
  useEffect(() => {
    load();
  }, [load]);

  const byKey = useMemo(() => {
    const out = {};
    for (const f of facts || []) {
      out[f.key] = out[f.key] || {};
      if (f.status === "confirmed") out[f.key].confirmed = f;
      // Participants' corrections sit beside any other proposal for the key
      if (f.status === "proposed" && f.origin === "participant") out[f.key].corrections = [...(out[f.key].corrections || []), f];
      else if (f.status === "proposed") out[f.key].proposal = f;
    }
    return out;
  }, [facts]);
  const docNames = useMemo(() => Object.fromEntries(docs.map((d) => [d.document_id, d.filename])), [docs]);

  if (!member || !registry || !facts) {
    return (
      <div>
        <h2 id="board-member-title" style={visuallyHidden}>Board member</h2>
        {error ? <Notice tone="error">{error}</Notice> : <p style={{ color: color.textMuted }}>Loading…</p>}
      </div>
    );
  }

  const role = member.governance_role;
  const blockers = member.review_blockers;
  const alreadyReviewed = member.profile_status === "reviewed";
  const rowProps = (spec) => ({
    ui,
    orgId,
    memberId,
    spec,
    confirmed: byKey[spec.key] && byKey[spec.key].confirmed,
    proposal: byKey[spec.key] && byKey[spec.key].proposal,
    corrections: byKey[spec.key] && byKey[spec.key].corrections,
    docNames,
    onChanged: load,
  });
  const tenure = member.tenure;

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", gap: space.md, flexWrap: "wrap", alignItems: "flex-start" }}>
        <div style={{ minWidth: 0 }}>
          <h2 id="board-member-title" style={{ margin: 0, fontSize: 18, fontWeight: font.weight.heavy, color: color.text, wordBreak: "break-word" }}>
            {member.display_code ? <span style={{ color: color.textMuted }}>{member.display_code} · </span> : null}
            {member.full_name}
          </h2>
          <div style={{ marginTop: 2, fontSize: 13, color: color.textMuted, overflowWrap: "break-word" }}>
            {member.email || "No email"} · {role ? roleLabel(registry, role) : "Role not confirmed"}
          </div>
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: space.sm }}>
            {member.profile_status === "reviewed" ? <Badge tone="green">Reviewed v{member.profile_version}</Badge> : <Badge tone="amber">Profile draft</Badge>}
            {!member.active ? <Badge tone="gray">Inactive</Badge> : null}
            {member.committees.map((c) => (
              <Badge key={c.membership_id} tone="blue">
                {c.committee_name}
                {c.membership_role === "chair" ? " (Chair)" : ""}
              </Badge>
            ))}
            {tenure && tenure.years !== null ? (
              <Badge tone={tenure.exceeds_limit ? "red" : "gray"}>
                {`${tenure.years} years on the board${tenure.exceeds_limit ? `, over the ${tenure.limit_years}-year limit` : ""}`}
              </Badge>
            ) : null}
          </div>
        </div>
        <div style={{ display: "grid", justifyItems: "end", gap: 4, maxWidth: 360 }}>
          <div style={{ display: "flex", gap: space.sm, flexWrap: "wrap", justifyContent: "flex-end" }}>
            {!editing ? (
              <Button variant="secondary" onClick={() => setEditing(true)}>
                Edit details
              </Button>
            ) : null}
            {member.active ? (
              <Button variant="secondary" disabled={busy}
                onClick={() => window.confirm(`Deactivate ${member.full_name}? They won't be added to new evaluations.`) && run(async () => { await boardApi.deactivate(orgId, memberId); await load(); })}>
                Deactivate
              </Button>
            ) : (
              <Button variant="secondary" disabled={busy} onClick={() => run(async () => { await boardApi.update(orgId, memberId, { active: true }); await load(); })}>
                Reactivate
              </Button>
            )}
            <Button
              onClick={() => run(async () => { await boardApi.markReviewed(orgId, memberId); await load(); })}
              disabled={busy || blockers.length > 0 || alreadyReviewed}
              title={blockers.join(" ") || (alreadyReviewed ? "Already reviewed. Any change sets it back to draft." : undefined)}
            >
              Mark profile reviewed
            </Button>
          </div>
          <span style={{ fontSize: font.small, color: blockers.length ? "#92400E" : color.textMuted, textAlign: "right" }}>
            {blockers.length
              ? blockers.join(" ")
              : member.profile_status === "reviewed"
              ? `Reviewed ${formatDate(member.profile_reviewed_at)} (version ${member.profile_version}). Any change sets it back to draft.`
              : "Any change to a confirmed fact sets the profile back to draft."}
          </span>
        </div>
      </div>

      {error ? (
        <div style={{ marginTop: space.sm }}>
          <Notice tone="error">{error}</Notice>
        </div>
      ) : null}
      {editing ? (
        <EditMember ui={ui} orgId={orgId} member={member} onCancel={() => setEditing(false)}
          onSaved={async () => { setEditing(false); await load(); }} />
      ) : null}

      <div style={{ marginTop: space.lg }}>
        <Documents ui={ui} orgId={orgId} member={member} docs={docs} onChanged={load} />
      </div>
      <ProposedCommittees ui={ui} orgId={orgId} items={member.proposed_committees} onChanged={load} />

      <OtherCorrections ui={ui} orgId={orgId} memberId={memberId} registry={registry} facts={facts} onChanged={load} />

      {registry.groups.map((g) => {
        const specs = registry.facts.filter((s) => s.group === g.key);
        const heading = (
          <h3 id={`member-group-${g.key}`} style={{ margin: 0, fontSize: 12, fontWeight: font.weight.heavy, letterSpacing: 0.6, textTransform: "uppercase", color: color.textMuted, display: "inline" }}>
            {g.label}
          </h3>
        );
        if (g.key === "independence") {
          const known = specs.filter((s) => byKey[s.key] && byKey[s.key].confirmed && byKey[s.key].confirmed.value.answer !== "unknown").length;
          const pending = specs.filter((s) => byKey[s.key] && byKey[s.key].proposal).length;
          return (
            <section key={g.key} style={{ marginTop: space.lg }} aria-labelledby={`member-group-${g.key}`}>
              <details open={(g.expanded_for_roles || []).includes(role) || pending > 0}>
                <summary style={{ cursor: "pointer" }}>
                  {heading}
                  <span style={{ marginLeft: space.sm, fontSize: font.small, color: color.textMuted }}>
                    {known} of {specs.length} answered{pending ? ` · ${pending} proposed` : ""}
                  </span>
                </summary>
                {g.help ? <p style={{ margin: `${space.sm}px 0`, fontSize: 13, color: color.textMuted }}>{g.help}</p> : null}
                <div style={ui.tableWrapStyle()}>
                  <table style={{ width: "100%", borderCollapse: "collapse", fontSize: font.body, minWidth: 520 }}>
                    <thead>
                      <tr style={{ background: color.surfaceMuted, textAlign: "left" }}>
                        {["Question", "Answer", "Source", "Actions"].map((h) => (
                          <th key={h} scope="col" style={{ ...ui.tdStyle(), fontWeight: font.weight.heavy }}>
                            {h === "Actions" ? <span style={visuallyHidden}>{h}</span> : h}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {specs.map((spec) => (
                        <IndependenceRow key={spec.key} {...rowProps(spec)} />
                      ))}
                    </tbody>
                  </table>
                </div>
              </details>
            </section>
          );
        }
        return (
          <section key={g.key} style={{ marginTop: space.lg }} aria-labelledby={`member-group-${g.key}`}>
            {heading}
            {g.key === "framing" ? (
              <div style={{ margin: `${space.sm}px 0` }}>
                <Notice tone="warn">{g.help || "These set question tone only and are never used in analysis."}</Notice>
              </div>
            ) : null}
            {specs.map((spec) => (
              <FactRow key={spec.key} {...rowProps(spec)} />
            ))}
          </section>
        );
      })}
      <Panel style={{ marginTop: space.lg, background: color.surfaceMuted }}>
        <span style={{ fontSize: 13, color: color.textMuted }}>
          Sources: <b>Public</b> = public information · <b>Client</b> = supplied by the company · <b>Consultant</b> = your own judgement.
        </span>
      </Panel>
    </div>
  );
}
