import React, { useEffect, useMemo, useState } from "react";
import { questionBankApi } from "../../../api/questionBankApi.js";
import { color, font, radius, space } from "../../../theme.js";
import { LinkButton, Notice } from "../companies/shared.jsx";
import { inputCss } from "../companies/helpers.js";
import { ANSWER_TYPE_LABELS } from "../questionBank/bankHelpers.js";
import { shortName } from "./reviewHelpers.js";

/**
 * The core peer grid as one compact block: each statement is rated for every colleague.
 * Removing a statement removes it for all colleagues; "Show as rows" lists each cell for finer edits.
 */
export function PeerGrid({ ui, questions, editable, onActMany, onExpand }) {
  const { Badge } = ui;
  const statements = useMemo(() => {
    const by = new Map();
    questions.forEach((q) => {
      const s = by.get(q.bank_item_code) || { code: q.bank_item_code, text: q.bank_text || q.text, cells: [] };
      s.cells.push(q);
      by.set(q.bank_item_code, s);
    });
    return [...by.values()];
  }, [questions]);
  const colleagues = useMemo(() => {
    const seen = new Map();
    questions.forEach((q) => q.subject && seen.set(q.subject.id, q.subject.label));
    return [...seen.entries()];
  }, [questions]);

  return (
    <li style={{ listStyle: "none", padding: space.md, borderRadius: radius.md, border: `1px solid ${color.border}`, background: color.surface }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: space.sm, flexWrap: "wrap", alignItems: "baseline" }}>
        <div>
          <strong>Statements about colleagues</strong>{" "}
          <span style={{ fontSize: 13, color: color.textMuted }}>
            · {statements.length} statements × {colleagues.length} colleagues, rated in one grid
          </span>
        </div>
        <LinkButton onClick={onExpand}>Show as rows</LinkButton>
      </div>
      <div style={{ overflowX: "auto", marginTop: space.sm }}>
        <table style={{ borderCollapse: "collapse", fontSize: 13, minWidth: 480, width: "100%" }}>
          <thead>
            <tr style={{ textAlign: "left", color: color.textMuted }}>
              <th scope="col" style={{ padding: "4px 6px", fontWeight: font.weight.bold }}>
                Statement
              </th>
              {colleagues.map(([id, label]) => (
                <th key={id} scope="col" style={{ padding: "4px 6px", fontWeight: font.weight.bold, whiteSpace: "nowrap" }} title={label}>
                  {shortName(label)}
                </th>
              ))}
              {editable ? <th scope="col" style={{ padding: "4px 6px" }}><span style={{ position: "absolute", width: 1, height: 1, overflow: "hidden", clip: "rect(0 0 0 0)" }}>Actions</span></th> : null}
            </tr>
          </thead>
          <tbody>
            {statements.map((s) => {
              const allRemoved = s.cells.every((c) => c.status === "removed");
              return (
                <tr key={s.code} style={{ borderTop: `1px solid ${color.border}`, opacity: allRemoved ? 0.6 : 1 }}>
                  <td style={{ padding: "6px", textDecoration: allRemoved ? "line-through" : "none" }}>
                    {s.text} <span style={{ fontSize: font.small, color: color.textMuted }}>{s.code}</span>
                  </td>
                  {colleagues.map(([id]) => {
                    const cell = s.cells.find((c) => c.subject?.id === id);
                    return (
                      <td key={id} style={{ padding: "6px", textAlign: "center" }}>
                        {!cell ? "—" : cell.status === "removed" ? <Badge tone="gray">off</Badge> : "✓"}
                      </td>
                    );
                  })}
                  {editable ? (
                    <td style={{ padding: "6px", whiteSpace: "nowrap" }}>
                      {allRemoved ? (
                        <LinkButton onClick={() => onActMany(s.cells, "restore")}>Restore</LinkButton>
                      ) : (
                        <LinkButton danger onClick={() => onActMany(s.cells.filter((c) => c.status !== "removed"), "remove")}>
                          Remove
                        </LinkButton>
                      )}
                    </td>
                  ) : null}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </li>
  );
}

/** Add a question: from the approved bank (search, pick a subject) or written by the consultant with its tags. */
export function AddQuestion({ ui, evalId, participantId, subjects, meta, onAdded, existing }) {
  const { Button } = ui;
  const [mode, setMode] = useState("bank");
  const [search, setSearch] = useState("");
  const [items, setItems] = useState([]);
  const [item, setItem] = useState(null);
  const [subjectId, setSubjectId] = useState("");
  const [form, setForm] = useState({ text: "", answer_type: "rating", theme_code: "", evidence_source_code: "", options: "" });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (mode !== "bank") return undefined;
    let alive = true;
    const t = setTimeout(async () => {
      try {
        const r = await questionBankApi.searchBank(evalId, search);
        if (alive) setItems(r.items);
      } catch (e) {
        if (alive) setError(e.message);
      }
    }, 250);
    return () => {
      alive = false;
      clearTimeout(t);
    };
  }, [evalId, search, mode]);

  // Subjects the item fits that don't already have it in this set ("CODE|subject id" in existing)
  const fitting = item ? subjects.filter((s) => item.subject_types.includes(s.type) && !existing?.has(`${item.code}|${s.id}`)) : subjects;
  const submit = async (body) => {
    setBusy(true);
    setError("");
    try {
      await questionBankApi.addQuestion(evalId, participantId, body);
      setItem(null);
      setSubjectId("");
      setForm({ text: "", answer_type: "rating", theme_code: "", evidence_source_code: "", options: "" });
      await onAdded();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));
  const choice = form.answer_type === "single_select" || form.answer_type === "multi_select";

  return (
    <div style={{ display: "grid", gap: space.md }}>
      <div role="radiogroup" aria-label="Where the question comes from" style={{ display: "flex", gap: space.md, fontSize: 13 }}>
        {[["bank", "From the bank"], ["written", "Write your own"]].map(([k, l]) => (
          <label key={k} style={{ display: "flex", gap: 6, alignItems: "center", cursor: "pointer" }}>
            <input type="radio" name={`add-${participantId}`} checked={mode === k} onChange={() => setMode(k)} />
            {l}
          </label>
        ))}
      </div>

      {mode === "bank" ? (
        <div style={{ display: "grid", gap: space.sm }}>
          <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search the bank by code or wording" aria-label="Search the bank" style={inputCss()} />
          <ul style={{ listStyle: "none", margin: 0, padding: 0, maxHeight: 240, overflowY: "auto", border: `1px solid ${color.border}`, borderRadius: radius.sm }}>
            {items.map((i) => (
              <li key={i.id} style={{ borderTop: `1px solid ${color.border}` }}>
                <button
                  type="button"
                  onClick={() => { setItem(i); setSubjectId(""); }}
                  aria-pressed={item?.id === i.id}
                  style={{ display: "block", width: "100%", textAlign: "left", padding: space.sm, border: 0, cursor: "pointer", background: item?.id === i.id ? color.primarySoft : "transparent", fontSize: 13, color: color.text }}
                >
                  <span style={{ fontSize: font.small, color: color.textMuted }}>{i.code} · {ANSWER_TYPE_LABELS[i.answer_type]}</span>
                  <div>{i.text}</div>
                </button>
              </li>
            ))}
            {!items.length ? <li style={{ padding: space.sm, fontSize: 13, color: color.textMuted }}>No matching items.</li> : null}
          </ul>
          {item && !fitting.length ? (
            <p style={{ margin: 0, fontSize: 13, color: color.textMuted }}>{item.code} is already in this set for everyone it can be about.</p>
          ) : item ? (
            <div style={{ display: "flex", gap: space.sm, flexWrap: "wrap", alignItems: "end" }}>
              <label style={{ display: "grid", gap: 4, fontSize: 13, flex: "1 1 240px" }}>
                About
                <select value={subjectId} onChange={(e) => setSubjectId(e.target.value)} style={inputCss()}>
                  <option value="">Choose who or what it's about…</option>
                  {fitting.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.label}
                    </option>
                  ))}
                </select>
              </label>
              <Button disabled={busy || !subjectId} onClick={() => submit({ source: "bank", item_id: item.id, subject_id: subjectId })}>
                Add {item.code}
              </Button>
            </div>
          ) : null}
        </div>
      ) : (
        <div style={{ display: "grid", gap: space.sm, gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))" }}>
          <label style={{ display: "grid", gap: 4, fontSize: 13, gridColumn: "1 / -1" }}>
            Question
            <textarea value={form.text} onChange={set("text")} rows={2} style={{ ...inputCss(), resize: "vertical" }} />
          </label>
          <label style={{ display: "grid", gap: 4, fontSize: 13 }}>
            Answer type
            <select value={form.answer_type} onChange={set("answer_type")} style={inputCss()}>
              {Object.entries(ANSWER_TYPE_LABELS).map(([k, l]) => (
                <option key={k} value={k}>
                  {l}
                </option>
              ))}
            </select>
          </label>
          <label style={{ display: "grid", gap: 4, fontSize: 13 }}>
            About
            <select value={subjectId} onChange={(e) => setSubjectId(e.target.value)} style={inputCss()}>
              <option value="">Choose…</option>
              {subjects.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.label}
                </option>
              ))}
            </select>
          </label>
          <label style={{ display: "grid", gap: 4, fontSize: 13 }}>
            Theme
            <select value={form.theme_code} onChange={set("theme_code")} style={inputCss()}>
              <option value="">Choose…</option>
              {(meta?.themes || []).map((t) => (
                <option key={t.code} value={t.code}>
                  {t.name}
                </option>
              ))}
            </select>
          </label>
          <label style={{ display: "grid", gap: 4, fontSize: 13 }}>
            Evidence source
            <select value={form.evidence_source_code} onChange={set("evidence_source_code")} style={inputCss()}>
              <option value="">Choose…</option>
              {(meta?.evidence_sources || []).map((t) => (
                <option key={t.code} value={t.code}>
                  {t.name}
                </option>
              ))}
            </select>
          </label>
          {choice ? (
            <label style={{ display: "grid", gap: 4, fontSize: 13, gridColumn: "1 / -1" }}>
              Options (one per line)
              <textarea value={form.options} onChange={set("options")} rows={3} style={{ ...inputCss(), resize: "vertical" }} />
            </label>
          ) : null}
          <div style={{ gridColumn: "1 / -1" }}>
            <Button
              disabled={busy || !form.text.trim() || !subjectId || !form.theme_code || !form.evidence_source_code}
              title="Question, subject, theme and evidence source are all needed"
              onClick={() =>
                submit({
                  source: "written",
                  text: form.text,
                  answer_type: form.answer_type,
                  subject_id: subjectId,
                  theme_code: form.theme_code,
                  evidence_source_code: form.evidence_source_code,
                  options: choice ? form.options.split("\n") : null,
                })
              }
            >
              Add question
            </Button>
          </div>
        </div>
      )}
      {error ? <Notice tone="error">{error}</Notice> : null}
    </div>
  );
}
