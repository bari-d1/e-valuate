/**
 * src/pages/member/MemberInvitePage.jsx
 * ------------------------------------
 * Board Member entry page for the token-based portal.
 *
 * Supported entry URLs:
 *  - /member/invite
 *  - /member/invite/:token
 *  - /member/invite?token=...
 *
 * What this page does:
 *  1) Reads token from route param or query param (if provided)
 *  2) Lets user paste/edit token manually
 *  3) Calls portalLoad(token) to validate token + fetch portal context
 *  4) If valid, navigates to /member/:token/evaluation
 *
 * Notes:
 * - Backend payload uses `respondent` (new) but some older data may still use `participant`.
 */

import React, { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { portalHubLoad, portalLoad } from "../../api/portalApi.js";

export default function MemberInvitePage() {
  const nav = useNavigate();
  const params = useParams();
  const [searchParams] = useSearchParams();

  const initialToken = useMemo(() => {
    const fromParam = (params?.token || "").trim();
    const fromQuery = (searchParams.get("token") || "").trim();
    return fromParam || fromQuery || "";
  }, [params, searchParams]);

  const [token, setToken] = useState(initialToken);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [preview, setPreview] = useState(null); // shows who/what this link is for

  // Keep input in sync if user hits /member/invite/:token directly
  useEffect(() => {
    setToken(initialToken);
  }, [initialToken]);

  async function validateAndContinue(t) {
    const trimmed = (t || "").trim();
    setError("");
    setPreview(null);

    if (!trimmed) {
      setError("Please enter your access token (from your invite link).");
      return;
    }

    try {
      setBusy(true);

      const hub = await portalHubLoad(trimmed, { allowNotFound: true });
      if (hub) {
        setPreview({
          person: hub?.respondent || null,
          evaluation: hub?.evaluation || null,
          questionCount: Array.isArray(hub?.assignments) ? hub.assignments.length : 0,
          status: hub?.assignments?.length ? "tasks ready" : "registered",
          isHub: true,
        });
        nav(`/member/hub/${encodeURIComponent(trimmed)}`, { replace: true });
        return;
      }

      const data = await portalLoad(trimmed);
      const person = data?.respondent || data?.participant || null;
      const statusText = String(data?.assignment?.status || person?.status || "").trim();

      setPreview({
        person,
        evaluation: data?.evaluation || null,
        questionCount: Array.isArray(data?.questions) ? data.questions.length : 0,
        status: statusText,
        isHub: false,
      });

      nav(`/member/${encodeURIComponent(trimmed)}/evaluation`, { replace: true });
    } catch (e) {
      setError(String(e?.message || e || "Invalid or expired link."));
    } finally {
      setBusy(false);
    }
  }

  // Auto-validate if token is present in URL
  useEffect(() => {
    if (initialToken) validateAndContinue(initialToken);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialToken]);

  return (
    <div style={pageWrap()}>
      <div style={card()}>
        <div style={title()}>Board Member Portal</div>
        <div style={subtitle()}>
          Use your <b>hub link</b> to see all tasks, or a <b>task link</b> to open one questionnaire directly.
        </div>

        <div style={{ marginTop: 14 }}>
          <label style={label()}>Access Token</label>
          <input
            value={token}
            onChange={(e) => setToken(e.target.value)}
            placeholder="e.g. 8f3c2a... (from your invite link)"
            style={input()}
            autoComplete="off"
            spellCheck={false}
            disabled={busy}
          />
          <div style={hint()}>
            <div>
              <b>Hub</b> (all your tasks): <code>/member/hub/&lt;hub_token&gt;</code>
            </div>
            <div style={{ marginTop: 4 }}>
              <b>Task</b> (one questionnaire): <code>/member/&lt;assignment_token&gt;/questions</code>
            </div>
          </div>
        </div>

        {error ? (
          <div style={errorBox()}>
            <b>Could not open portal:</b>
            <div style={{ marginTop: 6, whiteSpace: "pre-wrap" }}>{error}</div>
          </div>
        ) : null}

        <div style={{ marginTop: 14, display: "flex", gap: 10, flexWrap: "wrap" }}>
          <button
            onClick={() => validateAndContinue(token)}
            disabled={busy}
            style={primaryBtn(busy)}
            title="Validate token and continue"
          >
            {busy ? "Checking link..." : "Continue"}
          </button>

          <button
            onClick={() => {
              setToken("");
              setError("");
              setPreview(null);
              nav("/member/invite", { replace: true });
            }}
            disabled={busy}
            style={softBtn()}
            title="Clear token"
          >
            Clear
          </button>
        </div>

        {preview ? (
          <div style={previewBox()}>
            <div style={{ fontWeight: 900, marginBottom: 6 }}>Link Preview</div>

            <div style={kvRow()}>
              <span style={k()}>Status</span>
              <span style={v()}>{preview.status || "—"}</span>
            </div>

            <div style={kvRow()}>
              <span style={k()}>Email</span>
              <span style={v()}>{preview.person?.email || "—"}</span>
            </div>

            <div style={kvRow()}>
              <span style={k()}>Name</span>
              <span style={v()}>{preview.person?.full_name || "—"}</span>
            </div>

            <div style={kvRow()}>
              <span style={k()}>Evaluation</span>
              <span style={v()}>{preview.evaluation?.evaluation_id || "—"}</span>
            </div>

            <div style={kvRow()}>
              <span style={k()}>Questions</span>
              <span style={v()}>{preview.questionCount}</span>
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}

/** ---------- tiny inline styles (kept local on purpose) ---------- */

function pageWrap() {
  return {
    padding: 18,
    display: "flex",
    justifyContent: "center",
  };
}

function card() {
  return {
    width: "min(760px, 100%)",
    border: "1px solid #E5E7EB",
    borderRadius: 16,
    padding: 16,
    background: "white",
    boxShadow: "0 1px 10px rgba(2,6,23,0.05)",
  };
}

function title() {
  return { fontSize: 18, fontWeight: 900, color: "#0F172A" };
}

function subtitle() {
  return { marginTop: 6, fontSize: 13, color: "#64748B" };
}

function label() {
  return { display: "block", fontSize: 13, fontWeight: 800, color: "#0F172A", marginBottom: 6 };
}

function input() {
  return {
    width: "100%",
    padding: "10px 12px",
    borderRadius: 12,
    border: "1px solid #E5E7EB",
    outline: "none",
    fontSize: 14,
  };
}

function hint() {
  return { marginTop: 8, fontSize: 12, color: "#64748B" };
}

function primaryBtn(disabled) {
  return {
    padding: "10px 12px",
    borderRadius: 12,
    border: "1px solid #0F172A",
    background: disabled ? "#94A3B8" : "#0F172A",
    color: "white",
    fontWeight: 900,
    cursor: disabled ? "not-allowed" : "pointer",
  };
}

function softBtn() {
  return {
    padding: "10px 12px",
    borderRadius: 12,
    border: "1px solid #E5E7EB",
    background: "#F8FAFC",
    color: "#0F172A",
    fontWeight: 800,
    cursor: "pointer",
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
    fontSize: 13,
  };
}

function previewBox() {
  return {
    marginTop: 14,
    padding: 12,
    borderRadius: 12,
    border: "1px solid #E5E7EB",
    background: "#F8FAFC",
    color: "#0F172A",
    fontSize: 13,
  };
}

function kvRow() {
  return {
    display: "grid",
    gridTemplateColumns: "140px 1fr",
    gap: 10,
    padding: "6px 0",
    borderTop: "1px solid #E5E7EB",
  };
}

function k() {
  return { color: "#64748B", fontWeight: 800 };
}

function v() {
  return { color: "#0F172A", fontWeight: 800, wordBreak: "break-word" };
}
