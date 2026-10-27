import React, { useCallback, useEffect, useId, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { questionBankApi } from "../../../api/questionBankApi.js";
import { color, font, radius, space } from "../../../theme.js";
import { formatDateTime } from "../../../utils/format.js";
import { LinkButton, Notice, Panel, SectionTitle } from "../companies/shared.jsx";
import { inputCss, useAsync } from "../companies/helpers.js";
import {
  ANSWER_TYPE_LABELS,
  BINDING_LABELS,
  STATUS_TONE,
  TAG_LABELS,
  nameOf,
  placeholdersIn,
  useBankMeta,
} from "./bankHelpers.js";

const SELECT_TYPES = ["single_select", "multi_select"];

function ErrorList({ errors }) {
  if (!errors?.length) return null;
  return (
    <Notice tone="error">
      <ul style={{ margin: 0, paddingLeft: 18 }}>
        {errors.map((e) => (
          <li key={e}>{e}</li>
        ))}
      </ul>
    </Notice>
  );
}

/** JSON rule editor, checked against the server's rule validator as you type. */
function RuleEditor({ label, hint, initial, initialDescription, disabled, onChange }) {
  const [text, setText] = useState(initial ? JSON.stringify(initial, null, 2) : "");
  const [state, setState] = useState({ errors: [], description: initialDescription || "always" });
  const timer = useRef(null);
  const id = `rule-${useId()}`;

  function handle(value) {
    setText(value);
    clearTimeout(timer.current);
    if (!value.trim()) {
      setState({ errors: [], description: "always" });
      onChange(null, true);
      return;
    }
    let rule;
    try {
      rule = JSON.parse(value);
    } catch (e) {
      setState({ errors: [`Not valid JSON: ${e.message}`], description: "" });
      onChange(null, false);
      return;
    }
    onChange(rule, false);
    setState((s) => ({ ...s, checking: true }));
    timer.current = setTimeout(async () => {
      try {
        const r = await questionBankApi.validateRule(rule);
        setState({ errors: r.errors, description: r.description || "" });
        onChange(rule, r.valid);
      } catch (e) {
        setState({ errors: [e.message], description: "" });
      }
    }, 300);
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      <label htmlFor={id} style={{ fontSize: 13, fontWeight: font.weight.bold, color: color.text }}>
        {label}
      </label>
      <textarea
        id={id}
        value={text}
        disabled={disabled}
        onChange={(e) => handle(e.target.value)}
        spellCheck={false}
        rows={Math.min(14, Math.max(3, text.split("\n").length))}
        placeholder="Empty means always"
        aria-describedby={`${id}-status`}
        style={inputCss({ fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace", fontSize: 12.5 })}
      />
      <div id={`${id}-status`} aria-live="polite">
        {state.errors.length ? (
          <ErrorList errors={state.errors} />
        ) : (
          <div style={{ fontSize: 13, color: color.textMuted }}>
            {state.checking ? "Checking…" : <>Reads as: <span style={{ color: color.text }}>{state.description}</span></>}
          </div>
        )}
      </div>
      {hint ? <div style={{ fontSize: font.small, color: color.textMuted }}>{hint}</div> : null}
    </div>
  );
}

function scalePreset(meta, scale) {
  if (!scale) return "quality_5";
  const match = Object.entries(meta?.scales || {}).find(
    ([, s]) => s.min === scale.min && s.max === scale.max && JSON.stringify(s.labels) === JSON.stringify(scale.labels)
  );
  return match ? match[0] : "custom";
}

function toDraft(item, meta) {
  return {
    text: item.text,
    answer_type: item.answer_type,
    options: (item.options || []).join("\n"),
    scale_preset: scalePreset(meta, item.scale),
    dont_know: !!item.scale?.dont_know,
    custom_scale: item.scale,
    subject_types: item.subject_types,
    subject_binding: item.subject_binding,
    theme_code: item.theme_code,
    evidence_source_code: item.evidence_source_code,
    known_from: item.known_from || "",
    known_from_behaviour: item.known_from_behaviour,
    guidance: item.guidance || "",
    review_notes: item.review_notes || "",
    respondent_rule: item.respondent_rule,
    activation_rule: item.activation_rule,
    tags_reviewed: false,
  };
}

function toPayload(d, meta, item) {
  const options = SELECT_TYPES.includes(d.answer_type)
    ? d.options.split("\n").map((o) => o.trim()).filter(Boolean)
    : null;
  let scale = null;
  if (d.answer_type === "rating") {
    scale = d.scale_preset === "custom" ? { ...d.custom_scale } : { ...meta.scales[d.scale_preset] };
    if (d.dont_know) scale.dont_know = true;
    else delete scale.dont_know;
  }
  const tagNotes = { ...(item.tag_notes || {}) };
  if (d.tags_reviewed) Object.keys(tagNotes).forEach((k) => (tagNotes[k] = { ...tagNotes[k], status: "confirmed" }));
  return {
    text: d.text,
    answer_type: d.answer_type,
    options,
    scale,
    subject_types: d.subject_types,
    subject_binding: d.subject_binding,
    theme_code: d.theme_code,
    evidence_source_code: d.evidence_source_code,
    known_from: d.known_from || null,
    known_from_behaviour: d.known_from_behaviour,
    placeholders: placeholdersIn(d.text, ...(options || [])),
    guidance: d.guidance || null,
    review_notes: d.review_notes || null,
    respondent_rule: d.respondent_rule,
    activation_rule: d.activation_rule,
    tag_notes: tagNotes,
  };
}

function Editor({ ui, meta, data, editable, onSaved }) {
  const { Button, Field } = ui;
  const item = data.item;
  const [d, setD] = useState(() => toDraft(item, meta));
  const [rulesValid, setRulesValid] = useState({ respondent: true, activation: true });
  const [errors, setErrors] = useState([]);
  const { busy, run } = useAsync();
  const set = (k, v) => setD((x) => ({ ...x, [k]: v }));
  const approved = item.status === "approved";

  const save = () =>
    run(async () => {
      setErrors([]);
      try {
        const r = await questionBankApi.update(item.id, toPayload(d, meta, item));
        onSaved(r);
      } catch (e) {
        setErrors(e.errors || [e.message]);
      }
    });

  const toggleType = (code) =>
    set("subject_types", d.subject_types.includes(code) ? d.subject_types.filter((c) => c !== code) : [...d.subject_types, code]);

  const placeholders = placeholdersIn(d.text, d.options);
  const factLabel = (k) => meta.fact_keys.find((f) => f.key === k)?.label || k;
  const grid = { display: "grid", gap: space.md, gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", alignItems: "start" };

  return (
    <div style={{ display: "grid", gap: space.lg, gridTemplateColumns: "minmax(0, 1fr)" }}>
      <fieldset disabled={!editable} style={{ border: 0, margin: 0, padding: 0, display: "grid", gap: space.md, minWidth: 0 }}>
        <Field
          label="Question text"
          hint={
            placeholders.length
              ? `Templated: filled from ${placeholders.map(factLabel).join(", ")}.`
              : "Use {fact_key} for values filled from confirmed facts, e.g. {review_year}."
          }
        >
          <textarea value={d.text} onChange={(e) => set("text", e.target.value)} rows={3} style={inputCss()} />
        </Field>

        <div style={grid}>
          <Field label="Answer type">
            <select value={d.answer_type} onChange={(e) => set("answer_type", e.target.value)} style={inputCss()}>
              {meta.answer_types.map((t) => (
                <option key={t} value={t}>
                  {ANSWER_TYPE_LABELS[t]}
                </option>
              ))}
            </select>
          </Field>
          {d.answer_type === "rating" ? (
            <Field label="Scale">
              <div style={{ display: "grid", gap: 6 }}>
                <select
                  aria-label="Scale"
                  value={d.scale_preset}
                  onChange={(e) => set("scale_preset", e.target.value)}
                  style={inputCss()}
                >
                  <option value="quality_5">1–5 Poor … Excellent</option>
                  <option value="agree_5">1–5 Strongly disagree … Strongly agree</option>
                  {d.scale_preset === "custom" ? <option value="custom">Custom (kept as is)</option> : null}
                </select>
                <label style={{ fontSize: 13, display: "flex", gap: 6, alignItems: "center" }}>
                  <input type="checkbox" checked={d.dont_know} onChange={(e) => set("dont_know", e.target.checked)} />
                  Allow “Don't know”
                </label>
              </div>
            </Field>
          ) : null}
        </div>
        {SELECT_TYPES.includes(d.answer_type) ? (
          <Field label="Options" hint="One per line.">
            <textarea value={d.options} onChange={(e) => set("options", e.target.value)} rows={5} style={inputCss()} />
          </Field>
        ) : null}

        <Field label="Subject types" hint="What or who the item is about.">
          <div style={{ display: "flex", gap: space.md, flexWrap: "wrap" }}>
            {meta.subject_types.map((t) => (
              <label key={t.code} style={{ fontSize: 13, display: "flex", gap: 6, alignItems: "center" }}>
                <input type="checkbox" checked={d.subject_types.includes(t.code)} onChange={() => toggleType(t.code)} />
                {t.name}
              </label>
            ))}
          </div>
        </Field>

        <div style={grid}>
          <Field label="Subject binding" hint="Which subjects the item repeats over.">
            <select value={d.subject_binding} onChange={(e) => set("subject_binding", e.target.value)} style={inputCss()}>
              {meta.subject_bindings.map((b) => (
                <option key={b} value={b}>
                  {BINDING_LABELS[b]}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Theme">
            <select value={d.theme_code} onChange={(e) => set("theme_code", e.target.value)} style={inputCss()}>
              {meta.themes.map((t) => (
                <option key={t.code} value={t.code}>
                  {t.name}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Evidence source">
            <select value={d.evidence_source_code} onChange={(e) => set("evidence_source_code", e.target.value)} style={inputCss()}>
              {meta.evidence_sources.map((t) => (
                <option key={t.code} value={t.code}>
                  {t.name}
                </option>
              ))}
            </select>
          </Field>
        </div>

        <div style={grid}>
          <Field label="Already known from" hint="A confirmed fact that answers this item.">
            <select value={d.known_from} onChange={(e) => set("known_from", e.target.value)} style={inputCss()}>
              <option value="">Not known in advance</option>
              {["person", "org", "committee", "evaluation"].map((scope) => (
                <optgroup key={scope} label={{ person: "Board member", org: "Organisation", committee: "Committee", evaluation: "Evaluation" }[scope]}>
                  {meta.fact_keys
                    .filter((f) => f.scope === scope)
                    .map((f) => (
                      <option key={f.key} value={f.key}>
                        {f.label}
                      </option>
                    ))}
                </optgroup>
              ))}
            </select>
          </Field>
          {d.known_from ? (
            <Field label="When known">
              <select value={d.known_from_behaviour} onChange={(e) => set("known_from_behaviour", e.target.value)} style={inputCss()}>
                <option value="skip">Skip the item</option>
                <option value="confirm">Ask them to confirm the stored value</option>
              </select>
            </Field>
          ) : null}
        </div>

        <RuleEditor
          label="Respondent rule (who answers)"
          initial={item.respondent_rule}
          initialDescription={item.respondent_rule_text}
          disabled={!editable}
          hint='e.g. {"all": [{"respondent.role": ["ned", "ined"]}, {"respondent.is_not_subject": true}]}'
          onChange={(rule, valid) => {
            set("respondent_rule", rule);
            setRulesValid((v) => ({ ...v, respondent: valid }));
          }}
        />
        <RuleEditor
          label="Activation rule (when it applies)"
          initial={item.activation_rule}
          initialDescription={item.activation_rule_text}
          disabled={!editable}
          hint={`Conditions: ${meta.conditions.map((c) => c.name).join(", ")}; combine with all, any, not.`}
          onChange={(rule, valid) => {
            set("activation_rule", rule);
            setRulesValid((v) => ({ ...v, activation: valid }));
          }}
        />

        <Field label="Guidance for phrasing" hint="Notes for the later AI phrasing step.">
          <textarea value={d.guidance} onChange={(e) => set("guidance", e.target.value)} rows={2} style={inputCss()} />
        </Field>
        <Field label="Review notes">
          <textarea value={d.review_notes} onChange={(e) => set("review_notes", e.target.value)} rows={2} style={inputCss()} />
        </Field>
        <label style={{ fontSize: 13, display: "flex", gap: 6, alignItems: "center" }}>
          <input type="checkbox" checked={d.tags_reviewed} onChange={(e) => set("tags_reviewed", e.target.checked)} />
          I've reviewed the suggested tags (marks them confirmed)
        </label>
      </fieldset>

      {editable ? (
        <div style={{ display: "grid", gap: space.sm }}>
          <ErrorList errors={errors} />
          {approved ? (
            <Notice tone="info">
              This version is approved. Saving creates version {data.latest_version + 1} as a draft; version {item.version} stays as it is.
            </Notice>
          ) : null}
          <div>
            <Button onClick={save} disabled={busy || !rulesValid.respondent || !rulesValid.activation}>
              {busy ? "Saving…" : approved ? `Save as version ${data.latest_version + 1}` : "Save changes"}
            </Button>
          </div>
        </div>
      ) : null}
    </div>
  );
}

function Clauses({ ui, meta, item, editable, onChange }) {
  const { Badge, Button, Field } = ui;
  const { busy, error, run } = useAsync();
  const [code, setCode] = useState(meta.governance_codes.includes("NCCG_2018") ? "NCCG_2018" : meta.governance_codes[0] || "");
  const [reference, setReference] = useState("");

  const act = (fn) => run(async () => onChange(await fn()));

  return (
    <section>
      <SectionTitle hint="Clauses of the governance codes this item tests. Suggested links need a consultant's confirmation.">
        Governance clauses
      </SectionTitle>
      {error ? <Notice tone="error">{error}</Notice> : null}
      {item.clauses.length === 0 ? <p style={{ margin: 0, color: color.textMuted }}>None linked.</p> : null}
      <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "grid", gap: space.sm }}>
        {item.clauses.map((c) => (
          <li key={c.clause_id}>
            <Panel>
              <div style={{ display: "flex", gap: space.sm, flexWrap: "wrap", alignItems: "center", justifyContent: "space-between" }}>
                <div style={{ fontWeight: font.weight.bold }}>
                  {c.code.replace("_", " ")} {c.reference}
                  {c.heading ? <span style={{ fontWeight: font.weight.regular }}> · {c.heading}</span> : null}
                </div>
                <div style={{ display: "flex", gap: space.md, alignItems: "center", flexWrap: "wrap" }}>
                  <Badge tone={c.status === "confirmed" ? "green" : "amber"}>{c.status === "confirmed" ? "Confirmed" : "Suggested"}</Badge>
                  {c.status === "suggested" ? (
                    <LinkButton disabled={busy} onClick={() => act(() => questionBankApi.confirmClause(item.id, c.clause_id))}>
                      Confirm
                    </LinkButton>
                  ) : null}
                  <LinkButton danger disabled={busy} onClick={() => act(() => questionBankApi.removeClause(item.id, c.clause_id))}>
                    Remove
                  </LinkButton>
                </div>
              </div>
              {c.text ? (
                <p style={{ margin: `${space.xs}px 0 0`, fontSize: 13, color: color.textMuted }}>
                  {c.text.length > 280 ? `${c.text.slice(0, 280)}…` : c.text}
                </p>
              ) : null}
            </Panel>
          </li>
        ))}
      </ul>
      {editable ? (
        <div style={{ display: "flex", gap: space.sm, flexWrap: "wrap", alignItems: "end", marginTop: space.md }}>
          <Field label="Code">
            <select value={code} onChange={(e) => setCode(e.target.value)} style={inputCss({ width: "auto" })}>
              {meta.governance_codes.map((c) => (
                <option key={c} value={c}>
                  {c.replace("_", " ")}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Clause reference">
            <input value={reference} onChange={(e) => setReference(e.target.value)} placeholder="e.g. 7.2.1" style={inputCss({ width: 140 })} />
          </Field>
          <Button
            variant="secondary"
            disabled={busy || !reference.trim()}
            onClick={() =>
              act(async () => {
                const r = await questionBankApi.addClause(item.id, code, reference.trim());
                setReference("");
                return r;
              })
            }
          >
            Link clause
          </Button>
        </div>
      ) : null}
    </section>
  );
}

function Sources({ item }) {
  return (
    <section>
      <SectionTitle hint="Where this item came from, so reviewers can trace it back to the original forms.">Source references</SectionTitle>
      <ul style={{ margin: 0, paddingLeft: 18, display: "grid", gap: space.sm, fontSize: 13 }}>
        {item.source_refs.map((r, i) => (
          <li key={`${r.form_id || r.derived_from}-${r.item}-${i}`}>
            {r.derived_from ? (
              <>
                Drawn from bank item <strong>{r.derived_from}</strong>: “{r.text}”
                {r.forms?.length ? <div style={{ color: color.textMuted }}>Originally on: {r.forms.join("; ")}</div> : null}
              </>
            ) : (
              <>
                <strong>{r.form}</strong>, item {r.item}
              </>
            )}
            {r.section ? <span style={{ color: color.textMuted }}> · {r.section}</span> : null}
            {r.original_text ? <div style={{ fontStyle: "italic", color: color.textMuted }}>Originally: “{r.original_text}”</div> : null}
            {r.original_answer ? <div style={{ color: color.textMuted }}>Answer format: {r.original_answer}</div> : null}
          </li>
        ))}
      </ul>
    </section>
  );
}

function TagNotes({ ui, item }) {
  const { Badge } = ui;
  const entries = Object.entries(item.tag_notes || {});
  if (!entries.length) return null;
  return (
    <section>
      <SectionTitle hint="Why each tag was suggested. A governance consultant confirms them.">Tag reasons</SectionTitle>
      <dl style={{ margin: 0, display: "grid", gap: space.sm, fontSize: 13 }}>
        {entries.map(([k, v]) => (
          <div key={k}>
            <dt style={{ fontWeight: font.weight.bold, display: "flex", gap: space.sm, alignItems: "center", flexWrap: "wrap" }}>
              {TAG_LABELS[k] || k}
              <Badge tone={v.status === "confirmed" ? "green" : "amber"}>{v.status === "confirmed" ? "Confirmed" : "Suggested"}</Badge>
            </dt>
            <dd style={{ margin: "2px 0 0", color: color.textMuted }}>{v.reason}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

export default function QuestionBankItemPage({ ui }) {
  const { Badge, Button, Card } = ui;
  const { itemId } = useParams();
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [saved, setSaved] = useState("");
  const { busy, error, run } = useAsync();
  const meta = useBankMeta(run);

  const load = useCallback(() => run(async () => setData(await questionBankApi.get(itemId))), [itemId, run]);
  useEffect(() => {
    load();
  }, [load]);

  function applied(r, message) {
    setSaved(message);
    if (r.item.id !== itemId) navigate(`/consultant/question-bank/${r.item.id}`);
    else setData(r);
  }

  if (!data || !meta) {
    return (
      <Card title="Question bank item">
        {error ? <Notice tone="error">{error}</Notice> : <p style={{ color: color.textMuted }}>Loading…</p>}
      </Card>
    );
  }

  const item = data.item;
  const latest = item.version === data.latest_version;
  const editable = latest && item.status !== "retired";
  const latestId = data.versions.find((v) => v.version === data.latest_version)?.id;

  return (
    <Card
      title={`${item.code} · version ${item.version}`}
      subtitle={`${nameOf(meta.themes, item.theme_code)} · ${nameOf(meta.evidence_sources, item.evidence_source_code)}`}
      right={<Badge tone={STATUS_TONE[item.status]}>{item.status[0].toUpperCase() + item.status.slice(1)}</Badge>}
    >
      <div style={{ display: "grid", gap: space.xl, gridTemplateColumns: "minmax(0, 1fr)" }}>
        <div style={{ display: "flex", gap: space.md, flexWrap: "wrap", alignItems: "center", justifyContent: "space-between" }}>
          <Link to="/consultant/question-bank" style={{ color: color.primaryText, fontWeight: font.weight.bold, fontSize: 13 }}>
            ← All items
          </Link>
          {latest ? (
            <div style={{ display: "flex", gap: space.sm, flexWrap: "wrap" }}>
              {item.status === "draft" ? (
                <Button
                  disabled={busy}
                  onClick={() => run(async () => applied(await questionBankApi.approve(item.id), `Approved version ${item.version}.`))}
                >
                  Approve
                </Button>
              ) : null}
              {item.status !== "retired" ? (
                <Button
                  variant="danger"
                  disabled={busy}
                  onClick={() => {
                    if (window.confirm(`Retire ${item.code}? It will no longer be selected for any evaluation.`))
                      run(async () => applied(await questionBankApi.retire(item.id), `Retired ${item.code}.`));
                  }}
                >
                  Retire
                </Button>
              ) : null}
            </div>
          ) : null}
        </div>

        {error ? <Notice tone="error">{error}</Notice> : null}
        {saved ? <Notice tone="success">{saved}</Notice> : null}
        {!latest ? (
          <Notice tone="warn">
            This is an older version kept for audit. <Link to={`/consultant/question-bank/${latestId}`}>Open version {data.latest_version}</Link> to make changes.
          </Notice>
        ) : item.status === "retired" ? (
          <Notice tone="warn">This item is retired and is never selected. Retired items can't be edited.</Notice>
        ) : null}
        {!editable && item.review_notes ? <Notice tone="info">{item.review_notes}</Notice> : null}

        <Editor
          key={`${item.id}-${item.updated_at}`}
          ui={ui}
          meta={meta}
          data={data}
          editable={editable}
          onSaved={(r) => applied(r, r.new_version ? `Saved as version ${r.item.version} (draft).` : "Saved.")}
        />

        <TagNotes ui={ui} item={item} />
        <Clauses ui={ui} meta={meta} item={item} editable={editable} onChange={(r) => setData(r)} />
        <Sources item={item} />

        <section>
          <SectionTitle>Versions</SectionTitle>
          <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "flex", gap: space.sm, flexWrap: "wrap" }}>
            {data.versions.map((v) => (
              <li key={v.id}>
                <Link
                  to={`/consultant/question-bank/${v.id}`}
                  aria-current={v.id === item.id ? "page" : undefined}
                  style={{
                    display: "inline-block",
                    padding: "6px 10px",
                    borderRadius: radius.sm,
                    border: `1px solid ${v.id === item.id ? color.primaryBorder : color.border}`,
                    background: v.id === item.id ? color.primarySoft : color.surface,
                    color: color.text,
                    fontSize: 13,
                    textDecoration: "none",
                  }}
                >
                  v{v.version} · {v.status}
                  <span style={{ color: color.textMuted }}> · {formatDateTime(v.approved_at || v.created_at)}</span>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      </div>
    </Card>
  );
}
