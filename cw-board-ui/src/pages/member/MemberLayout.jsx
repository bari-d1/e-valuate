/**
 * src/pages/member/MemberLayout.jsx
 * --------------------------------
 * Layout wrapper for the Board Member portal routes.
 *
 * Member flow:
 *   view evaluation → answer questions → submit → thank you
 *
 * What this component does:
 *  - Provides a consistent page shell (header + container)
 *  - Renders nested member routes via <Outlet />
 *  - Optionally shows the token (from URL) for debugging/support
 *
 * Assumptions:
 *  - Your router mounts this layout at /member (nested routes under it)
 *  - Routes include token-scoped paths like /member/:token/evaluation, etc.
 */

import React from "react";
import { Outlet, useLocation, useParams } from "react-router-dom";

export default function MemberLayout() {
  const { token } = useParams();
  const loc = useLocation();

  const showToken = Boolean(token);

  return (
    <div style={page()}>
      <header style={header()}>
        <div style={brand()}>
          <div style={brandTop()}>Board Member Portal</div>
          <div style={brandSub()}>
            Complete your evaluation: view → answer → submit
          </div>
        </div>

        <div style={right()}>
          {showToken ? (
            <span style={pill()} title="Support token (from your invite link)">
              Token: {String(token).slice(0, 8)}…
            </span>
          ) : (
            <span style={pillMuted()} title="No token in route yet">
              {loc.pathname}
            </span>
          )}
        </div>
      </header>

      <main style={main()}>
        <Outlet />
      </main>

      <footer style={footer()}>
        <div style={{ opacity: 0.8 }}>
          If you have trouble accessing your questionnaire, please contact your administrator.
        </div>
      </footer>
    </div>
  );
}

/** ---------- local styles (simple + dependency-free) ---------- */

function page() {
  return {
    minHeight: "100vh",
    background: "#F8FAFC",
    display: "flex",
    flexDirection: "column",
  };
}

function header() {
  return {
    padding: "14px 18px",
    borderBottom: "1px solid #E5E7EB",
    background: "white",
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 12,
  };
}

function brand() {
  return { display: "flex", flexDirection: "column", gap: 2 };
}

function brandTop() {
  return { fontSize: 16, fontWeight: 900, color: "#0F172A" };
}

function brandSub() {
  return { fontSize: 12, color: "#64748B", fontWeight: 700 };
}

function right() {
  return { display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" };
}

function pill() {
  return {
    fontSize: 12,
    fontWeight: 900,
    color: "#0F172A",
    border: "1px solid #E5E7EB",
    background: "#F8FAFC",
    borderRadius: 999,
    padding: "6px 10px",
    whiteSpace: "nowrap",
  };
}

function pillMuted() {
  return {
    fontSize: 12,
    fontWeight: 800,
    color: "#64748B",
    border: "1px solid #E5E7EB",
    background: "#F8FAFC",
    borderRadius: 999,
    padding: "6px 10px",
    whiteSpace: "nowrap",
  };
}

function main() {
  return {
    width: "min(920px, 100%)",
    margin: "0 auto",
    padding: 18,
    flex: 1,
  };
}

function footer() {
  return {
    padding: "14px 18px",
    borderTop: "1px solid #E5E7EB",
    background: "white",
    fontSize: 12,
    color: "#64748B",
    fontWeight: 700,
  };
}
