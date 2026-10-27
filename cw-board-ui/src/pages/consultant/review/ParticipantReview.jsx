import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { questionBankApi } from "../../../api/questionBankApi.js";
import { color, font, radius, space } from "../../../theme.js";
import { formatDateTime } from "../../../utils/format.js";
import { Notice, Panel, SectionTitle } from "../companies/shared.jsx";
import { inputCss, useAsync } from "../companies/helpers.js";
import { useBankMeta } from "../questionBank/bankHelpers.js";
import QuestionCard from "./QuestionCard.jsx";
import { AddQuestion, PeerGrid } from "./SetParts.jsx";
import { SECTION_HINTS, SET_STATUS, eventLabel, hasOpenWording, isGrid, isPendingNew, plural } from "./reviewHelpers.js";

const ACTIONS = {
  wording: (e, q, b) => questionBankApi.wording(e, q.id, b),
  regenerate: (e, q, b) => questionBankApi.regenerate(e, q.id, b.note),
  acceptNew: (e, q) => questionBankApi.acceptNew(e, q.id),
  rejectNew: (e, q) => questionBankApi.rejectNew(e, q.id),
  tags: (e, q, b) => questionBankApi.tags(e, q.id, b),
  remove: (e, q, b) => questionBankApi.remove(e, q.id, b?.reason),
  restore: (e, q) => questionBankApi.restore(e, q.id),
  move: (e, q, b) => questionBankApi.move(e, q.id, b.direction),
};

// The approval bar sticks to the bottom only where there's room for it
const STICKY_QUERY = "(min-width: 700px)";
function useWideScreen() {
  const [wide, setWide] = useState(() => typeof window !== "undefined" && window.matchMedia(STICKY_QUERY).matches);
  useEffect(() => {
    const m = window.matchMedia(STICKY_QUERY);
    const on = () => setWide(m.matches);
    m.addEventListener("change", on);
    return () => m.removeEventListener("change", on);
  }, []);
  return wide;
}

function CoverageStrip({ coverage }) {
  if (!coverage?.length) return null;
  return (
    <div>
      <div style={{ fontSize: font.small, fontWeight: font.weight.bold, color: color.textMuted, marginBottom: 4 }}>
        Coverage: subjects they can speak about
      </div>
      <ul aria-live="polite" style={{ listStyle: "none", margin: 0, padding: 0, display: "flex", gap: 6, flexWrap: "wrap" }}>
        {coverage.map((c) => (
          <li
            key={c.subject_id}
            title={c.covered ? `${c.questions} questions` : `Only ${c.questions}: below the coverage floor`}
            style={{
              fontSize: font.small,
              padding: "2px 8px",
              borderRadius: radius.pill,
              border: `1px solid ${c.covered ? "#A7F3D0" : "#FED7AA"}`,
              background: c.covered ? "#E8FFF3" : "#FFF7ED",
              color: c.covered ? "#065F46" : "#92400E",
            }}
          >
            {c.covered ? "✓" : "!"} {c.label} · {c.questions}
          </li>
        ))}
      </ul>
    </div>
  );
}

function ApproveBar({ ui, set, busy, onApprove, onReopen }) {
  const { Button } = ui;
  const [overriding, setOverriding] = useState(false);
  const [reason, setReason] = useState("");
  const gaps = set.coverage_gaps || [];
  const pending = set.counts?.pending_new || 0;

  if (set.status === "locked") {
    return (
      <Notice tone="info">
        {`Locked ${formatDateTime(set.locked_at)}: the participant has started, so this set can't change.`}
      </Notice>
    );
  }
  if (set.status === "approved") {
    return (
      <div style={{ display: "grid", gap: space.sm }}>
        <Notice tone="success">
          {`Approved by ${set.approved_by} on ${formatDateTime(set.approved_at)}.${set.override_reason ? ` Approved despite gaps: ${set.override_reason}` : ""} It's read-only until reopened; reopening is possible until the participant opens it.`}
        </Notice>
        <div style={{ display: "flex", gap: space.sm, flexWrap: "wrap", alignItems: "center" }}>
          <input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Why reopen? (required)" aria-label="Reason for reopening" style={inputCss({ flex: "1 1 260px", width: "auto" })} />
          <Button variant="secondary" disabled={busy || !reason.trim()} onClick={() => onReopen(reason)}>
            Reopen for changes
          </Button>
        </div>
      </div>
    );
  }
  const blockers = [...gaps.map((g) => g.message), ...(pending ? [`${plural(pending, "AI-proposed question")} awaiting a decision (left out unless accepted).`] : [])];
  return (
    <div style={{ display: "grid", gap: space.sm }}>
      {gaps.length ? (
        <div style={{ fontSize: 13 }}>
          <strong>Approval needs attention:</strong>
          <ul style={{ margin: "4px 0 0", paddingLeft: 18 }}>
            {blockers.map((b) => (
              <li key={b}>{b}</li>
            ))}
          </ul>
        </div>
      ) : pending ? (
        <div style={{ fontSize: 13, color: color.textMuted }}>{blockers[0]}</div>
      ) : null}
      <div style={{ display: "flex", gap: space.sm, flexWrap: "wrap", alignItems: "center" }}>
        <Button disabled={busy || gaps.length > 0} title={gaps.length ? "Fill the coverage gaps, or approve anyway with a reason" : "Approve this set"} onClick={() => onApprove(null)}>
          Approve set
        </Button>
        {gaps.length ? (
          overriding ? (
            <>
              <input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Reason for approving with gaps" aria-label="Reason for approving with gaps" style={inputCss({ flex: "1 1 260px", width: "auto" })} />
              <Button disabled={busy || !reason.trim()} onClick={() => onApprove(reason)}>
                Approve anyway
              </Button>
            </>
          ) : (
            <Button variant="secondary" onClick={() => setOverriding(true)}>
              Approve with gaps…
            </Button>
          )
        ) : null}
      </div>
    </div>
  );
}

function ParticipantPicker({ evalId, current }) {
  const navigate = useNavigate();
  const [rows, setRows] = useState([]);
  useEffect(() => {
    let alive = true;
    questionBankApi.review(evalId).then((r) => alive && setRows(r.participants.filter((p) => p.status !== "not_assembled"))).catch(() => {});
    return () => {
      alive = false;
    };
  }, [evalId]);
  return (
    <label style={{ display: "flex", gap: space.sm, alignItems: "center", fontSize: 13, flexWrap: "wrap" }}>
      Participant
      <select value={current || ""} onChange={(e) => navigate(`/consultant/review/participants/${e.target.value}`)} style={inputCss({ width: "auto", minWidth: 0, maxWidth: "100%" })}>
        <option value="" disabled>
          Choose a participant…
        </option>
        {rows.map((r) => (
          <option key={r.participant_id} value={r.participant_id}>
            {r.display_code ? `${r.display_code} · ` : ""}
            {r.label} ({SET_STATUS[r.status].label.toLowerCase()})
          </option>
        ))}
      </select>
    </label>
  );
}

/** One participant's set: header with live coverage, questions by section, add, approve or reopen. */
export default function ParticipantReview({ ui, evalId }) {
  const { participantId } = useParams();
  const { Badge } = ui;
  const [loaded, setLoaded] = useState(null);
  const [expandGrid, setExpandGrid] = useState(false);
  const [focusId, setFocusId] = useState(null);
  const [adding, setAdding] = useState(false);
  const { busy, error, setError, run } = useAsync();
  const metaAsync = useAsync();
  const meta = useBankMeta(metaAsync.run);
  const refs = useRef({});
  const wide = useWideScreen();

  const load = useCallback(async () => {
    if (!participantId) return;
    setLoaded(await questionBankApi.reviewSet(evalId, participantId));
  }, [evalId, participantId]);
  useEffect(() => {
    run(load);
  }, [load, run]);
  // Another participant's set stays out of view while this one loads
  const data = loaded && loaded.participant_id === participantId ? loaded : null;

  const editable = data?.set?.status === "draft";
  const aiOn = !!data?.set?.summary?.ai?.enabled;
  const all = useMemo(() => (data?.sections || []).flatMap((s) => s.questions), [data]);
  const codeById = useMemo(() => Object.fromEntries(all.map((q) => [q.id, q.bank_item_code || "the previous question"])), [all]);
  // The questions the keyboard moves through, in screen order
  const order = useMemo(() => all.filter((q) => expandGrid || !isGrid(q)).map((q) => q.id), [all, expandGrid]);

  const act = (q, kind, body) =>
    new Promise((resolve) => {
      run(async () => {
        await ACTIONS[kind](evalId, q, body || {});
        await load();
        resolve();
      });
    });
  const actMany = (qs, kind) =>
    run(async () => {
      for (const q of qs) await ACTIONS[kind](evalId, q, {});
      await load();
    });

  const onKeyDown = (e) => {
    if (["INPUT", "TEXTAREA", "SELECT"].includes(e.target.tagName) || e.metaKey || e.ctrlKey || e.altKey) return;
    const i = order.indexOf(focusId);
    const go = (n) => {
      const id = order[Math.max(0, Math.min(order.length - 1, n))];
      if (id) refs.current[id]?.focus();
    };
    const q = all.find((x) => x.id === focusId);
    if (e.key === "j") go(i + 1);
    else if (e.key === "k") go(i < 0 ? 0 : i - 1);
    else if (!editable || !q) return;
    else if (e.key === "a" && isPendingNew(q)) act(q, "acceptNew");
    else if (e.key === "a" && hasOpenWording(q)) act(q, "wording", { use: "ai" });
    else if (e.key === "r" && isPendingNew(q)) act(q, "rejectNew");
    else if (e.key === "r" && (hasOpenWording(q) || (q.ai_text && q.text_source === "ai_tailored"))) act(q, "wording", { use: "bank" });
    else return;
    e.preventDefault();
  };

  if (!participantId) {
    return (
      <div style={{ display: "grid", gap: space.md }}>
        <ParticipantPicker evalId={evalId} />
        <p style={{ margin: 0, color: color.textMuted }}>
          Choose a participant, or open one from the <Link to="/consultant/review">overview</Link>.
        </p>
      </div>
    );
  }

  const set = data?.set;
  const header = data?.header;
  const st = set ? SET_STATUS[set.status] : null;

  return (
    <div onKeyDown={onKeyDown} style={{ display: "grid", gap: space.lg, gridTemplateColumns: "minmax(0, 1fr)" }}>
      <ParticipantPicker evalId={evalId} current={participantId} />
      {error ? (
        <div role="alert">
          <Notice tone="error">{error}</Notice>
        </div>
      ) : null}
      {!data ? (
        <p style={{ color: color.textMuted }}>Loading…</p>
      ) : !set ? (
        <Notice tone="info">No assembled set for this participant yet. Assemble drafts from the overview.</Notice>
      ) : (
        <>
          <Panel>
            <div style={{ display: "grid", gap: space.md }}>
              <div style={{ display: "flex", gap: space.sm, flexWrap: "wrap", alignItems: "center", justifyContent: "space-between" }}>
                <div>
                  <h2 style={{ margin: 0, fontSize: font.heading }}>
                    {header.display_code ? `${header.display_code} · ` : ""}
                    {data.label}
                  </h2>
                  <div style={{ fontSize: 13, color: color.textMuted }}>
                    {header.role_label}
                    {header.committees.length
                      ? ` · ${header.committees.map((c) => (c.role === "chair" ? `${c.name} (chair)` : c.name)).join(", ")}`
                      : ""}
                  </div>
                </div>
                <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                  <Badge tone={st.tone}>{st.label}</Badge>
                  <Badge tone="blue">{plural(set.counts.questions, "question")}</Badge>
                  <Badge tone={set.estimated_minutes > 45 ? "amber" : "blue"}>{`~${set.estimated_minutes} min`}</Badge>
                  {set.counts.removed ? <Badge tone="gray">{`${set.counts.removed} removed`}</Badge> : null}
                  {set.counts.open_wording + set.counts.pending_new ? (
                    <Badge tone="purple">{`${set.counts.open_wording + set.counts.pending_new} AI decisions open`}</Badge>
                  ) : null}
                </div>
              </div>
              <CoverageStrip coverage={set.coverage} />
              {data.rater_warnings
                .filter((w) => (w.participant_ids || []).includes(participantId))
                .map((w) => (
                  <Notice key={`${w.set}-${w.subject_id}`} tone="warn">
                    {w.message}
                  </Notice>
                ))}
              {editable ? (
                <p style={{ margin: 0, fontSize: font.small, color: color.textMuted }}>
                  Keyboard: click a question, then <kbd>j</kbd> / <kbd>k</kbd> for next and previous, <kbd>a</kbd> to use a suggestion or accept a proposed question, <kbd>r</kbd> to go back to the bank wording or reject a proposed question.
                </p>
              ) : null}
            </div>
          </Panel>

          {data.sections.map((sec) => {
            const grid = sec.key === "colleagues" && !expandGrid ? sec.questions.filter(isGrid) : [];
            const rows = sec.questions.filter((q) => !grid.includes(q));
            return (
              <section key={sec.key} aria-labelledby={`sec-${sec.key}`}>
                <SectionTitle hint={SECTION_HINTS[sec.key]}>
                  <span id={`sec-${sec.key}`}>
                    {sec.label} <span style={{ fontWeight: font.weight.regular, color: color.textMuted }}>· {sec.questions.filter((q) => q.status !== "removed").length}</span>
                  </span>
                </SectionTitle>
                <ul style={{ margin: 0, padding: 0, display: "grid", gap: space.sm, gridTemplateColumns: "minmax(0, 1fr)" }}>
                  {grid.length ? <PeerGrid ui={ui} questions={grid} editable={editable} onActMany={actMany} onExpand={() => setExpandGrid(true)} /> : null}
                  {rows.map((q, n) => (
                    <QuestionCard
                      key={q.id}
                      ref={(el) => {
                        refs.current[q.id] = el;
                      }}
                      ui={ui}
                      q={q}
                      meta={meta}
                      subjects={data.subject_options}
                      editable={editable && !busy}
                      aiOn={aiOn}
                      focused={focusId === q.id}
                      onFocus={() => setFocusId(q.id)}
                      onAct={(kind, body) => act(q, kind, body)}
                      first={n === 0 && !grid.length}
                      last={n === rows.length - 1}
                      followsCode={q.depends_on_question_id ? codeById[q.depends_on_question_id] : null}
                    />
                  ))}
                </ul>
                {sec.key === "colleagues" && expandGrid ? (
                  <button type="button" onClick={() => setExpandGrid(false)} style={{ marginTop: space.sm, border: 0, background: "none", color: color.primaryText, cursor: "pointer", fontWeight: font.weight.bold }}>
                    Show the colleague statements as one grid
                  </button>
                ) : null}
              </section>
            );
          })}

          {editable ? (
            <Panel>
              {adding ? (
                <>
                  <SectionTitle hint="From the approved bank (placeholders filled for the subject you pick), or your own with its tags.">Add a question</SectionTitle>
                  <AddQuestion
                    ui={ui}
                    evalId={evalId}
                    participantId={participantId}
                    subjects={data.subject_options}
                    meta={meta}
                    existing={new Set(all.filter((q) => q.bank_item_code && q.subject).map((q) => `${q.bank_item_code}|${q.subject.id}`))}
                    onAdded={async () => {
                      await load();
                      setAdding(false);
                    }}
                  />
                </>
              ) : (
                <ui.Button variant="secondary" onClick={() => setAdding(true)}>
                  Add a question
                </ui.Button>
              )}
            </Panel>
          ) : null}

          <div style={{ position: wide ? "sticky" : "static", bottom: 0, zIndex: 1, background: color.surface, border: `1px solid ${color.border}`, borderRadius: radius.md, padding: space.md, boxShadow: "0 -4px 12px rgba(15,23,42,0.06)" }}>
            <ApproveBar
              ui={ui}
              set={set}
              busy={busy}
              onApprove={(reason) =>
                run(async () => {
                  setError("");
                  await questionBankApi.approveSet(evalId, participantId, reason);
                  await load();
                })
              }
              onReopen={(reason) =>
                run(async () => {
                  await questionBankApi.reopenSet(evalId, participantId, reason);
                  await load();
                })
              }
            />
          </div>

          {data.history?.length ? (
            <details>
              <summary style={{ cursor: "pointer", fontWeight: font.weight.bold }}>Change history ({data.history.length})</summary>
              <ul style={{ margin: `${space.sm}px 0 0`, paddingLeft: 18, fontSize: 13, display: "grid", gap: 2 }}>
                {data.history.map((e) => (
                  <li key={e.id}>
                    {formatDateTime(e.at)}: <strong>{e.by}</strong> {eventLabel(e)}
                    {e.detail?.reason ? ` (${e.detail.reason})` : ""}
                    {e.detail?.override_reason ? ` (despite gaps: ${e.detail.override_reason})` : ""}
                  </li>
                ))}
              </ul>
            </details>
          ) : null}
        </>
      )}
    </div>
  );
}
