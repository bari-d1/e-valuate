/**
 * Personal task hub — lists all assessment assignments for one participant.
 *
 * Route: /member/hub/:hubToken
 * API: GET /api/v1/portal/hub/{hubToken}
 */

import React, { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { portalHubLoad } from "../../api/portalApi.js";
import { MemberUI as ui } from "./memberUi.jsx";

function tokenFromPortalUrl(url) {
  const m = String(url || "").match(/\/member\/([^/]+)\/questions/);
  return m ? decodeURIComponent(m[1]) : "";
}

function statusTone(status) {
  const s = String(status || "").toLowerCase();
  if (s === "responded") return "green";
  if (s === "invited") return "gray";
  return "blue";
}

export default function MemberHubPage() {
  const { hubToken } = useParams();
  const nav = useNavigate();
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState("");
  const [data, setData] = useState(null);

  useEffect(() => {
    const t = (hubToken || "").trim();
    if (!t) {
      setError("Missing hub link token.");
      setBusy(false);
      return;
    }

    let cancelled = false;
    (async () => {
      setBusy(true);
      setError("");
      try {
        const res = await portalHubLoad(t);
        if (!cancelled) setData(res);
      } catch (e) {
        if (!cancelled) setError(String(e?.message || e || "Could not load your tasks."));
      } finally {
        if (!cancelled) setBusy(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [hubToken]);

  const ev = data?.evaluation;
  const person = data?.respondent;
  const assignments = Array.isArray(data?.assignments) ? data.assignments : [];

  return (
    <div style={ui.pageShellStyle()}>
      <ui.Card
        title="My assessment tasks"
        subtitle={
          ev
            ? `${ev.tenant_name || "Board evaluation"} · ${ev.year || ""} · ${ev.evaluation_id || ""}`
            : "Board member portal"
        }
        right={<ui.Badge tone="blue">Task hub</ui.Badge>}
      >
        {busy ? (
          <div style={{ padding: 8, color: "#64748B", fontWeight: 700 }}>Loading your tasks…</div>
        ) : null}

        {error ? (
          <div
            style={{
              marginTop: 10,
              padding: 12,
              borderRadius: 12,
              border: "1px solid #FECACA",
              background: "#FEF2F2",
              color: "#991B1B",
              fontSize: 13,
            }}
          >
            <b>Could not open hub:</b>
            <div style={{ marginTop: 6 }}>{error}</div>
            <div style={{ marginTop: 10 }}>
              <Link to="/member/invite" style={{ fontWeight: 900, color: "#0F172A" }}>
                ← Back to portal entry
              </Link>
            </div>
          </div>
        ) : null}

        {!busy && !error && data ? (
          <>
            <div
              style={{
                marginTop: 4,
                padding: 12,
                borderRadius: 12,
                background: "#F8FAFC",
                border: "1px solid #E5E7EB",
                fontSize: 13,
              }}
            >
              <div>
                <b>{person?.full_name || person?.email || "Participant"}</b>
                {person?.role ? (
                  <span style={{ marginLeft: 8 }}>
                    <ui.Badge tone="gray">{person.role}</ui.Badge>
                  </span>
                ) : null}
              </div>
              {person?.email ? (
                <div style={{ marginTop: 4, color: "#64748B" }}>{person.email}</div>
              ) : null}
            </div>

            {assignments.length === 0 ? (
              <div
                style={{
                  marginTop: 14,
                  padding: 14,
                  borderRadius: 12,
                  border: "1px solid #BFDBFE",
                  background: "#EFF6FF",
                  color: "#1E3A8A",
                  fontSize: 13,
                  lineHeight: 1.45,
                }}
              >
                <b>No questionnaires yet.</b> You are registered for this evaluation. Your consultant will
                generate your assessment tasks soon—you can bookmark this page and check back, or wait for
                an email with your task links.
              </div>
            ) : (
              <div style={{ marginTop: 14, overflowX: "auto" }}>
                <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
                  <thead style={{ background: "#F8FAFC" }}>
                    <tr>
                      {["Task", "Status", "Action"].map((h) => (
                        <th
                          key={h}
                          style={{
                            textAlign: "left",
                            padding: "10px 12px",
                            borderBottom: "1px solid #E5E7EB",
                            fontWeight: 800,
                          }}
                        >
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {assignments.map((a) => {
                      const token = tokenFromPortalUrl(a.portal_url);
                      const done = String(a.status || "").toLowerCase() === "responded";
                      return (
                        <tr key={a.assignment_id} style={{ borderBottom: "1px solid #F1F5F9" }}>
                          <td style={{ padding: "10px 12px", fontWeight: 800 }}>{a.label || a.assignment_type}</td>
                          <td style={{ padding: "10px 12px" }}>
                            <ui.Badge tone={statusTone(a.status)}>{a.status || "—"}</ui.Badge>
                          </td>
                          <td style={{ padding: "10px 12px" }}>
                            {token ? (
                              <ui.Button
                                variant={done ? "soft" : "primary"}
                                onClick={() => nav(`/member/${encodeURIComponent(token)}/questions`)}
                              >
                                {done ? "View / summary" : "Open questionnaire"}
                              </ui.Button>
                            ) : (
                              "—"
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}

            <div style={{ marginTop: 14, fontSize: 12, color: "#64748B" }}>
              Each task opens a separate questionnaire. Complete every task that applies to you.
            </div>
          </>
        ) : null}
      </ui.Card>
    </div>
  );
}
