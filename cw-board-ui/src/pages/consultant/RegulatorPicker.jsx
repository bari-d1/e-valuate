import React, { useState } from "react";
import { REGULATOR_GROUPS, REGULATOR_CODES } from "../../data/nigerianRegulators.js";
import { color, font, radius, space } from "../../theme.js";

// Split "NAICOM, FRC" into ["NAICOM", "FRC"]
function splitList(text) {
  return String(text || "")
    .split(",")
    .map((x) => x.trim())
    .filter(Boolean);
}

// Match a saved value to a listed regulator code, ignoring case
function canonicalCode(token) {
  return REGULATOR_CODES.find((c) => c.toLowerCase() === token.toLowerCase()) || null;
}

/**
 * Regulator selection for an evaluation.
 * Reads and writes the same comma-separated value the create form already sends,
 * so saved evaluations and the API are unchanged. Unlisted regulators go in "Other".
 */
export default function RegulatorPicker({ value, onChange, disabled }) {
  const tokens = splitList(value);
  const selected = new Set(tokens.map(canonicalCode).filter(Boolean));
  const others = tokens.filter((t) => !canonicalCode(t));

  // Local text so typing "NAFDAC, " isn't reformatted mid-keystroke
  const [otherText, setOtherText] = useState(others.join(", "));
  const [prevValue, setPrevValue] = useState(value);
  if (value !== prevValue) {
    setPrevValue(value);
    if (!String(value || "").trim()) setOtherText(""); // form was reset
  }

  const emit = (nextSelected, nextOtherText) => {
    const listed = REGULATOR_CODES.filter((c) => nextSelected.has(c)); // keep list order
    onChange([...listed, ...splitList(nextOtherText)].join(", "));
  };

  const toggle = (code) => {
    const next = new Set(selected);
    if (next.has(code)) next.delete(code);
    else next.add(code);
    emit(next, otherText);
  };

  return (
    <fieldset style={{ margin: 0, padding: 0, border: 0, minWidth: 0 }}>
      <legend style={{ padding: 0, fontSize: 13, fontWeight: font.weight.bold, color: color.text }}>Regulators</legend>
      <div style={{ marginTop: 2, fontSize: font.small, color: color.textMuted }}>
        Tick every regulator whose rules apply to this client.
      </div>

      {REGULATOR_GROUPS.map((g) => (
        <div key={g.group} style={{ marginTop: space.md }}>
          <div
            style={{
              fontSize: 11,
              fontWeight: font.weight.heavy,
              letterSpacing: 0.6,
              textTransform: "uppercase",
              color: color.textMuted,
            }}
          >
            {g.group}
          </div>
          <div
            style={{
              marginTop: 6,
              display: "grid",
              gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))",
              gap: space.sm,
            }}
          >
            {g.items.map((r) => {
              const on = selected.has(r.code);
              return (
                <label
                  key={r.code}
                  style={{
                    display: "flex",
                    gap: 10,
                    alignItems: "flex-start",
                    padding: "8px 10px",
                    borderRadius: radius.sm,
                    border: `1px solid ${on ? color.primarySoftBorder : color.border}`,
                    background: on ? color.primarySoft : color.surface,
                    cursor: disabled ? "not-allowed" : "pointer",
                  }}
                >
                  <input
                    type="checkbox"
                    checked={on}
                    disabled={disabled}
                    onChange={() => toggle(r.code)}
                    style={{ marginTop: 3 }}
                  />
                  <span>
                    <span style={{ fontWeight: font.weight.bold, color: color.text }}>{r.code}</span>
                    <span style={{ color: color.text }}> — {r.name}</span>
                    {r.note ? (
                      <span style={{ display: "block", fontSize: font.small, color: color.textMuted }}>{r.note}</span>
                    ) : null}
                  </span>
                </label>
              );
            })}
          </div>
        </div>
      ))}

      <div style={{ marginTop: space.md }}>
        <label htmlFor="regulators-other" style={{ fontSize: 13, fontWeight: font.weight.bold, color: color.text }}>
          Other regulators
        </label>
        <input
          id="regulators-other"
          value={otherText}
          disabled={disabled}
          onChange={(e) => {
            setOtherText(e.target.value);
            emit(selected, e.target.value);
          }}
          placeholder="Not in the list? Type them here, separated by commas"
          autoComplete="off"
          spellCheck={false}
          style={{
            display: "block",
            width: "100%",
            marginTop: 6,
            padding: "10px 12px",
            fontSize: font.body,
            border: `1px solid ${color.borderStrong}`,
            borderRadius: radius.sm,
          }}
        />
      </div>

      <div style={{ marginTop: space.sm, fontSize: font.small, color: color.textMuted }} aria-live="polite">
        {tokens.length ? `Selected: ${tokens.join(", ")}` : "None selected"}
      </div>
    </fieldset>
  );
}
