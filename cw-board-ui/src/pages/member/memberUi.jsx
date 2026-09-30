/**
 * src/pages/member/memberUi.jsx
 * -----------------------------
 * Shared UI toolkit for the Board Member portal.
 *
 * Goals:
 * - Make Member portal styling consistent and polished (similar vibe to Consultant UI)
 * - Provide a small "ui bundle" with components + style helpers:
 *   - Card, Badge, Button, Field
 *   - pageShellStyle, inputStyle, textareaStyle
 *   - renderFlowBar (optional action row)
 *
 * Usage:
 *   import { MemberUI as ui } from "./memberUi.jsx";
 *   <div style={ui.pageShellStyle()}>
 *     <ui.Card title="..." subtitle="..." right={<ui.Badge tone="blue">Board Member</ui.Badge>}>
 *       ...
 *     </ui.Card>
 *   </div>
 */

import React from "react";

/** @returns {import("react").CSSProperties} */
function pageShellStyle() {
  return {
    minHeight: "100vh",
    padding: 18,
    background: "linear-gradient(180deg, #F8FAFC 0%, #FFFFFF 50%, #F8FAFC 100%)",
    color: "#0F172A",
  };
}

/** @returns {import("react").CSSProperties} */
function cardWrapStyle() {
  return {
    maxWidth: 980,
    margin: "0 auto",
    background: "white",
    border: "1px solid #E5E7EB",
    borderRadius: 18,
    boxShadow: "0 8px 30px rgba(15,23,42,0.06)",
    overflow: "hidden",
  };
}

/** @returns {import("react").CSSProperties} */
function cardHeaderStyle() {
  return {
    padding: "16px 16px 12px",
    borderBottom: "1px solid #EEF2F7",
    background: "linear-gradient(180deg, #FFFFFF 0%, #FBFDFF 100%)",
  };
}

/** @returns {import("react").CSSProperties} */
function cardBodyStyle() {
  return {
    padding: 16,
  };
}

/**
 * Small Card component compatible with your Member pages.
 * @param {{title?: string, subtitle?: string, right?: any, children?: any}} props
 */
function Card({ title, subtitle, right, children }) {
  return (
    <div style={cardWrapStyle()}>
      {(title || subtitle || right) ? (
        <div style={cardHeaderStyle()}>
          <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "flex-start", flexWrap: "wrap" }}>
            <div>
              {title ? (
                <div style={{ fontSize: 18, fontWeight: 950, color: "#0F172A", letterSpacing: -0.2 }}>
                  {title}
                </div>
              ) : null}
              {subtitle ? (
                <div style={{ marginTop: 4, color: "#64748B", fontSize: 13, lineHeight: 1.35 }}>
                  {subtitle}
                </div>
              ) : null}
            </div>

            {right ? <div>{right}</div> : null}
          </div>
        </div>
      ) : null}

      <div style={cardBodyStyle()}>{children}</div>
    </div>
  );
}

/**
 * Badge component: tone controls colors.
 * @param {{tone?: "gray"|"blue"|"green"|"amber"|"red"|"purple", children?: any}} props
 */
function Badge({ tone = "gray", children }) {
  const map = {
    gray: { bg: "#F1F5F9", fg: "#334155", br: "#E2E8F0" },
    blue: { bg: "#EEF2FF", fg: "#3730A3", br: "#C7D2FE" },
    green: { bg: "#ECFDF3", fg: "#065F46", br: "#A7F3D0" },
    amber: { bg: "#FFF7ED", fg: "#92400E", br: "#FED7AA" },
    red: { bg: "#FEF2F2", fg: "#991B1B", br: "#FECACA" },
    purple: { bg: "#F5F3FF", fg: "#5B21B6", br: "#DDD6FE" },
  };

  const c = map[tone] || map.gray;

  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 8,
        padding: "4px 10px",
        borderRadius: 999,
        border: `1px solid ${c.br}`,
        background: c.bg,
        color: c.fg,
        fontSize: 12,
        fontWeight: 900,
        whiteSpace: "nowrap",
      }}
    >
      {children}
    </span>
  );
}

/**
 * Button component compatible with Consultant-ish variants.
 * @param {{variant?: "primary"|"secondary"|"soft"|"highlight", disabled?: boolean, title?: string, onClick?: Function, children?: any}} props
 */
function Button({ variant = "soft", disabled = false, title = "", onClick, children }) {
  const base = {
    padding: "10px 12px",
    borderRadius: 12,
    border: "1px solid #E5E7EB",
    fontWeight: 950,
    fontSize: 13,
    cursor: disabled ? "not-allowed" : "pointer",
    opacity: disabled ? 0.6 : 1,
    transition: "transform 120ms ease, box-shadow 120ms ease, background 120ms ease",
    userSelect: "none",
  };

  const variants = {
    primary: { background: "#0F172A", color: "#FFFFFF", border: "1px solid #0F172A" },
    secondary: { background: "#EEF2FF", color: "#1E1B4B", border: "1px solid #C7D2FE" },
    soft: { background: "#F8FAFC", color: "#0F172A", border: "1px solid #E5E7EB" },
    highlight: { background: "#F5F3FF", color: "#3B0764", border: "1px solid #DDD6FE" },
  };

  const v = variants[variant] || variants.soft;

  return (
    <button
      type="button"
      title={title}
      disabled={disabled}
      onClick={(e) => {
        if (disabled) return;
        onClick?.(e);
      }}
      style={{ ...base, ...v, boxShadow: disabled ? "none" : "0 6px 18px rgba(15,23,42,0.08)" }}
      onMouseDown={(e) => {
        if (disabled) return;
        e.currentTarget.style.transform = "scale(0.98)";
      }}
      onMouseUp={(e) => {
        if (disabled) return;
        e.currentTarget.style.transform = "scale(1)";
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.transform = "scale(1)";
      }}
    >
      {children}
    </button>
  );
}

/**
 * Field wrapper for label + hint + children
 * @param {{label?: string, hint?: string, children?: any}} props
 */
function Field({ label, hint, children }) {
  return (
    <div style={{ display: "grid", gap: 6 }}>
      {label ? (
        <div style={{ fontSize: 12, fontWeight: 950, color: "#0F172A" }}>
          {label}
          {hint ? <span style={{ marginLeft: 8, fontWeight: 700, color: "#64748B" }}>{hint}</span> : null}
        </div>
      ) : null}
      {children}
    </div>
  );
}

/** @returns {import("react").CSSProperties} */
function inputStyle() {
  return {
    width: "100%",
    padding: "10px 12px",
    borderRadius: 12,
    border: "1px solid #E5E7EB",
    background: "#FFFFFF",
    color: "#0F172A",
    fontSize: 13,
    outline: "none",
  };
}

/**
 * @param {number} h
 * @returns {import("react").CSSProperties}
 */
function textareaStyle(h = 120) {
  return {
    ...inputStyle(),
    height: h,
    resize: "vertical",
    lineHeight: 1.35,
  };
}

/**
 * Simple “flow bar” (left actions | meta | right actions)
 * @param {{left?: Array<any>, meta?: any, right?: Array<any>, marginTop?: number, tone?: string}} cfg
 */
function renderFlowBar(cfg = {}) {
  const { left = [], meta = null, right = [], marginTop = 12 } = cfg;

  const renderItems = (items) =>
    (items || []).map((it) => (
      <Button
        key={it.key || it.label}
        variant={it.variant || "soft"}
        disabled={!!it.disabled}
        title={it.title || ""}
        onClick={it.onClick}
      >
        {it.label}
      </Button>
    ));

  return (
    <div
      style={{
        marginTop,
        padding: 12,
        borderRadius: 14,
        border: "1px solid #E5E7EB",
        background: "#F8FAFC",
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        gap: 12,
        flexWrap: "wrap",
      }}
    >
      <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
        {renderItems(left)}
      </div>

      <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
        {meta}
      </div>

      <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
        {renderItems(right)}
      </div>
    </div>
  );
}

/**
 * Export bundle as `MemberUI` so your pages can do:
 *   import { MemberUI as ui } from "./memberUi.jsx";
 */
export const MemberUI = {
  Card,
  Badge,
  Button,
  Field,

  pageShellStyle,
  inputStyle,
  textareaStyle,
  renderFlowBar,
};
