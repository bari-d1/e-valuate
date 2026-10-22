import React from "react";
import { color, font, radius, space } from "../../../theme.js";

/** Small building blocks shared by the company pages. */

export function SectionTitle({ children, hint }) {
  return (
    <div style={{ marginBottom: space.sm }}>
      <h2 style={{ margin: 0, fontSize: 15, fontWeight: font.weight.heavy, color: color.text }}>{children}</h2>
      {hint ? <p style={{ margin: "2px 0 0", fontSize: 13, color: color.textMuted }}>{hint}</p> : null}
    </div>
  );
}

export function Notice({ tone = "info", children }) {
  const tones = {
    info: { bg: color.primarySoft, bd: color.primarySoftBorder, fg: "#1E3A8A" },
    error: { bg: "#FEF2F2", bd: "#FECACA", fg: "#7F1D1D" },
    success: { bg: "#ECFDF5", bd: "#A7F3D0", fg: "#065F46" },
    warn: { bg: "#FFF7ED", bd: "#FED7AA", fg: "#92400E" },
  };
  const t = tones[tone] || tones.info;
  return (
    <div
      role={tone === "error" ? "alert" : "status"}
      style={{
        padding: "10px 12px",
        borderRadius: radius.sm,
        border: `1px solid ${t.bd}`,
        background: t.bg,
        color: t.fg,
        fontSize: 13,
        lineHeight: 1.45,
        whiteSpace: "pre-wrap",
      }}
    >
      {children}
    </div>
  );
}

export function Panel({ children, highlight = false, style }) {
  return (
    <div
      style={{
        border: `1px solid ${highlight ? "#FED7AA" : color.border}`,
        background: highlight ? "#FFFBF5" : color.surface,
        borderRadius: radius.md,
        padding: space.md,
        ...style,
      }}
    >
      {children}
    </div>
  );
}

export function LinkButton({ children, onClick, disabled, danger = false, title }) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      title={title}
      style={{
        padding: 0,
        border: 0,
        background: "none",
        color: disabled ? color.disabledText : danger ? color.danger : color.primaryText,
        fontWeight: font.weight.bold,
        fontSize: 13,
        cursor: disabled ? "not-allowed" : "pointer",
        textDecoration: "underline",
      }}
    >
      {children}
    </button>
  );
}

/** A quoted excerpt from a source document, for proposals. */
export function Excerpt({ text, filename }) {
  if (!text) return null;
  return (
    <figure style={{ margin: `${space.sm}px 0 0` }}>
      <blockquote
        style={{
          margin: 0,
          padding: "6px 10px",
          borderLeft: `3px solid ${color.borderStrong}`,
          background: color.surfaceMuted,
          color: color.text,
          fontSize: 13,
          fontStyle: "italic",
        }}
      >
        “{text}”
      </blockquote>
      {filename ? (
        <figcaption style={{ marginTop: 2, fontSize: font.small, color: color.textMuted }}>From {filename}</figcaption>
      ) : null}
    </figure>
  );
}

