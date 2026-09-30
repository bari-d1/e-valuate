/**
 * src/pages/member/MemberEvaluationPage.jsx
 * ----------------------------------------
 * Board Member: View evaluation context via token.
 *
 * Lock UX:
 * - If assignment.status === "responded", hide Start Answering and offer Summary link.
 */

import React, { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams, Link } from "react-router-dom";
import { portalLoad } from "../../api/portalApi.js";
import { getHubTokenMisroute, redirectToHubFromMisroute } from "../../api/memberPortalErrors.js";
import { MemberUI as ui } from "./memberUi.jsx";

export default function MemberEvaluationPage() {
  const nav = useNavigate();
  const { token } = useParams();

  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [payload, setPayload] = useState(null);

  useEffect(() => {
    let alive = true;

    async function run() {
      setBusy(true);
      setErr("");
      try {
        const data = await portalLoad(token);
        if (!alive) return;
        setPayload(data);
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

  const ev = payload?.evaluation || null;
  const respondent = payload?.respondent || null;
  const assignment = payload?.assignment || null;

  const statusText = String(assignment?.status || respondent?.status || "").trim();
  const statusLower = statusText.toLowerCase();
  const isResponded = statusLower === "responded";

  const statusTone = useMemo(() => {
    const s = statusLower;
    if (s === "responded") return "green";
    if (s === "invited") return "gray";
    if (s) return "amber";
    return "gray";
  }, [statusLower]);

  const regulators = useMemo(() => {
    const r = ev?.regulators;
    return Array.isArray(r) ? r : [];
  }, [ev]);

  const qCount = payload?.questions?.length || 0;

  const templateCode = ev?.instrument?.template_code || "DEFAULT";
  const version = ev?.instrument?.version ?? 1;

  return (
    <div style={ui.pageShellStyle()}>
      <ui.Card
        title="Evaluation"
        subtitle="Review the evaluation details before answering questions."
        right={<ui.Badge tone="blue">Board Member</ui.Badge>}
      >
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
          <ui.Badge tone="gray">Token: {(token || "").slice(0, 10)}…</ui.Badge>
          {busy ? <ui.Badge tone="gray">Loading…</ui.Badge> : null}
          {isResponded ? <ui.Badge tone="green">Completed</ui.Badge> : null}
        </div>

        {err ? (
          <div style={{ marginTop: 12 }}>
            <ui.Badge tone="red">Error</ui.Badge>
            <div style={{ marginTop: 8, color: "#991B1B", fontFamily: "monospace", fontSize: 12 }}>{err}</div>
          </div>
        ) : null}

        {payload ? (
          <div style={{ marginTop: 14, display: "grid", gap: 12 }}>
            {/* Respondent */}
            <div style={{ border: "1px solid #E5E7EB", borderRadius: 16, padding: 14, background: "#FFFFFF" }}>
              <div style={{ fontWeight: 950, color: "#0F172A" }}>Respondent</div>

              <div style={{ marginTop: 8, display: "flex", gap: 10, flexWrap: "wrap" }}>
                <ui.Badge tone="gray">{respondent?.full_name || "—"}</ui.Badge>
                <ui.Badge tone="gray">{respondent?.email || "—"}</ui.Badge>
                {respondent?.role ? <ui.Badge tone="purple">Role: {respondent.role}</ui.Badge> : null}

                {statusText ? <ui.Badge tone={statusTone}>Status: {statusText}</ui.Badge> : <ui.Badge tone="gray">Status: —</ui.Badge>}

                {assignment?.assignment_type ? <ui.Badge tone="gray">Assignment: {assignment.assignment_type}</ui.Badge> : null}
              </div>
            </div>

            {/* Evaluation */}
            <div style={{ border: "1px solid #E5E7EB", borderRadius: 16, padding: 14, background: "#FFFFFF" }}>
              <div style={{ fontWeight: 950, color: "#0F172A" }}>Evaluation</div>

              <div style={{ marginTop: 10, display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                <div>
                  <div style={{ fontSize: 12, color: "#64748B", fontWeight: 900 }}>Evaluation ID</div>
                  <div style={{ marginTop: 4, fontWeight: 900 }}>{ev?.evaluation_id || "—"}</div>
                </div>

                <div>
                  <div style={{ fontSize: 12, color: "#64748B", fontWeight: 900 }}>Tenant</div>
                  <div style={{ marginTop: 4, fontWeight: 900 }}>{ev?.tenant_name || "—"}</div>
                </div>

                <div>
                  <div style={{ fontSize: 12, color: "#64748B", fontWeight: 900 }}>Sector</div>
                  <div style={{ marginTop: 4, fontWeight: 900 }}>{ev?.sector || "—"}</div>
                </div>

                <div>
                  <div style={{ fontSize: 12, color: "#64748B", fontWeight: 900 }}>Year</div>
                  <div style={{ marginTop: 4, fontWeight: 900 }}>{String(ev?.year ?? "—")}</div>
                </div>

                <div style={{ gridColumn: "1 / -1" }}>
                  <div style={{ fontSize: 12, color: "#64748B", fontWeight: 900 }}>Regulators</div>
                  <div style={{ marginTop: 6, display: "flex", gap: 10, flexWrap: "wrap" }}>
                    {regulators.length ? regulators.map((r) => <ui.Badge key={r} tone="gray">{r}</ui.Badge>) : <ui.Badge tone="gray">—</ui.Badge>}
                  </div>
                </div>

                <div style={{ gridColumn: "1 / -1" }}>
                  <div style={{ fontSize: 12, color: "#64748B", fontWeight: 900 }}>Questionnaire</div>
                  <div style={{ marginTop: 6, display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
                    <ui.Badge tone="gray">
                      {templateCode} v{String(version)}
                    </ui.Badge>
                    <ui.Badge tone="green">Questions: {qCount}</ui.Badge>
                  </div>
                </div>
              </div>

              <div style={{ marginTop: 14, display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
                {!isResponded ? (
                  <>
                    <ui.Button
                      variant="primary"
                      disabled={busy}
                      onClick={() => nav(`/member/${token}/questions`)}
                      title="Go to questions"
                    >
                      Start answering →
                    </ui.Button>

                    <Link to={`/member/${token}/questions`} style={{ alignSelf: "center", fontWeight: 900, color: "#0F172A" }}>
                      Go to Questions →
                    </Link>
                  </>
                ) : (
                  <>
                    <ui.Button
                      variant="primary"
                      disabled={busy}
                      onClick={() => nav(`/member/${token}/thank-you`)}
                      title="View submission summary"
                    >
                      View submission summary →
                    </ui.Button>

                    <Link to={`/member/${token}/thank-you`} style={{ alignSelf: "center", fontWeight: 900, color: "#0F172A" }}>
                      Go to Thank you →
                    </Link>
                  </>
                )}
              </div>
            </div>
          </div>
        ) : !busy ? (
          <ui.Badge tone="amber" style={{ marginTop: 12 }}>
            No payload loaded.
          </ui.Badge>
        ) : null}
      </ui.Card>
    </div>
  );
}
