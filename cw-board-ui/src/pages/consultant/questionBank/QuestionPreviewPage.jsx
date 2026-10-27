import React, { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { questionBankApi } from "../../../api/questionBankApi.js";
import { color, font, radius, space } from "../../../theme.js";
import { Notice, Panel, SectionTitle } from "../companies/shared.jsx";
import { useAsync } from "../companies/helpers.js";
import { ANSWER_TYPE_LABELS } from "./bankHelpers.js";
import AssembledSet from "./AssembledSet.jsx";
import AssemblyPanel from "./AssemblyPanel.jsx";

function plural(n, word) {
  return `${n} ${word}${n === 1 ? "" : "s"}`;
}

function ItemCode({ code }) {
  return <span style={{ fontVariantNumeric: "tabular-nums", fontWeight: font.weight.bold, whiteSpace: "nowrap" }}>{code}</span>;
}

function Summary({ ui, data, selected, onSelect }) {
  const { Badge } = ui;
  return (
    <div style={ui.tableWrapStyle()}>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: font.body, minWidth: 640 }}>
        <thead>
          <tr style={{ background: color.surfaceMuted, textAlign: "left" }}>
            {["Participant", "Questions", "Confirm", "Skipped", "Blocked", "Time"].map((h) => (
              <th key={h} scope="col" style={{ ...ui.tdStyle(), fontWeight: font.weight.heavy }}>
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.participants.map((p) => {
            const isSelected = p.participant_id === selected;
            return (
              <tr
                key={p.participant_id}
                style={{
                  borderTop: `1px solid ${color.border}`,
                  background: isSelected ? color.primarySoft : p.long ? "#FFFBF5" : undefined,
                }}
              >
                <td style={ui.tdStyle()}>
                  <button
                    type="button"
                    onClick={() => onSelect(p.participant_id)}
                    aria-pressed={isSelected}
                    style={{
                      padding: 0,
                      border: 0,
                      background: "none",
                      textAlign: "left",
                      cursor: "pointer",
                      color: color.primaryText,
                      fontWeight: font.weight.bold,
                      fontSize: font.body,
                      textDecoration: "underline",
                    }}
                  >
                    {p.label}
                  </button>
                  <div style={{ fontSize: font.small, color: color.textMuted }}>{p.role_label}</div>
                </td>
                <td style={ui.tdStyle()}>
                  {p.counts.included}
                  <div style={{ fontSize: font.small, color: color.textMuted }}>{plural(p.counts.subjects, "subject")}</div>
                </td>
                <td style={ui.tdStyle()}>{p.counts.to_confirm}</td>
                <td style={ui.tdStyle()}>{p.counts.skipped}</td>
                <td style={ui.tdStyle()}>{p.counts.blocked ? <Badge tone="red">{p.counts.blocked}</Badge> : 0}</td>
                <td style={{ ...ui.tdStyle(), whiteSpace: "nowrap" }}>
                  ~{p.estimated_minutes} min
                  {p.long ? (
                    <div style={{ marginTop: 4 }}>
                      <Badge tone="amber">Long</Badge>
                    </div>
                  ) : null}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function groupBySubject(entries) {
  const groups = [];
  const byKey = {};
  entries.forEach((e) => {
    if (!byKey[e.subject.key]) {
      byKey[e.subject.key] = { subject: e.subject, items: [] };
      groups.push(byKey[e.subject.key]);
    }
    byKey[e.subject.key].items.push(e);
  });
  return groups;
}

const SUBJECT_KIND = { board: "The board", function: "Function", person: "Person", committee: "Committee" };

function Included({ ui, participant }) {
  const { Badge } = ui;
  const groups = groupBySubject(participant.included);
  if (!groups.length) return <p style={{ margin: 0, color: color.textMuted }}>No items for this participant.</p>;
  return (
    <div style={{ display: "grid", gap: space.sm }}>
      {groups.map((g) => (
        <details key={g.subject.key} style={{ border: `1px solid ${color.border}`, borderRadius: radius.md, background: color.surface }}>
          <summary style={{ padding: space.md, cursor: "pointer", fontWeight: font.weight.bold }}>
            About {g.subject.kind === "board" ? "the board" : g.subject.label}
            <span style={{ fontWeight: font.weight.regular, color: color.textMuted }}>
              {" "}
              · {g.subject.kind === "board" ? "" : `${SUBJECT_KIND[g.subject.kind]} · `}
              {plural(g.items.length, "item")} · ~{Math.max(1, Math.round(g.items.reduce((s, i) => s + i.seconds, 0) / 60))} min
            </span>
          </summary>
          <ol style={{ margin: 0, padding: `0 ${space.md}px ${space.md}px ${space.md + 18}px`, display: "grid", gap: space.md }}>
            {g.items.map((i) => (
              <li key={`${i.code}-${g.subject.key}`}>
                <div style={{ display: "flex", gap: space.sm, flexWrap: "wrap", alignItems: "center" }}>
                  <ItemCode code={i.code} />
                  <span style={{ fontSize: font.small, color: color.textMuted }}>{ANSWER_TYPE_LABELS[i.answer_type]}</span>
                  {i.status === "draft" ? <Badge tone="amber">Draft</Badge> : null}
                  {i.confirm ? <Badge tone="green">Confirm stored value</Badge> : null}
                </div>
                <div style={{ marginTop: 2 }}>{i.text}</div>
                {i.confirm ? (
                  <div style={{ fontSize: 13, marginTop: 2 }}>
                    Stored {i.confirm.known_from_label.toLowerCase()}: <strong>{i.confirm.value_text}</strong>
                  </div>
                ) : null}
                <div style={{ fontSize: 13, color: color.textMuted, marginTop: 2 }}>{i.why}</div>
              </li>
            ))}
          </ol>
        </details>
      ))}
    </div>
  );
}

function SimpleList({ entries, render, empty }) {
  if (!entries.length) return <p style={{ margin: 0, color: color.textMuted }}>{empty}</p>;
  return (
    <ul style={{ margin: 0, paddingLeft: 18, display: "grid", gap: space.sm, fontSize: 13 }}>
      {entries.map((e, n) => (
        <li key={`${e.code}-${e.subject.key}-${n}`}>{render(e)}</li>
      ))}
    </ul>
  );
}

function ParticipantDetail({ ui, participant }) {
  const p = participant;
  return (
    <div style={{ display: "grid", gap: space.lg, gridTemplateColumns: "minmax(0, 1fr)" }}>
      <div>
        <SectionTitle hint={`${p.role_label} · ${plural(p.counts.included, "question")} about ${plural(p.counts.subjects, "subject")}, about ${p.estimated_minutes} minutes.`}>
          {p.label}
        </SectionTitle>
        {p.long ? <Notice tone="warn">This preview is long. Consider trimming items before assembly.</Notice> : null}
      </div>

      <section>
        <SectionTitle hint="Grouped by what each item is about. Open a group to see the items and why each was included.">
          Included
        </SectionTitle>
        <Included ui={ui} participant={p} />
      </section>

      <section>
        <SectionTitle hint="Not asked, because a confirmed fact already answers them.">Skipped: already known</SectionTitle>
        <SimpleList
          entries={p.skipped}
          empty="Nothing skipped."
          render={(e) => (
            <>
              <ItemCode code={e.code} /> {e.text}
              <div style={{ color: color.textMuted }}>
                About {e.subject.label}. Stored {e.known_from_label.toLowerCase()}: <strong style={{ color: color.text }}>{e.value_text}</strong>
              </div>
            </>
          )}
        />
      </section>

      <section>
        <SectionTitle hint="Would apply, but data is missing. Confirm the facts to unblock them.">Blocked by missing data</SectionTitle>
        <SimpleList
          entries={p.blocked}
          empty="Nothing blocked."
          render={(e) => (
            <>
              <ItemCode code={e.code} /> {e.text}
              <div style={{ color: color.danger }}>
                About {e.subject.label}. Missing: {e.missing.join(", ")}
              </div>
            </>
          )}
        />
      </section>

      <details>
        <summary style={{ cursor: "pointer", fontWeight: font.weight.bold, fontSize: 15 }}>
          Not included ({p.counts.not_included})
        </summary>
        <div style={{ marginTop: space.sm }}>
          <SimpleList
            entries={p.not_included}
            empty="Nothing left out."
            render={(e) => (
              <>
                <ItemCode code={e.code} /> about {e.subject.label}
                <div style={{ color: color.textMuted }}>{e.reasons.join("; ")}</div>
              </>
            )}
          />
        </div>
      </details>
    </div>
  );
}

export default function QuestionPreviewPage({ ui, evalId }) {
  const { Card } = ui;
  const [includeDrafts, setIncludeDrafts] = useState(true);
  const [data, setData] = useState(null);
  const [selected, setSelected] = useState("");
  const [view, setView] = useState("preview");
  const [setsVersion, setSetsVersion] = useState(0);
  const { busy, error, run } = useAsync();
  const refreshSets = useCallback(() => setSetsVersion((n) => n + 1), []);
  const id = String(evalId || "").trim();

  const load = useCallback(() => {
    if (!id) return;
    run(async () => setData(await questionBankApi.preview(id, { includeDrafts })));
  }, [id, includeDrafts, run]);
  useEffect(() => {
    load();
  }, [load]);

  if (!id) {
    return (
      <Card title="Question preview">
        <Notice tone="info">
          Open an evaluation first (<Link to="/consultant/evaluations">Evaluations</Link>), then come back to see which items each participant would get.
        </Notice>
      </Card>
    );
  }

  const participant = data?.participants.find((p) => p.participant_id === selected) || data?.participants[0];
  const ctx = data?.context;

  return (
    <Card
      title="Question preview"
      subtitle="Which question bank items each participant would get, about whom, and why. Nothing is created or sent."
    >
      {/* minmax(0, 1fr): wide tables scroll in their own box instead of widening the page */}
      <div style={{ display: "grid", gap: space.lg, gridTemplateColumns: "minmax(0, 1fr)" }}>
        <div style={{ display: "flex", gap: space.md, flexWrap: "wrap", alignItems: "center", justifyContent: "space-between" }}>
          <label style={{ fontSize: 13, display: "flex", gap: 6, alignItems: "center" }}>
            <input type="checkbox" checked={includeDrafts} onChange={(e) => setIncludeDrafts(e.target.checked)} />
            Include draft items (not yet approved)
          </label>
          {busy ? <span style={{ fontSize: 13, color: color.textMuted }}>Updating…</span> : null}
        </div>

        {error ? <Notice tone="error">{error}</Notice> : null}
        {(data?.warnings || []).map((w) => (
          <Notice key={w} tone="warn">
            {w}
          </Notice>
        ))}

        {ctx ? (
          <Panel>
            <dl style={{ margin: 0, display: "grid", gap: space.sm, gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", fontSize: 13 }}>
              {[
                ["Sector", ctx.sector || "Not set"],
                ["Governance codes", ctx.governance_codes.map((c) => c.replace("_", " ")).join(", ") || "None"],
                ["Year under review", ctx.review_year],
                ["Committees", ctx.committees.map((c) => c.name).join(", ") || "None confirmed"],
                ["Items considered", data.items_considered],
              ].map(([k, v]) => (
                <div key={k}>
                  <dt style={{ color: color.textMuted }}>{k}</dt>
                  <dd style={{ margin: 0, fontWeight: font.weight.bold }}>{v}</dd>
                </div>
              ))}
            </dl>
          </Panel>
        ) : null}

        <AssemblyPanel ui={ui} evalId={id} onOptionsChanged={load} onRunFinished={refreshSets} />

        {data === null ? (
          <p style={{ color: color.textMuted }}>Loading…</p>
        ) : data.participants.length === 0 ? (
          <Notice tone="info">This evaluation has no participants yet.</Notice>
        ) : (
          <>
            <section>
              <SectionTitle hint={`Rows over ${data.long_preview_minutes} minutes are marked long. Select a participant to see their items.`}>
                Participants
              </SectionTitle>
              <Summary ui={ui} data={data} selected={participant?.participant_id} onSelect={setSelected} />
            </section>
            {participant ? (
              <>
                <div role="tablist" aria-label="Participant view" style={{ display: "flex", gap: space.sm, flexWrap: "wrap" }}>
                  {[
                    ["preview", "Selection preview"],
                    ["assembled", "Assembled draft"],
                  ].map(([key, label]) => (
                    <ui.Button key={key} variant={view === key ? "primary" : "secondary"} onClick={() => setView(key)}>
                      {label}
                    </ui.Button>
                  ))}
                </div>
                {view === "preview" ? (
                  <ParticipantDetail ui={ui} participant={participant} />
                ) : (
                  <section>
                    <SectionTitle hint="Bank text and any AI suggestion side by side. Editing and approval come in the review screen.">
                      {participant.label}: assembled draft
                    </SectionTitle>
                    <AssembledSet ui={ui} evalId={id} participantId={participant.participant_id} refreshKey={setsVersion} />
                  </section>
                )}
              </>
            ) : null}
          </>
        )}
      </div>
    </Card>
  );
}
