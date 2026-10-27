import React, { useCallback, useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { questionBankApi } from "../../../api/questionBankApi.js";
import { color, font, space } from "../../../theme.js";
import { Notice, Panel } from "../companies/shared.jsx";
import { inputCss, useAsync, visuallyHidden } from "../companies/helpers.js";
import { ANSWER_TYPE_LABELS, STATUS_TONE, nameOf, useBankMeta } from "./bankHelpers.js";

const FILTERS = ["q", "status", "subject_type", "theme", "evidence_source"];

function Filters({ ui, meta, params, setParam }) {
  const { Field } = ui;
  const select = (key, label, options) => (
    <Field label={label}>
      <select value={params.get(key) || ""} onChange={(e) => setParam(key, e.target.value)} style={inputCss()}>
        <option value="">All</option>
        {options.map((o) => (
          <option key={o.code} value={o.code}>
            {o.name}
          </option>
        ))}
      </select>
    </Field>
  );
  return (
    <div style={{ display: "grid", gap: space.md, gridTemplateColumns: "repeat(auto-fit, minmax(170px, 1fr))", alignItems: "end" }}>
      <Field label="Search" hint="Code, question text or guidance">
        <input
          type="search"
          defaultValue={params.get("q") || ""}
          onKeyDown={(e) => e.key === "Enter" && setParam("q", e.currentTarget.value.trim())}
          onBlur={(e) => setParam("q", e.currentTarget.value.trim())}
          style={inputCss()}
        />
      </Field>
      {select("status", "Status", (meta?.statuses || []).map((s) => ({ code: s, name: s[0].toUpperCase() + s.slice(1) })))}
      {select("subject_type", "Subject type", meta?.subject_types || [])}
      {select("theme", "Theme", meta?.themes || [])}
      {select("evidence_source", "Evidence source", meta?.evidence_sources || [])}
    </div>
  );
}

export default function QuestionBankPage({ ui }) {
  const { Badge, Card } = ui;
  const [params, setParams] = useSearchParams();
  const [data, setData] = useState(null);
  const { error, run } = useAsync();
  const meta = useBankMeta(run);
  // A string, so the list reloads only when a filter value actually changes
  const filterKey = JSON.stringify(FILTERS.map((k) => params.get(k) || ""));

  const load = useCallback(
    () =>
      run(async () => {
        const values = JSON.parse(filterKey);
        setData(await questionBankApi.list(Object.fromEntries(FILTERS.map((k, i) => [k, values[i]]))));
      }),
    [run, filterKey]
  );
  useEffect(() => {
    load();
  }, [load]);

  function setParam(key, value) {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    setParams(next, { replace: true });
  }

  const counts = data?.status_counts || {};
  const filtered = FILTERS.some((k) => params.get(k));

  return (
    <Card
      title="Question bank"
      subtitle="The firm's methodology as approved items. Rules decide who answers each item and about whom; AI only rephrases them later."
    >
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: space.md }}>
        <Badge tone="green">{counts.approved || 0} approved</Badge>
        <Badge tone="amber">{counts.draft || 0} draft</Badge>
        <Badge tone="gray">{counts.retired || 0} retired</Badge>
      </div>

      <Filters ui={ui} meta={meta} params={params} setParam={setParam} key={params.get("q") || ""} />

      {error ? (
        <div style={{ marginTop: space.md }}>
          <Notice tone="error">{error}</Notice>
        </div>
      ) : null}

      {data === null ? (
        <p style={{ color: color.textMuted }}>Loading…</p>
      ) : data.items.length === 0 ? (
        <Panel style={{ marginTop: space.md }}>
          <p style={{ margin: 0, color: color.textMuted }}>
            {filtered
              ? "No items match these filters."
              : "The bank is empty. Load the draft bank with scripts/question_bank/load_bank.py."}
          </p>
        </Panel>
      ) : (
        <>
          <p style={{ margin: `${space.md}px 0 0`, fontSize: 13, color: color.textMuted }} role="status">
            {data.total} item{data.total === 1 ? "" : "s"}
            {filtered ? " match" : ""}
          </p>
          <div style={ui.tableWrapStyle()}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: font.body, minWidth: 600 }}>
              <thead>
                <tr style={{ background: color.surfaceMuted, textAlign: "left" }}>
                  {["Code", "Question", "Tags", "Status"].map((h) => (
                    <th key={h} scope="col" style={{ ...ui.tdStyle(), fontWeight: font.weight.heavy }}>
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.items.map((i) => (
                  <tr key={i.id} style={{ borderTop: `1px solid ${color.border}` }}>
                    <td style={{ ...ui.tdStyle(), whiteSpace: "nowrap" }}>
                      <Link to={`/consultant/question-bank/${i.id}`} style={{ fontWeight: font.weight.bold, color: color.primaryText }}>
                        {i.code}
                      </Link>
                      {i.version > 1 ? <div style={{ fontSize: font.small, color: color.textMuted }}>v{i.version}</div> : null}
                    </td>
                    <td style={ui.tdStyle()}>
                      <div>{i.text}</div>
                      <div style={{ fontSize: font.small, color: color.textMuted, marginTop: 2 }}>
                        {ANSWER_TYPE_LABELS[i.answer_type]} · Who: {i.respondent_rule_text}
                        {i.activation_rule ? ` · When: ${i.activation_rule_text}` : ""}
                      </div>
                    </td>
                    <td style={ui.tdStyle()}>
                      <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
                        {i.subject_types.map((s) => (
                          <Badge key={s} tone="blue" wrap>
                            {nameOf(meta?.subject_types, s)}
                          </Badge>
                        ))}
                        <Badge tone="purple" wrap>{nameOf(meta?.themes, i.theme_code)}</Badge>
                        <Badge tone="gray" wrap>{nameOf(meta?.evidence_sources, i.evidence_source_code)}</Badge>
                        {i.templated ? <Badge tone="amber">Templated</Badge> : null}
                        {i.known_from ? <Badge tone="green" wrap>Known: {i.known_from_label}</Badge> : null}
                      </div>
                    </td>
                    <td style={ui.tdStyle()}>
                      <Badge tone={STATUS_TONE[i.status]}>{i.status[0].toUpperCase() + i.status.slice(1)}</Badge>
                      <span style={visuallyHidden}> version {i.version}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </Card>
  );
}
