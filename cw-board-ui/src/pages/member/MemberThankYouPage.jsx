/**
 * MemberThankYouPage.jsx
 * ----------------------
 * Board Member Portal — Thank-you / completion page.
 *
 * Route:
 *   /member/:token/thank-you
 *
 * What it does:
 * - Shows a confirmation message after successful submission.
 * - Loads portal context + saved responses to display a lightweight summary:
 *     - respondent name/email
 *     - evaluation tenant/sector/year
 *     - assignment status + responded_at (assignment-first)
 *     - answered count (based on saved responses)
 *
 * Notes:
 * - Read-only page.
 * - If token is invalid/expired, shows safe error and link back to /member/invite.
 */

import React, { useEffect, useMemo, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { portalLoad, portalGetResponses } from "../../api/portalApi.js";

export default function MemberThankYouPage() {
  const { token } = useParams();

  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  const [portal, setPortal] = useState(null);
  const [responses, setResponses] = useState(null);

  // ✅ API shape: { assignment, respondent, subject?, evaluation, questions }
  const assignment = portal?.assignment || {};
  const participant = portal?.respondent || {};
  const evaluation = portal?.evaluation || {};

  const questions = Array.isArray(portal?.questions) ? portal.questions : [];
  const items = Array.isArray(responses?.items) ? responses.items : [];

  const answeredCount = useMemo(() => {
    const byId = new Map();
    for (const it of items) byId.set(String(it.question_id), it);

    let n = 0;
    for (const q of questions) {
      const qid = String(q.question_id);
      const at = String(q.answer_type || "").toLowerCase();
      const r = byId.get(qid);
      if (!r) continue;

      // rating / yesno strict; everything else is treated like "comment/text"
      if (at === "rating") {
        if (r.score !== null && r.score !== undefined) n += 1;
      } else if (at === "yesno") {
        if (r.score === 0 || r.score === 1) n += 1;
      } else {
        if (String(r.comment || "").trim()) n += 1;
      }
    }
    return n;
  }, [items, questions]);

  async function load() {
    const t = String(token || "").trim();
    if (!t) {
      setErr("Missing token in URL.");
      setLoading(false);
      return;
    }

    setErr("");
    setLoading(true);
    setBusy(true);

    try {
      // Load portal first (required)
      const p = await portalLoad(t);
      setPortal(p);

      // Responses are nice-to-have; don't fail the whole page if this errors
      try {
        const r = await portalGetResponses(t);
        setResponses(r);
      } catch (e) {
        setResponses(null);
      }
    } catch (e) {
      setErr(String(e?.message || e));
    } finally {
      setBusy(false);
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  const instrument = evaluation?.instrument || {};
  const templateCode = instrument?.template_code || "DEFAULT";
  const version = instrument?.version ?? 1;

  // ✅ assignment-first “truth”
  const statusRaw = String(assignment?.status || participant?.status || "").trim();
  const status = statusRaw.toLowerCase();
  const respondedAt = assignment?.responded_at || participant?.responded_at || null;

  return (
    <div style={pageWrap()}>
      <div style={card()}>
        <div style={{ display: "flex", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
          <div>
            <div style={title()}>Thank you!</div>
            <div style={subtitle()}>Your response has been recorded.</div>
          </div>

          <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
            <button onClick={load} disabled={busy} style={btn()}>
              {busy ? "Refreshing..." : "Refresh summary"}
            </button>

            <Link to="/member/invite" style={linkBtn()}>
              Use another invite →
            </Link>
          </div>
        </div>

        {err ? <div style={errorBox()}>{err}</div> : null}

        <div style={{ marginTop: 10, fontSize: 12, color: "#94A3B8" }}>
          Token: <span style={{ fontFamily: "monospace" }}>{String(token || "")}</span>
        </div>

        {!loading && portal ? (
          <>
            <div style={grid()}>
              <div style={panel()}>
                <div style={panelTitle()}>Summary</div>

                <div style={row()}>
                  <span style={label()}>Status</span>
                  <span style={pill(status)}>{statusRaw ? statusRaw : "—"}</span>
                </div>

                <div style={row()}>
                  <span style={label()}>Answered</span>
                  <span style={value()}>
                    {answeredCount}/{questions.length}
                  </span>
                </div>

                <div style={row()}>
                  <span style={label()}>Responded at</span>
                  <span style={value()}>{respondedAt || "—"}</span>
                </div>
              </div>

              <div style={panel()}>
                <div style={panelTitle()}>You</div>

                <div style={row()}>
                  <span style={label()}>Name</span>
                  <span style={value()}>{participant?.full_name || "—"}</span>
                </div>

                <div style={row()}>
                  <span style={label()}>Email</span>
                  <span style={value()}>{participant?.email || "—"}</span>
                </div>

                <div style={row()}>
                  <span style={label()}>Role</span>
                  <span style={value()}>{participant?.role || "—"}</span>
                </div>
              </div>

              <div style={panelWide()}>
                <div style={panelTitle()}>Evaluation</div>

                <div style={row()}>
                  <span style={label()}>Tenant</span>
                  <span style={value()}>{evaluation?.tenant_name || "—"}</span>
                </div>

                <div style={row()}>
                  <span style={label()}>Sector</span>
                  <span style={value()}>{evaluation?.sector || "—"}</span>
                </div>

                <div style={row()}>
                  <span style={label()}>Year</span>
                  <span style={value()}>{evaluation?.year ?? "—"}</span>
                </div>

                <div style={row()}>
                  <span style={label()}>Questionnaire</span>
                  <span style={value()}>
                    {String(templateCode)} v{String(version)}
                  </span>
                </div>
              </div>
            </div>

            {status && status !== "responded" ? (
              <div style={warnBox()}>
                It looks like your <b>assignment</b> is not marked as <b>responded</b> yet.
                If you just submitted, click <b>Refresh summary</b>. If it still doesn’t update,
                go back to your submit page and try again.
              </div>
            ) : null}
          </>
        ) : loading ? (
          <div style={{ marginTop: 12, color: "#64748B", fontSize: 13 }}>Loading summary…</div>
        ) : null}
      </div>
    </div>
  );
}

/* ------------------------- styles ------------------------- */

function pageWrap() {
  return { padding: 18, maxWidth: 980, margin: "0 auto" };
}
function card() {
  return {
    padding: 16,
    background: "white",
    borderRadius: 16,
    border: "1px solid #E5E7EB",
    boxShadow: "0 1px 2px rgba(15, 23, 42, 0.05)",
  };
}
function title() {
  return { fontWeight: 900, color: "#0F172A", fontSize: 22 };
}
function subtitle() {
  return { marginTop: 6, color: "#64748B", fontSize: 13 };
}
function grid() {
  return { marginTop: 14, display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 };
}
function panel() {
  return { padding: 12, borderRadius: 14, border: "1px solid #E5E7EB", background: "#FFFFFF" };
}
function panelWide() {
  return { ...panel(), gridColumn: "1 / -1" };
}
function panelTitle() {
  return { fontWeight: 900, color: "#0F172A", marginBottom: 10 };
}
function row() {
  return { display: "flex", justifyContent: "space-between", gap: 10, marginTop: 8 };
}
function label() {
  return { fontSize: 12, color: "#64748B", fontWeight: 800 };
}
function value() {
  return { fontSize: 13, color: "#0F172A", fontWeight: 800, textAlign: "right" };
}
function pill(status) {
  const s = String(status || "").toLowerCase();
  const ok = s === "responded";
  return {
    padding: "3px 10px",
    borderRadius: 999,
    border: "1px solid #E5E7EB",
    background: ok ? "#E8FFF3" : "#FFF7ED",
    color: ok ? "#065F46" : "#92400E",
    fontWeight: 900,
    fontSize: 12,
    textTransform: "capitalize",
  };
}
function btn() {
  return {
    borderRadius: 12,
    padding: "10px 12px",
    fontWeight: 900,
    fontSize: 13,
    border: "1px solid #E5E7EB",
    background: "#F8FAFC",
    color: "#0F172A",
    cursor: "pointer",
  };
}
function linkBtn() {
  return {
    display: "inline-block",
    borderRadius: 12,
    padding: "10px 12px",
    fontWeight: 900,
    fontSize: 13,
    border: "1px solid #E5E7EB",
    background: "#111827",
    color: "white",
    textDecoration: "none",
  };
}
function errorBox() {
  return {
    marginTop: 12,
    padding: 12,
    borderRadius: 12,
    border: "1px solid #FECACA",
    background: "#FEF2F2",
    color: "#991B1B",
    fontWeight: 800,
    whiteSpace: "pre-wrap",
  };
}
function warnBox() {
  return {
    marginTop: 12,
    padding: 12,
    borderRadius: 12,
    border: "1px solid #FED7AA",
    background: "#FFF7ED",
    color: "#92400E",
    fontWeight: 800,
  };
}
