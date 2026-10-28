import React, { useState } from "react";
import { color, font, radius, space } from "../../../theme.js";
import { fmt } from "./findingsHelpers.js";

/**
 * Charts drawn to scale on a 1 to 5 axis. Each is also readable as text (labels and values are
 * written out), so screen readers and small screens lose nothing.
 */

const AXIS = [1, 2, 3, 4, 5];
const pos = (v) => `${((v - 1) / 4) * 100}%`;

function Axis() {
  return (
    <div aria-hidden="true" style={{ position: "relative", height: 16, marginTop: 2 }}>
      {AXIS.map((v) => (
        <span
          key={v}
          style={{
            position: "absolute",
            left: pos(v),
            transform: v === 1 ? "none" : v === 5 ? "translateX(-100%)" : "translateX(-50%)",
            fontSize: 11,
            color: color.textMuted,
          }}
        >
          {v}
        </span>
      ))}
    </div>
  );
}

function Track({ children, height = 14 }) {
  return (
    <div style={{ position: "relative", height, background: color.surfaceMuted, borderRadius: radius.sm, border: `1px solid ${color.border}` }}>
      {AXIS.slice(1, 4).map((v) => (
        <span key={v} aria-hidden="true" style={{ position: "absolute", left: pos(v), top: 0, bottom: 0, width: 1, background: color.border }} />
      ))}
      {children}
    </div>
  );
}

function Distribution({ dist }) {
  if (!dist) return null;
  const max = Math.max(1, ...Object.values(dist));
  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(5, minmax(0, 1fr))", gap: 4, marginTop: space.xs }}>
      {AXIS.map((v) => (
        <div key={v} style={{ display: "grid", gap: 2, justifyItems: "center", fontSize: 11, color: color.textMuted }}>
          <div style={{ height: 28, width: "60%", display: "flex", alignItems: "flex-end" }}>
            <div style={{ width: "100%", height: `${(dist[String(v)] / max) * 100}%`, minHeight: dist[String(v)] ? 2 : 0, background: color.primary, borderRadius: 2 }} />
          </div>
          <span>
            {v}: {dist[String(v)]}
          </span>
        </div>
      ))}
    </div>
  );
}

/** One horizontal bar per theme (or item): the average on a 1 to 5 axis, rater count and agreement. Tap for the spread of ratings. */
export function ScoreBars({ rows }) {
  const [open, setOpen] = useState(null);
  return (
    <div style={{ display: "grid", gap: space.md }}>
      {rows.map((r) => (
        <div key={r.key}>
          <button
            type="button"
            onClick={() => setOpen(open === r.key ? null : r.key)}
            aria-expanded={open === r.key}
            disabled={!r.distribution}
            style={{ all: "unset", display: "block", width: "100%", cursor: r.distribution ? "pointer" : "default" }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", gap: space.sm, fontSize: 13, flexWrap: "wrap" }}>
              <span style={{ fontWeight: font.weight.bold, color: color.text }}>{r.label}</span>
              <span style={{ color: color.textMuted }}>
                {r.suppressed ? "Not shown" : `${fmt(r.mean)} · ${r.raters} rater${r.raters === 1 ? "" : "s"} · ${r.consensus}`}
              </span>
            </div>
            <div style={{ marginTop: 4 }}>
              <Track>
                {!r.suppressed && r.mean ? (
                  <div
                    style={{
                      position: "absolute",
                      left: 0,
                      top: 2,
                      bottom: 2,
                      width: pos(r.mean),
                      minWidth: 3,
                      background: r.mean <= 2.5 ? color.danger : r.mean >= 4.2 ? "#059669" : color.primary,
                      borderRadius: radius.sm,
                    }}
                  />
                ) : null}
              </Track>
            </div>
          </button>
          {r.suppressed ? <div style={{ fontSize: 12, color: color.textMuted, marginTop: 2 }}>{r.suppressed}</div> : null}
          {open === r.key ? <Distribution dist={r.distribution} /> : null}
        </div>
      ))}
      {rows.length ? <Axis /> : null}
    </div>
  );
}

/** Self-rating against the colleagues' average for each core statement. Gaps of 1 point or more are flagged. */
export function SelfPeerChart({ rows }) {
  return (
    <div style={{ display: "grid", gap: space.md }}>
      <div style={{ display: "flex", gap: space.md, fontSize: 12, color: color.textMuted, flexWrap: "wrap" }}>
        <span>
          <span aria-hidden="true" style={{ display: "inline-block", width: 10, height: 10, borderRadius: radius.pill, background: color.primary, marginRight: 4 }} />
          Colleagues' average
        </span>
        <span>
          <span aria-hidden="true" style={{ display: "inline-block", width: 10, height: 10, borderRadius: radius.pill, border: `2px solid ${color.text}`, background: color.surface, marginRight: 4 }} />
          Self-rating
        </span>
      </div>
      {rows.map((r) => {
        const lo = r.peer_mean !== null && r.self !== null ? Math.min(r.peer_mean, r.self) : null;
        const hi = r.peer_mean !== null && r.self !== null ? Math.max(r.peer_mean, r.self) : null;
        return (
          <div key={r.code}>
            <div style={{ display: "flex", justifyContent: "space-between", gap: space.sm, fontSize: 13, flexWrap: "wrap" }}>
              <span style={{ fontWeight: font.weight.bold }}>{r.statement}</span>
              <span style={{ color: r.flagged ? color.danger : color.textMuted, fontWeight: r.flagged ? font.weight.bold : font.weight.regular }}>
                Self {r.self ?? "—"} · colleagues {r.suppressed ? "not shown" : `${fmt(r.peer_mean)} (${r.peer_raters})`}
                {r.gap !== null && r.gap !== undefined ? ` · gap ${r.gap > 0 ? "+" : ""}${r.gap.toFixed(1)}` : ""}
              </span>
            </div>
            <div style={{ marginTop: 6 }}>
              <Track height={18}>
                {lo !== null ? (
                  <span
                    aria-hidden="true"
                    style={{ position: "absolute", left: pos(lo), width: `calc(${pos(hi)} - ${pos(lo)})`, top: 8, height: 2, background: r.flagged ? color.danger : color.borderStrong }}
                  />
                ) : null}
                {r.peer_mean !== null && !r.suppressed ? (
                  <span
                    aria-hidden="true"
                    style={{ position: "absolute", left: pos(r.peer_mean), top: 3, width: 12, height: 12, marginLeft: -6, borderRadius: radius.pill, background: color.primary }}
                  />
                ) : null}
                {r.self !== null ? (
                  <span
                    aria-hidden="true"
                    style={{ position: "absolute", left: pos(r.self), top: 2, width: 14, height: 14, marginLeft: -7, borderRadius: radius.pill, border: `2px solid ${color.text}`, background: color.surface, boxSizing: "border-box" }}
                  />
                ) : null}
              </Track>
            </div>
            {r.suppressed ? <div style={{ fontSize: 12, color: color.textMuted, marginTop: 2 }}>{r.suppressed}</div> : null}
          </div>
        );
      })}
      <Axis />
    </div>
  );
}
