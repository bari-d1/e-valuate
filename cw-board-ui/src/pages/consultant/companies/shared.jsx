import React from "react";
import { SOURCE_LABELS } from "../../../api/orgApi.js";
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


export function SourceTag({ ui, source }) {
  const { Badge } = ui;
  const tone = { public: "blue", client: "purple", consultant: "gray" }[source] || "gray";
  return <Badge tone={tone}>{SOURCE_LABELS[source] || source}</Badge>;
}

/**
 * Corrections participants gave on their form ("Needs updating" on a confirm item). They are the
 * participant's own words, never applied by themselves: the consultant confirms a proper value
 * (renderEditor) or dismisses them. Without renderEditor (a fact the profile doesn't hold), only dismiss.
 */
export function ParticipantCorrections({ ui, items, editingId, onEdit, onDismiss, renderEditor, busy }) {
  const { Badge, Button } = ui;
  if (!items || !items.length) return null;
  return items.map((p) => (
    <Panel highlight key={p.fact_id} style={{ marginTop: space.sm }}>
      <div style={{ display: "flex", gap: space.sm, alignItems: "center", flexWrap: "wrap" }}>
        <Badge tone="purple">From the participant</Badge>
        <span style={{ fontWeight: font.weight.bold, color: color.text, whiteSpace: "pre-wrap" }}>
          {p.value ? `“${p.value}”` : "No correction given"}
        </span>
      </div>
      {p.note ? <div style={{ marginTop: 4, fontSize: font.small, color: color.textMuted }}>{p.note}</div> : null}
      {editingId === p.fact_id && renderEditor ? (
        <div style={{ marginTop: space.sm }}>{renderEditor(p)}</div>
      ) : (
        <div style={{ display: "flex", gap: space.sm, flexWrap: "wrap", marginTop: space.sm }}>
          {renderEditor ? (
            <Button onClick={() => onEdit(p.fact_id)} disabled={busy}>
              Set the correct value
            </Button>
          ) : null}
          <Button variant="danger" onClick={() => onDismiss(p)} disabled={busy}>
            Dismiss
          </Button>
        </div>
      )}
    </Panel>
  ));
}

/** What an extraction run dropped and why, collapsed under a one-line count. */
export function DroppedItems({ items }) {
  if (!items || !items.length) return null;
  return (
    <details style={{ marginTop: space.sm, fontSize: 13 }}>
      <summary style={{ cursor: "pointer", color: color.text }}>
        {`${items.length} item(s) were dropped because they couldn't be checked against the documents. Show which`}
      </summary>
      <ul style={{ margin: `${space.xs}px 0 0`, paddingLeft: 18, color: color.textMuted, display: "grid", gap: 2 }}>
        {items.map((d, i) => (
          <li key={i}>
            <span style={{ color: color.text }}>{d.label || d.committee || d.key || "Item"}</span>
            {d.filename ? ` (${d.filename}${d.part ? `, ${d.part}` : ""})` : ""}: {d.reason}
          </li>
        ))}
      </ul>
    </details>
  );
}
