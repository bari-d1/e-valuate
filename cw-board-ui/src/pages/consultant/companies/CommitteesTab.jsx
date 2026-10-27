import React, { useCallback, useEffect, useState } from "react";
import { SOURCE_LABELS, boardApi, orgApi } from "../../../api/orgApi.js";
import { color, font, space } from "../../../theme.js";
import { Excerpt, LinkButton, Notice, Panel, SectionTitle } from "./shared.jsx";
import { inputCss, useAsync, visuallyHidden } from "./helpers.js";

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
          <input value={name} onChange={(e) => setName(e.target.value)} style={inputCss()} maxLength={255} />
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

function LinkedMembers({ ui, org, c, links, members, onChanged }) {
  const { Badge, Button } = ui;
  const { busy, error, run } = useAsync();
  const [adding, setAdding] = useState(false);
  const [memberId, setMemberId] = useState("");
  const [role, setRole] = useState("member");
  const [redrafted, setRedrafted] = useState("");
  const id = org.organisation_id;
  // Changing someone's committee seats sends their profile back to draft for re-review (who: their name)
  const act = (fn, who) =>
    run(async () => {
      await fn();
      setRedrafted(who || "");
      await onChanged();
    });
  const linked = links.filter((l) => l.status === "confirmed");
  const proposed = links.filter((l) => l.status === "proposed");
  const linkedIds = new Set(links.filter((l) => l.status !== "rejected").map((l) => l.board_member_id));
  const available = members.filter((m) => m.active && !linkedIds.has(m.board_member_id));

  return (
    <div style={{ marginTop: space.sm, borderTop: `1px solid ${color.border}`, paddingTop: space.sm }}>
      <div style={{ fontSize: 13, fontWeight: font.weight.bold, color: color.text }}>Linked board members</div>
      {linked.length ? (
        <ul style={{ listStyle: "none", margin: "4px 0 0", padding: 0, display: "grid", gap: 4 }}>
          {linked.map((l) => (
            <li key={l.membership_id} style={{ display: "flex", gap: space.sm, alignItems: "center", flexWrap: "wrap", fontSize: 13 }}>
              <span style={{ color: color.text }}>{l.board_member}</span>
              {l.membership_role === "chair" ? <Badge tone="blue">Chair</Badge> : null}
              <LinkButton danger disabled={busy} onClick={() => window.confirm(`Unlink ${l.board_member}?`) && act(() => boardApi.deleteMembership(id, l.membership_id), l.board_member)}>
                Unlink
              </LinkButton>
            </li>
          ))}
        </ul>
      ) : (
        <div style={{ marginTop: 2, fontSize: 13, color: color.textMuted }}>None yet.</div>
      )}
      {proposed.map((l) => (
        <Panel key={l.membership_id} highlight style={{ marginTop: space.sm, padding: space.sm }}>
          <div style={{ display: "flex", gap: space.sm, alignItems: "center", flexWrap: "wrap", fontSize: 13 }}>
            <Badge tone="amber">Proposed</Badge>
            <span style={{ fontWeight: font.weight.bold, color: color.text }}>{l.board_member}</span>
            {l.membership_role === "chair" ? <Badge tone="blue">Chair</Badge> : null}
          </div>
          {l.matched_name ? (
            <div style={{ marginTop: 2, fontSize: font.small, color: color.textMuted }}>Matched “{l.matched_name}”</div>
          ) : null}
          <div style={{ display: "flex", gap: space.sm, flexWrap: "wrap", marginTop: space.sm }}>
            <Button onClick={() => act(() => boardApi.confirmMembership(id, l.membership_id), l.board_member)} disabled={busy}>
              Confirm
            </Button>
            <Button variant="danger" onClick={() => act(() => boardApi.rejectMembership(id, l.membership_id))} disabled={busy}>
              Reject
            </Button>
          </div>
        </Panel>
      ))}
      {adding ? (
        <div style={{ display: "flex", gap: space.sm, flexWrap: "wrap", alignItems: "center", marginTop: space.sm }}>
          <label style={visuallyHidden} htmlFor={`add-link-${c.committee_id}`}>
            Board member
          </label>
          <select id={`add-link-${c.committee_id}`} value={memberId} onChange={(e) => setMemberId(e.target.value)} style={inputCss({ flex: "1 1 180px", width: "auto" })}>
            <option value="">Choose a board member…</option>
            {available.map((m) => (
              <option key={m.board_member_id} value={m.board_member_id}>
                {m.label}
              </option>
            ))}
          </select>
          <label style={visuallyHidden} htmlFor={`add-role-${c.committee_id}`}>
            Role on the committee
          </label>
          <select id={`add-role-${c.committee_id}`} value={role} onChange={(e) => setRole(e.target.value)} style={inputCss({ width: "auto" })}>
            <option value="member">Member</option>
            <option value="chair">Chair</option>
          </select>
          <Button
            disabled={busy || !memberId}
            onClick={() =>
              act(async () => {
                await boardApi.addMembership(id, { committee_id: c.committee_id, board_member_id: memberId, membership_role: role });
                setAdding(false);
                setMemberId("");
              }, available.find((m) => m.board_member_id === memberId)?.label)
            }
          >
            Link
          </Button>
          <Button variant="secondary" onClick={() => setAdding(false)} disabled={busy}>
            Cancel
          </Button>
        </div>
      ) : available.length ? (
        <div style={{ marginTop: space.sm }}>
          <LinkButton onClick={() => setAdding(true)}>Add a board member</LinkButton>
        </div>
      ) : null}
      {redrafted && !error ? (
        <div style={{ marginTop: space.sm }}>
          <Notice tone="info">{`${redrafted}'s profile is back to Draft because their committee seats changed. Re-review it on the Board tab.`}</Notice>
        </div>
      ) : null}
      {error ? (
        <div style={{ marginTop: space.sm }}>
          <Notice tone="error">{error}</Notice>
        </div>
      ) : null}
    </div>
  );
}

function plural(n, one, many) {
  return `${n} ${n === 1 ? one : many}`;
}

function MatchResults({ ui, org, result, onChanged }) {
  const { Button } = ui;
  const { busy, error, run } = useAsync();
  const [linkedNames, setLinkedNames] = useState([]);
  const [redrafted, setRedrafted] = useState([]);
  const id = org.organisation_id;
  const entryKey = (e) => `${e.committee_id}-${e.name}`;
  const link = (entry, cand) =>
    run(async () => {
      await boardApi.addMembership(id, {
        committee_id: entry.committee_id,
        board_member_id: cand.board_member_id,
        membership_role: entry.membership_role,
      });
      setLinkedNames((prev) => [...prev, entryKey(entry)]);
      setRedrafted((prev) => [...prev, cand.board_member]);
      await onChanged();
    });
  const nearMisses = result.near_misses.filter((e) => !linkedNames.includes(entryKey(e)));
  const rejected = result.previously_rejected || [];
  return (
    <Panel style={{ marginBottom: space.md }}>
      <Notice tone={result.proposed.length ? "success" : "info"}>
        {result.proposed.length
          ? `${plural(result.proposed.length, "exact match", "exact matches")} proposed below for you to confirm.`
          : "No new exact matches."}
        {result.already_linked.length ? ` ${plural(result.already_linked.length, "name is", "names are")} already linked.` : ""}
        {rejected.length ? ` ${plural(rejected.length, "match was", "matches were")} rejected before and left alone.` : ""}
        {result.skipped_committees.length ? `\nNot matched: ${result.skipped_committees.map((s) => `${s.committee} (${s.reason})`).join(", ")}.` : ""}
      </Notice>
      {redrafted.length ? (
        <div style={{ marginTop: space.sm }}>
          <Notice tone="info">{`Back to Draft because their committee seats changed: ${redrafted.join(", ")}. Re-review them on the Board tab.`}</Notice>
        </div>
      ) : null}
      {nearMisses.length ? (
        <div style={{ marginTop: space.md }}>
          <SectionTitle hint="Close but not exact, so nothing was proposed. Link one only if it's the same person.">Near-misses</SectionTitle>
          <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "grid", gap: space.sm }}>
            {nearMisses.map((e) => (
              <li key={`${e.committee_id}-${e.name}`} style={{ fontSize: 13, borderTop: `1px solid ${color.border}`, paddingTop: space.sm }}>
                <div style={{ color: color.text }}>
                  <b>“{e.name}”</b> on {e.committee}
                  {e.membership_role === "chair" ? " (chair)" : ""}
                  {e.reason ? <span style={{ color: color.textMuted }}> · {e.reason}</span> : null}
                </div>
                <ul style={{ listStyle: "none", margin: "4px 0 0", padding: 0, display: "grid", gap: 6 }}>
                  {e.candidates.map((cand) => (
                    <li key={cand.board_member_id} style={{ display: "flex", gap: space.sm, flexWrap: "wrap", alignItems: "center" }}>
                      <Button variant="secondary" disabled={busy} onClick={() => link(e, cand)}>
                        {`Link ${cand.board_member}`}
                      </Button>
                      <span style={{ color: color.textMuted }}>{cand.reason}</span>
                    </li>
                  ))}
                </ul>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      {result.unmatched.length ? (
        <div style={{ marginTop: space.md }}>
          <SectionTitle hint="No board member has a similar name. Add them on the Board tab, or link someone by hand.">Unmatched names</SectionTitle>
          <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13, color: color.text }}>
            {result.unmatched.map((e) => (
              <li key={`${e.committee_id}-${e.name}`}>
                “{e.name}” on {e.committee}
                {e.membership_role === "chair" ? " (chair)" : ""}
              </li>
            ))}
          </ul>
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

function CommitteeCard({ ui, org, c, docNames, links, members, onChanged }) {
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
      {!proposed ? <LinkedMembers ui={ui} org={org} c={c} links={links} members={members} onChanged={onChanged} /> : null}

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
  const [links, setLinks] = useState([]);
  const [members, setMembers] = useState([]);
  const [matchResult, setMatchResult] = useState(null);
  const { busy, error, run } = useAsync();
  const id = org.organisation_id;

  const load = useCallback(
    () =>
      run(async () => {
        const [c, d, l, m] = await Promise.all([
          orgApi.committees(id),
          orgApi.documents(id),
          boardApi.memberships(id),
          boardApi.list(id),
        ]);
        setItems(c.items.filter((x) => x.status !== "rejected"));
        setLinks(l.items);
        setMembers(m.items);
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
        <SectionTitle hint="Names exactly as written in the company's documents, linked to board members once confirmed.">
          Committees
        </SectionTitle>
        <div style={{ display: "flex", gap: space.sm, flexWrap: "wrap" }}>
          <Button
            onClick={() => run(async () => { setMatchResult(await boardApi.match(id)); await refresh(); })}
            disabled={busy}
            title="Propose links where a committee name exactly matches a board member's name"
          >
            Match members
          </Button>
          {!adding ? (
            <Button variant="secondary" onClick={() => setAdding(true)}>
              Add committee
            </Button>
          ) : null}
        </div>
      </div>

      {error ? <Notice tone="error">{error}</Notice> : null}

      {matchResult ? <MatchResults ui={ui} org={org} result={matchResult} onChanged={refresh} /> : null}

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
            <CommitteeCard key={c.committee_id} ui={ui} org={org} c={c} docNames={docNames} links={links.filter((l) => l.committee_id === c.committee_id)} members={members} onChanged={refresh} />
          ))}
        </div>
      )}
    </div>
  );
}
