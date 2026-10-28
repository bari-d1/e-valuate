import React, { useLayoutEffect, useRef, useState } from "react";
import { color, font, radius, space } from "../../theme.js";
import { answerText, hasAnswer } from "./formHelpers.js";

/**
 * Answer controls for the participant form. Native radios, checkboxes and selects so keyboard
 * and screen reader support come for free; each question is a fieldset whose legend is its text.
 */

const TAP = 48; // minimum tap target height
const SR_ONLY = { position: "absolute", width: 1, height: 1, overflow: "hidden", clip: "rect(0 0 0 0)", whiteSpace: "nowrap" };

function optionStyle(selected, { compact = false } = {}) {
  return {
    display: "flex",
    flexDirection: compact ? "column" : "row",
    alignItems: "center",
    justifyContent: compact ? "flex-start" : "flex-start",
    gap: compact ? 4 : space.sm,
    minHeight: TAP,
    padding: compact ? "8px 4px" : "10px 12px",
    borderRadius: radius.md,
    border: `1.5px solid ${selected ? color.primary : color.borderStrong}`,
    background: selected ? color.primarySoft : color.surface,
    color: color.text,
    fontWeight: selected ? font.weight.bold : font.weight.regular,
    fontSize: compact ? 13 : 15,
    lineHeight: 1.25,
    textAlign: compact ? "center" : "left",
    cursor: "pointer",
    minWidth: 0,
  };
}

const radioStyle = { width: 20, height: 20, margin: 0, flex: "none", accentColor: color.primary };

/** A set of single-choice options as large tap targets. */
export function Choices({ name, options, value, onChange, columns, compact }) {
  return (
    <div
      style={{
        display: "grid",
        gap: space.sm,
        gridTemplateColumns: columns ? `repeat(${columns}, minmax(0, 1fr))` : "minmax(0, 1fr)",
      }}
    >
      {options.map((o) => {
        const selected = value === o.value;
        return (
          <label key={String(o.value)} style={optionStyle(selected, { compact })}>
            <input
              type="radio"
              name={name}
              value={String(o.value)}
              checked={selected}
              onChange={() => onChange(o.value)}
              style={radioStyle}
            />
            <span style={{ display: "grid", gap: 2 }}>
              {o.number !== undefined ? <span style={{ fontWeight: font.weight.heavy, fontSize: 16 }}>{o.number}</span> : null}
              <span>{o.label}</span>
            </span>
          </label>
        );
      })}
    </div>
  );
}

function ratingOptions(scale) {
  const opts = (scale?.points || []).map((p) => ({ value: p.value, number: p.value, label: p.label || "" }));
  return opts;
}

/** A rating: the scale's points side by side with their labels, plus "Don't know" when allowed. */
export function Rating({ name, scale, value, onChange }) {
  const points = ratingOptions(scale);
  return (
    <div style={{ display: "grid", gap: space.sm }}>
      <Choices name={name} options={points} value={value} onChange={onChange} columns={points.length} compact />
      {scale?.dont_know ? (
        <Choices name={name} options={[{ value: "dont_know", label: "Don't know" }]} value={value} onChange={onChange} />
      ) : null}
    </div>
  );
}

/** A text box that grows as you type. */
export function GrowingText({ id, value, onChange, placeholder, describedBy, rows = 3, maxLength = 5000 }) {
  const ref = useRef(null);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.max(el.scrollHeight, rows * 24 + 20)}px`;
  }, [value, rows]);
  return (
    <textarea
      id={id}
      ref={ref}
      value={value || ""}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
      aria-describedby={describedBy}
      maxLength={maxLength}
      rows={rows}
      style={{
        width: "100%",
        padding: "12px 14px",
        borderRadius: radius.md,
        border: `1.5px solid ${color.borderStrong}`,
        fontSize: 16, // 16px stops phones zooming in on focus
        lineHeight: 1.5,
        resize: "none",
        overflow: "hidden",
      }}
    />
  );
}

function Checks({ name, options, value, onChange }) {
  const chosen = Array.isArray(value) ? value : [];
  const toggle = (o) => onChange(chosen.includes(o) ? chosen.filter((x) => x !== o) : [...chosen, o]);
  return (
    <div style={{ display: "grid", gap: space.sm }}>
      {options.map((o) => {
        const selected = chosen.includes(o);
        return (
          <label key={o} style={optionStyle(selected)}>
            <input type="checkbox" name={name} checked={selected} onChange={() => toggle(o)} style={radioStyle} />
            <span>{o}</span>
          </label>
        );
      })}
    </div>
  );
}

function Confirm({ q, value, onChange }) {
  const v = value || {};
  const id = `fix-${q.id}`;
  return (
    <div style={{ display: "grid", gap: space.md }}>
      <div style={{ padding: space.md, borderRadius: radius.md, background: color.surfaceMuted, border: `1px solid ${color.border}` }}>
        <div style={{ fontSize: 13, color: color.textMuted }}>What we have on record{q.confirm.label ? ` (${q.confirm.label.toLowerCase()})` : ""}</div>
        <div style={{ fontWeight: font.weight.bold, fontSize: 16, whiteSpace: "pre-wrap" }}>{q.confirm.value}</div>
      </div>
      <Choices
        name={`q-${q.id}`}
        columns={2}
        options={[
          { value: "correct", label: "Correct" },
          { value: "needs_updating", label: "Needs updating" },
        ]}
        value={v.status}
        onChange={(status) => onChange({ status, correction: status === "needs_updating" ? v.correction || "" : "" })}
      />
      {v.status === "needs_updating" ? (
        <div style={{ display: "grid", gap: 6 }}>
          <label htmlFor={id} style={{ fontSize: 14, fontWeight: font.weight.bold }}>
            What should it say? <span style={{ fontWeight: font.weight.regular, color: color.textMuted }}>(optional)</span>
          </label>
          <GrowingText id={id} rows={2} maxLength={2000} value={v.correction} onChange={(t) => onChange({ status: v.status, correction: t })} />
          <div style={{ fontSize: 13, color: color.textMuted }}>Your consultant will check this before anything on record changes.</div>
        </div>
      ) : null}
    </div>
  );
}

/** One question: "About" line, wording, optional tag, the control (or the answer when read-only), and any error. */
export function Question({ q, value, onChange, error, readOnly, followUp }) {
  const name = `q-${q.id}`;
  const hintId = `${name}-hint`;
  const optional = !q.required && !readOnly;
  let control = null;
  if (readOnly) {
    control = (
      <div style={{ fontSize: 15, fontWeight: hasAnswer(q, value) ? font.weight.bold : font.weight.regular, color: hasAnswer(q, value) ? color.text : color.textMuted }}>
        {answerText(q, value)}
      </div>
    );
  } else if (q.confirm) {
    control = <Confirm q={q} value={value} onChange={onChange} />;
  } else if (q.answer_type === "rating") {
    control = <Rating name={name} scale={q.scale} value={value} onChange={onChange} />;
  } else if (q.answer_type === "yesno") {
    control = (
      <Choices name={name} columns={2} value={value} onChange={onChange} options={[{ value: "yes", label: "Yes" }, { value: "no", label: "No" }]} />
    );
  } else if (q.answer_type === "single_select") {
    control = <Choices name={name} value={value} onChange={onChange} options={(q.options || []).map((o) => ({ value: o, label: o }))} />;
  } else if (q.answer_type === "multi_select") {
    control = <Checks name={name} options={q.options || []} value={value} onChange={onChange} />;
  } else {
    control = <GrowingText id={`${name}-text`} value={value} onChange={onChange} describedBy={optional ? hintId : undefined} />;
  }
  const isText = !readOnly && !q.confirm && q.answer_type === "comment";
  const Wrapper = isText ? "div" : "fieldset";
  const Title = isText ? "label" : "legend";
  return (
    <Wrapper
      id={name}
      style={{
        margin: 0,
        border: 0,
        padding: followUp ? `${space.md}px 0 0 ${space.md}px` : 0,
        borderLeft: followUp ? `3px solid ${color.primarySoftBorder}` : 0,
        minWidth: 0,
        display: "grid",
        gap: space.sm,
        scrollMarginTop: 96,
      }}
    >
      <Title htmlFor={isText ? `${name}-text` : undefined} style={{ padding: 0, display: "grid", gap: 4 }}>
        {q.about ? (
          <span style={{ fontSize: 13, fontWeight: font.weight.bold, color: color.primaryText }}>About: {q.about}</span>
        ) : null}
        {q.srAbout ? <span style={SR_ONLY}>About {q.srAbout}:</span> : null}
        <span style={{ fontSize: 17, fontWeight: font.weight.bold, lineHeight: 1.4, color: color.text }}>
          {q.text}
          {optional ? (
            <span id={hintId} style={{ display: "block", marginTop: 2, fontSize: 14, fontWeight: font.weight.regular, color: color.textMuted }}>
              Optional
            </span>
          ) : null}
        </span>
      </Title>
      {control}
      {error ? (
        <div role="alert" style={{ fontSize: 14, color: color.danger, fontWeight: font.weight.bold }}>
          {error}
        </div>
      ) : null}
    </Wrapper>
  );
}

/**
 * The core peer grid. Wide screens: a table, statements by colleagues, one rating select per cell.
 * Phones: one colleague at a time with every statement, and "Colleague 2 of 5". Never scrolls sideways.
 */
export function PeerGrid({ grid, answers, onAnswer, readOnly, wide, errors }) {
  const [index, setIndex] = useState(0);
  const cols = grid.colleagues;
  const points = grid.scale?.points || [];
  const labelFor = (v) => (v === "dont_know" ? "Don't know" : points.find((p) => p.value === v)?.label || "");
  const doneFor = (c) => grid.statements.every((s) => !s.cells[c.id] || hasAnswer({}, answers[s.cells[c.id]]));

  const intro = (
    <p style={{ margin: 0, color: color.textMuted, fontSize: 15 }}>
      Rate each colleague on each statement.{" "}
      {points.length ? `${points[0].value} is ${points[0].label?.toLowerCase()}, ${points[points.length - 1].value} is ${points[points.length - 1].label?.toLowerCase()}.` : ""}
    </p>
  );

  if (wide) {
    return (
      <div style={{ display: "grid", gap: space.md }} id="q-peer-grid">
        <h3 style={{ margin: 0, fontSize: 18 }}>Your colleagues</h3>
        {intro}
        <table style={{ width: "100%", borderCollapse: "collapse", tableLayout: "fixed", fontSize: 14 }}>
          <caption style={SR_ONLY}>
            Ratings of each colleague on each statement
          </caption>
          <thead>
            <tr>
              <th scope="col" style={{ textAlign: "left", padding: "8px 6px", width: "26%", color: color.textMuted, fontWeight: font.weight.bold }}>
                Statement
              </th>
              {cols.map((c) => (
                <th key={c.id} scope="col" style={{ textAlign: "left", padding: "8px 6px", fontWeight: font.weight.bold, overflowWrap: "anywhere" }}>
                  {c.name}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {grid.statements.map((s) => (
              <tr key={s.key} style={{ borderTop: `1px solid ${color.border}` }}>
                <th scope="row" style={{ textAlign: "left", padding: "10px 6px", fontWeight: font.weight.medium, verticalAlign: "middle" }}>
                  {s.text}
                </th>
                {cols.map((c) => {
                  const qid = s.cells[c.id];
                  if (!qid) {
                    return (
                      <td key={c.id} style={{ padding: 6, color: color.textMuted, fontSize: 13 }}>
                        Not asked
                      </td>
                    );
                  }
                  const v = answers[qid];
                  return (
                    <td key={c.id} style={{ padding: 6 }} id={`q-${qid}`}>
                      {readOnly ? (
                        <span style={{ fontWeight: font.weight.bold }}>{v === undefined || v === null ? "—" : v === "dont_know" ? "Don't know" : `${v} · ${labelFor(v)}`}</span>
                      ) : (
                        <select
                          aria-label={`${c.name}: ${s.text}`}
                          value={v === undefined || v === null ? "" : String(v)}
                          onChange={(e) => onAnswer(qid, e.target.value === "" ? null : e.target.value === "dont_know" ? "dont_know" : Number(e.target.value))}
                          style={{
                            width: "100%",
                            minHeight: 44,
                            padding: "6px 2px",
                            borderRadius: radius.sm,
                            border: `1.5px solid ${errors?.[qid] ? color.danger : v === undefined || v === null ? color.borderStrong : color.primary}`,
                            background: v === undefined || v === null ? color.surface : color.primarySoft,
                            fontSize: 13,
                          }}
                        >
                          <option value="">Choose…</option>
                          {points.map((p) => (
                            <option key={p.value} value={p.value}>
                              {p.value} · {p.label}
                            </option>
                          ))}
                          {grid.scale?.dont_know ? <option value="dont_know">Don't know</option> : null}
                        </select>
                      )}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }

  const c = cols[Math.min(index, cols.length - 1)];
  return (
    <div style={{ display: "grid", gap: space.md }} id="q-peer-grid">
      <h3 style={{ margin: 0, fontSize: 18 }}>Your colleagues</h3>
      {intro}
      <div
        style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: space.sm, padding: space.md, borderRadius: radius.md, background: color.surfaceMuted, border: `1px solid ${color.border}` }}
      >
        <div>
          <div style={{ fontSize: 13, color: color.textMuted }} aria-live="polite">
            Colleague {index + 1} of {cols.length}
          </div>
          <div style={{ fontWeight: font.weight.heavy, fontSize: 18 }}>{c.name}</div>
        </div>
        <span style={{ fontSize: 13, color: doneFor(c) ? "#065F46" : color.textMuted, fontWeight: font.weight.bold }}>
          {doneFor(c) ? "Done" : ""}
        </span>
      </div>
      {grid.statements.map((s) => {
        const qid = s.cells[c.id];
        if (!qid) return null;
        return (
          <Question
            key={`${c.id}-${s.key}`}
            q={{ id: qid, text: s.text, answer_type: "rating", scale: grid.scale, required: grid.required, about: null, srAbout: c.name }}
            value={answers[qid]}
            onChange={(v) => onAnswer(qid, v)}
            readOnly={readOnly}
            error={errors?.[qid]}
          />
        );
      })}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: space.sm }}>
        <NavButton disabled={index === 0} onClick={() => setIndex((i) => i - 1)}>
          ← Previous colleague
        </NavButton>
        <NavButton disabled={index >= cols.length - 1} onClick={() => setIndex((i) => i + 1)} primary>
          Next colleague →
        </NavButton>
      </div>
    </div>
  );
}

export function NavButton({ children, onClick, disabled, primary, type = "button", style }) {
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      style={{
        minHeight: TAP,
        padding: "12px 18px",
        borderRadius: radius.md,
        border: `1.5px solid ${disabled ? color.border : primary ? color.primaryBorder : color.borderStrong}`,
        background: disabled ? color.disabledBg : primary ? color.primary : color.surface,
        color: disabled ? color.disabledText : primary ? "#FFFFFF" : color.text,
        fontWeight: font.weight.bold,
        fontSize: 15,
        cursor: disabled ? "not-allowed" : "pointer",
        ...style,
      }}
    >
      {children}
    </button>
  );
}
