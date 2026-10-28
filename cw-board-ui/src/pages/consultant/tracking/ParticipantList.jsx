import React, { useState } from "react";
import { color, font, radius, space } from "../../../theme.js";
import { LinkButton } from "../companies/shared.jsx";
import { OUTSTANDING, STATUS_TONES, ago, shortDate } from "./trackingHelpers.js";

/**
 * Every participant's status and progress, with actions. A table on wide screens and a list of
 * cards on phones. Progress only: never anyone's answers.
 */

function Bar({ answered, required, label }) {
  const pct = required ? Math.round((answered / required) * 100) : 0;
  return (
    <div style={{ display: "grid", gap: 4, minWidth: 110 }}>
      <div
        role="progressbar"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={required}
        aria-valuenow={answered}
        aria-valuetext={`${answered} of ${required} required questions answered`}
        style={{ height: 8, borderRadius: radius.pill, background: color.border, overflow: "hidden" }}
      >
        <div style={{ width: `${pct}%`, height: "100%", background: pct === 100 ? "#059669" : color.primary }} />
      </div>
      <span style={{ fontSize: font.small, color: color.textMuted, fontVariantNumeric: "tabular-nums" }}>
        {required ? `${answered} of ${required}` : "—"}
      </span>
    </div>
  );
}

function Status({ ui, row }) {
  const { Badge } = ui;
  return (
    <div style={{ display: "grid", gap: 4, justifyItems: "start" }}>
      <Badge tone={STATUS_TONES[row.status]}>{row.status_label}</Badge>
      {row.email_error ? (
        <span style={{ fontSize: font.small, color: color.danger, fontWeight: font.weight.bold, maxWidth: 260 }}>
          Email failed: {row.email_error}
        </span>
      ) : null}
    </div>
  );
}

function Reminders({ row, inline }) {
  if (inline) {
    const parts = [`Reminders: ${row.reminders_sent || "none"}`];
    if (row.last_reminder_at) parts.push(`last ${ago(row.last_reminder_at)}`);
    if (row.next_reminder_on) parts.push(`next ${shortDate(row.next_reminder_on)}`);
    return <span>{parts.join(" · ")}</span>;
  }
  return (
    <span style={{ fontSize: 13, display: "inline-block", minWidth: 120 }}>
      {row.reminders_sent || "None"}
      {row.last_reminder_at ? <span style={{ color: color.textMuted }}> · {ago(row.last_reminder_at)}</span> : null}
      {row.next_reminder_on ? (
        <div style={{ fontSize: font.small, color: color.textMuted }}>Next {shortDate(row.next_reminder_on)}</div>
      ) : null}
    </span>
  );
}

function Actions({ row, onAction, busy, open }) {
  const [more, setMore] = useState(false);
  const outstanding = OUTSTANDING.has(row.status);
  return (
    <div style={{ display: "flex", gap: space.md, flexWrap: "wrap", alignItems: "center" }}>
      {outstanding ? (
        <LinkButton onClick={() => onAction("remind", row)} disabled={busy || !open}>
          Send reminder
        </LinkButton>
      ) : null}
      {outstanding || row.status === "ready" ? (
        <LinkButton onClick={() => onAction("resend", row)} disabled={busy || !open}>
          {row.status === "ready" ? "Send link" : "Resend link"}
        </LinkButton>
      ) : null}
      <div style={{ position: "relative" }}>
        <LinkButton onClick={() => setMore((m) => !m)} disabled={busy}>
          More {more ? "▴" : "▾"}
        </LinkButton>
        {more ? (
          <div
            role="menu"
            style={{
              position: "absolute",
              right: 0,
              top: "100%",
              zIndex: 5,
              marginTop: 4,
              background: color.surface,
              border: `1px solid ${color.border}`,
              borderRadius: radius.md,
              boxShadow: "0 8px 24px rgba(15,23,42,0.12)",
              padding: space.sm,
              display: "grid",
              gap: 2,
              minWidth: 180,
            }}
          >
            {[
              row.status !== "not_ready" ? ["regenerate", "Regenerate link"] : null,
              row.status === "submitted" ? ["reopen", "Reopen form"] : null,
              ["timeline", "Timeline"],
            ]
              .filter(Boolean)
              .map(([key, label]) => (
                <button
                  key={key}
                  type="button"
                  role="menuitem"
                  onClick={() => {
                    setMore(false);
                    onAction(key, row);
                  }}
                  style={{
                    textAlign: "left",
                    padding: "8px 10px",
                    minHeight: 36,
                    border: 0,
                    borderRadius: radius.sm,
                    background: "transparent",
                    fontSize: 14,
                    color: color.text,
                    cursor: "pointer",
                  }}
                >
                  {label}
                </button>
              ))}
          </div>
        ) : null}
      </div>
    </div>
  );
}

export default function ParticipantList({ ui, rows, selected, onToggle, onAction, busyId, wide, open, notes }) {
  if (!rows.length) {
    return <p style={{ color: color.textMuted, margin: 0 }}>Nobody matches this filter.</p>;
  }
  const check = (row) =>
    OUTSTANDING.has(row.status) ? (
      <input
        type="checkbox"
        aria-label={`Select ${row.name}`}
        checked={selected.includes(row.participant_id)}
        onChange={() => onToggle(row.participant_id)}
        style={{ width: 18, height: 18 }}
      />
    ) : null;
  const note = (row) =>
    notes[row.participant_id] ? (
      <div role="status" style={{ fontSize: 13, color: notes[row.participant_id].tone === "error" ? color.danger : "#065F46", marginTop: 4 }}>
        {notes[row.participant_id].text}
      </div>
    ) : null;

  if (!wide) {
    return (
      <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "grid", gap: space.sm }}>
        {rows.map((row) => (
          <li
            key={row.participant_id}
            style={{
              border: `1px solid ${row.status === "email_failed" ? color.dangerBorder : color.border}`,
              borderRadius: radius.md,
              padding: space.md,
              background: color.surface,
              display: "grid",
              gap: space.sm,
            }}
          >
            <div style={{ display: "flex", gap: space.sm, alignItems: "flex-start" }}>
              {check(row)}
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontWeight: font.weight.bold }}>{row.name}</div>
                <div style={{ fontSize: font.small, color: color.textMuted }}>{row.role}</div>
              </div>
              <Status ui={ui} row={row} />
            </div>
            <Bar answered={row.progress.answered} required={row.progress.required} label={`${row.name}: progress`} />
            <div style={{ fontSize: 13, color: color.textMuted, display: "grid", gap: 2 }}>
              <span>Last activity: {ago(row.last_activity_at)}</span>
              <Reminders row={row} inline />
            </div>
            <Actions row={row} onAction={onAction} busy={busyId === row.participant_id} open={open} />
            {note(row)}
          </li>
        ))}
      </ul>
    );
  }

  const th = { ...ui.tdStyle(), fontWeight: font.weight.heavy, whiteSpace: "nowrap", textAlign: "left" };
  return (
    <div style={ui.tableWrapStyle()}>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: font.body }}>
        <thead>
          <tr style={{ background: color.surfaceMuted }}>
            <th style={th} scope="col">
              <span style={{ position: "absolute", width: 1, height: 1, overflow: "hidden", clip: "rect(0 0 0 0)" }}>Select</span>
            </th>
            {["Participant", "Status", "Progress", "Last activity", "Reminders", "Actions"].map((h) => (
              <th key={h} style={th} scope="col">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr
              key={row.participant_id}
              style={{ borderTop: `1px solid ${color.border}`, background: row.status === "email_failed" ? "#FEF2F2" : undefined }}
            >
              <td style={ui.tdStyle()}>{check(row)}</td>
              <td style={ui.tdStyle()}>
                <div style={{ fontWeight: font.weight.bold, whiteSpace: "nowrap" }}>{row.name}</div>
                <div style={{ fontSize: font.small, color: color.textMuted }}>{row.role}</div>
              </td>
              <td style={ui.tdStyle()}>
                <Status ui={ui} row={row} />
              </td>
              <td style={ui.tdStyle()}>
                <Bar answered={row.progress.answered} required={row.progress.required} label={`${row.name}: progress`} />
              </td>
              <td style={{ ...ui.tdStyle(), whiteSpace: "nowrap", fontSize: 13 }}>{ago(row.last_activity_at)}</td>
              <td style={ui.tdStyle()}>
                <Reminders row={row} />
              </td>
              <td style={ui.tdStyle()}>
                <Actions row={row} onAction={onAction} busy={busyId === row.participant_id} open={open} />
                {note(row)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
