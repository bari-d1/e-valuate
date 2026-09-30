/**
 * src/pages/member/MemberSubmitPage.jsx
 * ------------------------------------
 * Board Member: Submit answers to backend (token-based).
 *
 * Lock:
 * - If assignment.status === "responded", block re-submission.
 */

import React, { useMemo, useState } from "react";
import { useNavigate, useParams, Link } from "react-router-dom";
import { portalSubmitResponses, portalLoad } from "../../api/portalApi.js";
import { MemberUI as ui } from "./memberUi.jsx";

function storageKey(token) {
  return `cw_portal_answers:${token}`;
}

function loadDraft(token) {
  try {
    const raw = sessionStorage.getItem(storageKey(token));
    return raw ? JSON.parse(raw) : {};
  } catch {
    return {};
  }
}

function clearDraft(token) {
  try {
    sessionStorage.removeItem(storageKey(token));
  } catch {
    // ignore
  }
}

/**
 * Convert { [qid]: {score, comment} } -> [{question_id, score, comment}]
 * @param {Record<string, any>} answers
 */
function toAnswerList(answers) {
  const out = [];
  const a = answers || {};
  for (const qid of Object.keys(a)) {
    const row = a[qid] || {};
    const hasScore = typeof row.score === "number";
    const hasComment = typeof row.comment === "string" && row.comment.trim();
    if (!hasScore && !hasComment) continue;
    out.push({
      question_id: qid,
      score: hasScore ? row.score : null,
      comment: hasComment ? row.comment : null,
    });
  }
  return out;
}

export default function MemberSubmitPage() {
  const nav = useNavigate();
  const { token } = useParams();

  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [okMsg, setOkMsg] = useState("");
  const [locked, setLocked] = useState(false);

  const draft = useMemo(() => loadDraft(token), [token]);
  const answersList = useMemo(() => toAnswerList(draft), [draft]);

  const canSubmit = answersList.length > 0;

  const submitNow = async () => {
    setBusy(true);
    setErr("");
    setOkMsg("");
    try {
      // Sanity check token still valid + get assignment status
      const p = await portalLoad(token);
      const assignmentStatus = String(p?.assignment?.status || "").toLowerCase();

      // ✅ LOCK: already responded
      if (assignmentStatus === "responded") {
        setLocked(true);
        setOkMsg("This evaluation has already been completed. You can view your submission summary.");
        nav(`/member/${token}/thank-you`, { replace: true });
        return;
      }

      const res = await portalSubmitResponses(token, answersList, true);

      clearDraft(token);
      setOkMsg(`Submitted. Created: ${res.created}, Updated: ${res.updated}, Finalized: ${res.finalized}`);
      nav(`/member/${token}/thank-you`);
    } catch (e) {
      setErr(String(e?.message || e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div style={ui.pageShellStyle()}>
      <ui.Card
        title="Submit"
        subtitle="Review and submit your answers. Once submitted, your status is marked as responded."
        right={<ui.Badge tone="blue">Board Member</ui.Badge>}
      >
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
          <ui.Badge tone="gray">Token: {(token || "").slice(0, 10)}…</ui.Badge>
          <ui.Badge tone={canSubmit ? "green" : "amber"}>Answers ready: {answersList.length}</ui.Badge>
        </div>

        {err ? (
          <div style={{ marginTop: 12 }}>
            <ui.Badge tone="red">Error</ui.Badge>
            <div style={{ marginTop: 8, color: "#991B1B", fontFamily: "monospace", fontSize: 12 }}>{err}</div>
          </div>
        ) : null}

        {okMsg ? (
          <div style={{ marginTop: 12 }}>
            <ui.Badge tone={locked ? "amber" : "green"}>{locked ? "Completed" : "OK"}</ui.Badge>
            <div style={{ marginTop: 8, color: locked ? "#92400E" : "#065F46", fontFamily: "monospace", fontSize: 12 }}>
              {okMsg}
            </div>
          </div>
        ) : null}

        <div style={{ marginTop: 14, display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
          <ui.Button
            variant="primary"
            disabled={busy || locked || !canSubmit}
            onClick={submitNow}
            title={locked ? "Already completed" : !canSubmit ? "Answer at least one question first" : "Submit answers"}
          >
            {busy ? "Submitting..." : locked ? "Already submitted" : "Submit →"}
          </ui.Button>

          <Link to={`/member/${token}/questions`} style={{ alignSelf: "center", fontWeight: 900, color: "#0F172A" }}>
            Back to questions →
          </Link>

          <Link to={`/member/${token}/evaluation`} style={{ alignSelf: "center", fontWeight: 900, color: "#0F172A" }}>
            View evaluation →
          </Link>

          <Link to={`/member/${token}/thank-you`} style={{ alignSelf: "center", fontWeight: 900, color: "#0F172A" }}>
            View submission summary →
          </Link>
        </div>

        {!canSubmit ? (
          <div style={{ marginTop: 12 }}>
            <ui.Badge tone="amber">No answers found in this browser tab yet.</ui.Badge>
          </div>
        ) : null}
      </ui.Card>
    </div>
  );
}
