/**
 * src/pages/member/MemberQuestionsPage.jsx
 * -----------------------------------------
 * Board Member Portal — Questions (Assignment-based)
 *
 * OPTION B (Lock portal once responded):
 * - If assignment.status === "responded", block answering UI
 * - Show message: "You’ve already completed this evaluation."
 *
 * Still includes backend-hydration fix:
 * - If local draft is empty, hydrate answers from backend responses
 *
 * Notes:
 * - Backend payload shape:
 *   { assignment, respondent, subject, evaluation, questions }
 */

import React, { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams, Link } from "react-router-dom";
import { portalLoad, portalGetResponses } from "../../api/portalApi.js";
import { getHubTokenMisroute, redirectToHubFromMisroute } from "../../api/memberPortalErrors.js";
import { MemberUI as ui } from "./memberUi.jsx";

/** Build the per-token storage key for draft answers. */
function storageKey(token) {
  return `cw_portal_answers:${token}`;
}

/** Load draft answers from sessionStorage (safe). */
function loadDraft(token) {
  try {
    const raw = sessionStorage.getItem(storageKey(token));
    return raw ? JSON.parse(raw) : {};
  } catch {
    return {};
  }
}

/** Save draft answers to sessionStorage (safe). */
function saveDraft(token, obj) {
  try {
    sessionStorage.setItem(storageKey(token), JSON.stringify(obj || {}));
  } catch {
    // ignore storage failures
  }
}

/**
 * Convert backend response items -> draft shape:
 * [{question_id, score, comment}] => { [qid]: {score, comment} }
 */
function responsesToDraft(items) {
  const out = {};
  const arr = Array.isArray(items) ? items : [];
  for (const it of arr) {
    const qid = String(it?.question_id || "").trim();
    if (!qid) continue;

    const hasScore = typeof it?.score === "number";
    out[qid] = {
      score: hasScore ? it.score : null,
      comment: typeof it?.comment === "string" ? it.comment : null,
    };
  }
  return out;
}

/** Count an answer as "answered" depending on the answer_type. */
function isAnswered(answerType, a) {
  const at = String(answerType || "").toLowerCase();
  if (!a) return false;

  if (at === "rating" || at === "yesno") {
    return typeof a.score === "number";
  }

  return typeof a.comment === "string" && a.comment.trim().length > 0;
}

/** Simple progress bar style helper. */
function progressBarStyle() {
  return {
    height: 10,
    borderRadius: 999,
    background: "#EEF2FF",
    overflow: "hidden",
    border: "1px solid #E5E7EB",
    position: "relative",
    boxShadow: "inset 0 1px 0 rgba(255,255,255,0.65)",
    marginTop: 8,
  };
}

function progressFillStyle(pct) {
  const clamped = Math.max(0, Math.min(100, pct));
  return {
    width: `${clamped}%`,
    height: "100%",
    borderRadius: 999,
    background: "linear-gradient(90deg, #2563EB, #7C3AED)",
  };
}

/**
 * Minimal modal component (no dependencies).
 */
function ConfirmModal({ open, title, message, confirmLabel, onConfirm, onClose }) {
  if (!open) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 1000,
        background: "rgba(15, 23, 42, 0.55)",
        display: "grid",
        placeItems: "center",
        padding: 14,
      }}
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose?.();
      }}
    >
      <div
        style={{
          width: "min(560px, 100%)",
          background: "#FFFFFF",
          borderRadius: 18,
          border: "1px solid #E5E7EB",
          boxShadow: "0 20px 60px rgba(15, 23, 42, 0.25)",
          padding: 14,
        }}
      >
        <div style={{ fontWeight: 950, color: "#0F172A", fontSize: 16 }}>{title}</div>
        <div style={{ marginTop: 8, color: "#475569", fontSize: 13, lineHeight: 1.45 }}>{message}</div>

        <div style={{ marginTop: 14, display: "flex", gap: 10, justifyContent: "flex-end", flexWrap: "wrap" }}>
          <button
            onClick={onClose}
            style={{
              padding: "10px 12px",
              borderRadius: 12,
              border: "1px solid #E5E7EB",
              background: "#FFFFFF",
              fontWeight: 900,
              cursor: "pointer",
            }}
          >
            Go back
          </button>

          <button
            onClick={onConfirm}
            style={{
              padding: "10px 12px",
              borderRadius: 12,
              border: "1px solid #1D4ED8",
              background: "#2563EB",
              color: "white",
              fontWeight: 900,
              cursor: "pointer",
            }}
          >
            {confirmLabel || "Continue"}
          </button>
        </div>
      </div>
    </div>
  );
}

export default function MemberQuestionsPage() {
  const nav = useNavigate();
  const { token } = useParams();

  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [payload, setPayload] = useState(null);

  // answers shape: { [question_id]: { score?: number|null, comment?: string|null } }
  const [answers, setAnswers] = useState(() => loadDraft(token));

  // confirm modal
  const [confirmOpen, setConfirmOpen] = useState(false);

  // keep answers keyed per token
  useEffect(() => {
    setAnswers(loadDraft(token));
  }, [token]);

  // load portal payload + hydrate answers from backend if local draft is empty
  useEffect(() => {
    let alive = true;

    async function run() {
      setBusy(true);
      setErr("");
      try {
        const data = await portalLoad(token);
        if (!alive) return;
        setPayload(data);

        // If there's no draft, hydrate from backend saved responses
        const currentDraft = loadDraft(token);
        const hasAnyDraft = currentDraft && Object.keys(currentDraft).length > 0;

        if (!hasAnyDraft) {
          const resp = await portalGetResponses(token);
          if (!alive) return;
          const hydrated = responsesToDraft(resp?.items);
          setAnswers(hydrated);
        }
      } catch (e) {
        if (!alive) return;
        const misroute = getHubTokenMisroute(e);
        if (misroute && redirectToHubFromMisroute(nav, token, misroute)) {
          return;
        }
        setErr(String(e?.message || e));
      } finally {
        if (alive) setBusy(false);
      }
    }

    if (token) run();

    return () => {
      alive = false;
    };
  }, [token]);

  // persist draft answers (won't matter when locked, but safe to keep)
  useEffect(() => {
    if (!token) return;
    saveDraft(token, answers);
  }, [token, answers]);

  const questions = payload?.questions || [];

  const byDimension = useMemo(() => {
    const m = new Map();
    for (const q of questions) {
      const d = q.dimension || "General";
      if (!m.has(d)) m.set(d, []);
      m.get(d).push(q);
    }
    return Array.from(m.entries());
  }, [questions]);

  const answeredCount = useMemo(() => {
    return questions.filter((q) => isAnswered(q.answer_type, answers?.[q.question_id])).length;
  }, [questions, answers]);

  const totalCount = questions.length;
  const remaining = Math.max(0, totalCount - answeredCount);
  const progressPct = totalCount ? Math.round((answeredCount / totalCount) * 100) : 0;

  const allAnswered = totalCount > 0 && remaining === 0;

  const setAnswer = (qid, patch) => {
    setAnswers((prev) => {
      const next = { ...(prev || {}) };
      next[qid] = { ...(next[qid] || {}), ...patch };
      return next;
    });
  };

  const clearAll = () => {
    setAnswers({});
    try {
      sessionStorage.removeItem(storageKey(token));
    } catch {}
  };

  // --- payload fields ---
  const evalId = payload?.evaluation?.evaluation_id;
  const tenant = payload?.evaluation?.tenant_name;
  const instrument = payload?.evaluation?.instrument;

  const assignment = payload?.assignment;
  const assignmentType = assignment?.assignment_type;
  const assignmentStatus = String(assignment?.status || "").toLowerCase();

  const respondent = payload?.respondent;
  const subject = payload?.subject;

  // ✅ LOCK: once responded
  const isLocked = assignmentStatus === "responded";

  /** Navigate to submit with guard. */
  const goSubmit = (force = false) => {
    if (!payload || busy) return;
    if (isLocked) return; // locked means no more submit from here

    if (allAnswered || force) {
      nav(`/member/${token}/submit`);
      return;
    }

    setConfirmOpen(true);
  };

  return (
    <div style={ui.pageShellStyle()}>
      <ui.Card
        title="Questions"
        subtitle="Please answer the questions below. Your progress is saved in this browser tab."
        right={<ui.Badge tone="blue">Board Member</ui.Badge>}
      >
        {/* Top status row */}
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
          {busy ? <ui.Badge tone="gray">Loading…</ui.Badge> : null}

          {payload ? (
            <>
              <ui.Badge tone="gray">Evaluation: {evalId || "—"}</ui.Badge>
              <ui.Badge tone="gray">Tenant: {tenant || "—"}</ui.Badge>

              <ui.Badge tone="gray">Assignment: {assignmentType || "—"}</ui.Badge>
              <ui.Badge tone={assignmentStatus === "responded" ? "green" : "amber"}>
                Status: {assignment?.status || "—"}
              </ui.Badge>

              {respondent?.full_name || respondent?.email ? (
                <ui.Badge tone="gray">Respondent: {respondent?.full_name || respondent?.email}</ui.Badge>
              ) : null}

              {subject?.full_name || subject?.email ? (
                <ui.Badge tone="gray">Subject: {subject?.full_name || subject?.email}</ui.Badge>
              ) : null}

              <ui.Badge tone="gray">
                Questionnaire: {instrument?.template_code || "—"} v{instrument?.version ?? "—"}
              </ui.Badge>

              <ui.Badge tone={remaining === 0 ? "green" : "amber"}>
                Progress: {answeredCount}/{totalCount}
              </ui.Badge>
            </>
          ) : (
            <ui.Badge tone="gray">Token: {token ? `${String(token).slice(0, 8)}…` : "—"}</ui.Badge>
          )}
        </div>

        {/* Error block */}
        {err ? (
          <div style={{ marginTop: 12, padding: 12, borderRadius: 14, border: "1px solid #FECACA", background: "#FEF2F2" }}>
            <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
              <ui.Badge tone="red">Error</ui.Badge>
              <div style={{ fontWeight: 900, color: "#991B1B" }}>Could not load questions.</div>
            </div>
            <div style={{ marginTop: 8, color: "#991B1B", fontFamily: "monospace", fontSize: 12 }}>{err}</div>
            <div style={{ marginTop: 10 }}>
              <Link to="/member/invite" style={{ fontWeight: 900, color: "#0F172A" }}>
                Use another invite →
              </Link>
            </div>
          </div>
        ) : null}

        {/* ✅ LOCKED STATE UI */}
        {!busy && payload && isLocked ? (
          <div
            style={{
              marginTop: 14,
              padding: 14,
              borderRadius: 16,
              border: "1px solid #E5E7EB",
              background: "#F8FAFC",
              boxShadow: "0 6px 18px rgba(15, 23, 42, 0.06)",
            }}
          >
            <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
              <ui.Badge tone="green">Completed</ui.Badge>
              <div style={{ fontWeight: 950, color: "#0F172A" }}>You’ve already completed this evaluation.</div>
            </div>

            <div style={{ marginTop: 8, color: "#475569", fontSize: 13, lineHeight: 1.45 }}>
              Your submission has been recorded. If you need to review your submission summary, open the Thank-you page.
            </div>

            <div style={{ marginTop: 12, display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
              <ui.Button variant="primary" onClick={() => nav(`/member/${token}/thank-you`)}>
                View submission summary →
              </ui.Button>

              <ui.Button variant="secondary" onClick={() => nav(`/member/${token}/evaluation`)}>
                View evaluation →
              </ui.Button>

              <Link to="/member/invite" style={{ alignSelf: "center", fontWeight: 900, color: "#0F172A" }}>
                Use another invite →
              </Link>
            </div>
          </div>
        ) : null}

        {/* NORMAL (UNLOCKED) FLOW */}
        {!busy && payload && !isLocked ? (
          <>
            {/* Progress bar */}
            <div style={{ marginTop: 10 }}>
              <div style={{ display: "flex", justifyContent: "space-between", gap: 10, flexWrap: "wrap" }}>
                <div style={{ fontSize: 12, fontWeight: 900, color: "#0F172A" }}>{progressPct}% complete</div>
                <div style={{ fontSize: 12, color: "#64748B" }}>
                  Tip: You can leave and come back — drafts stay in this browser.
                </div>
              </div>
              <div style={progressBarStyle()}>
                <div style={progressFillStyle(progressPct)} />
              </div>
            </div>

            {/* Sticky action bar */}
            <div
              style={{
                marginTop: 14,
                position: "sticky",
                top: 10,
                zIndex: 5,
                background: "rgba(255,255,255,0.92)",
                backdropFilter: "blur(8px)",
                border: "1px solid #E5E7EB",
                borderRadius: 16,
                padding: 12,
                boxShadow: "0 6px 18px rgba(15, 23, 42, 0.06)",
                display: "flex",
                gap: 10,
                flexWrap: "wrap",
                alignItems: "center",
                justifyContent: "space-between",
              }}
            >
              <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
                <ui.Button
                  variant="primary"
                  disabled={busy || !payload || totalCount === 0 || !allAnswered}
                  onClick={() => goSubmit(false)}
                  title={
                    !payload
                      ? "Load questions first"
                      : totalCount === 0
                      ? "No questions available"
                      : allAnswered
                      ? "Continue to submit"
                      : `Answer all questions to continue (${remaining} remaining)`
                  }
                >
                  Continue → Submit
                </ui.Button>

                {!allAnswered && payload && totalCount > 0 ? (
                  <ui.Button
                    variant="secondary"
                    disabled={busy}
                    onClick={() => setConfirmOpen(true)}
                    title={`Continue anyway (you have ${remaining} unanswered)`}
                  >
                    Continue anyway…
                  </ui.Button>
                ) : null}

                <ui.Button variant="soft" disabled={busy} onClick={clearAll} title="Clear saved draft answers for this token">
                  Clear Draft
                </ui.Button>

                <Link to={`/member/${token}/evaluation`} style={{ alignSelf: "center", fontWeight: 900, color: "#0F172A" }}>
                  View evaluation →
                </Link>
              </div>

              <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
                <ui.Badge tone={allAnswered ? "green" : "amber"}>{allAnswered ? "Ready to submit" : `${remaining} unanswered`}</ui.Badge>
              </div>
            </div>

            {/* Questions */}
            <div style={{ marginTop: 16, display: "grid", gap: 14 }}>
              {byDimension.map(([dim, qs]) => (
                <div
                  key={dim}
                  style={{
                    border: "1px solid #E5E7EB",
                    borderRadius: 18,
                    padding: 14,
                    background: "#FFFFFF",
                    boxShadow: "0 6px 20px rgba(15, 23, 42, 0.05)",
                  }}
                >
                  <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 10, flexWrap: "wrap" }}>
                    <div>
                      <div style={{ fontSize: 14, fontWeight: 950, color: "#0F172A" }}>{dim}</div>
                      <div style={{ marginTop: 3, fontSize: 12, color: "#64748B" }}>
                        Answer honestly — this improves the accuracy of the board evaluation report.
                      </div>
                    </div>

                    <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
                      <ui.Badge tone="gray">{qs.length} questions</ui.Badge>
                      <ui.Badge tone="gray">
                        Answered: {qs.filter((q) => isAnswered(q.answer_type, answers?.[q.question_id])).length}/{qs.length}
                      </ui.Badge>
                    </div>
                  </div>

                  <div style={{ marginTop: 12, display: "grid", gap: 12 }}>
                    {qs.map((q, idx) => {
                      const qid = q.question_id;
                      const a = answers?.[qid] || {};
                      const at = String(q.answer_type || "").toLowerCase();
                      const answered = isAnswered(at, a);

                      return (
                        <div
                          key={qid}
                          style={{
                            border: "1px solid #E5E7EB",
                            borderRadius: 16,
                            padding: 12,
                            background: answered ? "#F8FAFF" : "#FFFFFF",
                          }}
                        >
                          <div style={{ display: "flex", justifyContent: "space-between", gap: 10, flexWrap: "wrap" }}>
                            <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
                              <div
                                style={{
                                  width: 28,
                                  height: 28,
                                  borderRadius: 10,
                                  display: "grid",
                                  placeItems: "center",
                                  fontWeight: 950,
                                  color: "#0F172A",
                                  background: "#EEF2FF",
                                  border: "1px solid #E5E7EB",
                                }}
                              >
                                {idx + 1}
                              </div>

                              <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
                                <ui.Badge tone="purple">{at || "unknown"}</ui.Badge>
                                <ui.Badge tone="gray">Weight: {q.weight ?? 1}</ui.Badge>
                                {answered ? <ui.Badge tone="green">✓ Answered</ui.Badge> : <ui.Badge tone="amber">Pending</ui.Badge>}
                              </div>
                            </div>
                          </div>

                          <div style={{ marginTop: 10, fontWeight: 900, color: "#0F172A", lineHeight: 1.35 }}>{q.text}</div>

                          <div style={{ marginTop: 10 }}>
                            {at === "rating" ? (
                              <ui.Field label="Rating (1–5)">
                                <select
                                  value={typeof a.score === "number" ? String(a.score) : ""}
                                  onChange={(e) => setAnswer(qid, { score: e.target.value ? Number(e.target.value) : null })}
                                  style={ui.inputStyle()}
                                >
                                  <option value="">Select…</option>
                                  {[1, 2, 3, 4, 5].map((n) => (
                                    <option key={n} value={String(n)}>
                                      {n}
                                    </option>
                                  ))}
                                </select>
                              </ui.Field>
                            ) : at === "yesno" ? (
                              <ui.Field label="Yes / No">
                                <select
                                  value={typeof a.score === "number" ? String(a.score) : ""}
                                  onChange={(e) => setAnswer(qid, { score: e.target.value ? Number(e.target.value) : null })}
                                  style={ui.inputStyle()}
                                >
                                  <option value="">Select…</option>
                                  <option value="1">Yes</option>
                                  <option value="0">No</option>
                                </select>
                              </ui.Field>
                            ) : (
                              <ui.Field label="Comment">
                                <textarea
                                  value={a.comment || ""}
                                  onChange={(e) => setAnswer(qid, { comment: e.target.value })}
                                  style={ui.textareaStyle(120)}
                                  spellCheck={false}
                                  placeholder="Type your comment…"
                                />
                              </ui.Field>
                            )}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              ))}

              {!busy && payload && questions.length === 0 ? (
                <div style={{ padding: 12, borderRadius: 16, border: "1px solid #FED7AA", background: "#FFF7ED" }}>
                  <ui.Badge tone="amber">No active questions found for this assignment.</ui.Badge>
                </div>
              ) : null}
            </div>

            {/* Confirm modal */}
            <ConfirmModal
              open={confirmOpen}
              title="Some questions are unanswered"
              message={`You still have ${remaining} unanswered question(s). You can go back to complete them, or continue to Submit anyway.`}
              confirmLabel="Continue to Submit"
              onClose={() => setConfirmOpen(false)}
              onConfirm={() => {
                setConfirmOpen(false);
                nav(`/member/${token}/submit`);
              }}
            />
          </>
        ) : null}
      </ui.Card>
    </div>
  );
}
