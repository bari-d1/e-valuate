import React, { useCallback, useEffect, useMemo, useState } from "react";
import { downloadResponsesExport, releaseResponsesExportUrl } from "../../api/consultantAuth.js";

const API_BASE = import.meta.env.VITE_API_BASE || "http://127.0.0.1:8000";

const hintStyle = { fontSize: 11, color: "#64748B", fontWeight: 500, maxWidth: 280, lineHeight: 1.35 };

function useDebouncedValue(value, delayMs) {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), delayMs);
    return () => clearTimeout(t);
  }, [value, delayMs]);
  return debounced;
}

function linkDownloadStyle(disabled, primary) {
  const styles = primary
    ? { bg: "#2563EB", fg: "white", bd: "#1D4ED8" }
    : { bg: "#F8FAFC", fg: "#0F172A", bd: "#E2E8F0" };
  return {
    display: "inline-block",
    padding: "10px 12px",
    borderRadius: 10,
    border: `1px solid ${styles.bd}`,
    background: disabled ? "#E5E7EB" : styles.bg,
    color: disabled ? "#6B7280" : styles.fg,
    fontWeight: 800,
    cursor: disabled ? "not-allowed" : "pointer",
    textDecoration: "none",
    pointerEvents: disabled ? "none" : "auto",
    opacity: disabled ? 0.7 : 1,
  };
}

function FilterBlock({ title, hint, children }) {
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        gap: 6,
        minWidth: 0,
      }}
    >
      <div style={{ fontSize: 12, fontWeight: 800, color: "#0F172A" }}>{title}</div>
      {children}
      <div style={hintStyle}>{hint}</div>
    </div>
  );
}

function FilterChip({ label, onRemove }) {
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 6,
        padding: "4px 8px 4px 10px",
        borderRadius: 999,
        background: "#EEF2FF",
        border: "1px solid #C7D2FE",
        fontSize: 12,
        fontWeight: 700,
        color: "#3730A3",
      }}
    >
      {label}
      <button
        type="button"
        onClick={onRemove}
        title="Remove filter"
        style={{
          border: "none",
          background: "transparent",
          cursor: "pointer",
          padding: "0 2px",
          fontSize: 14,
          lineHeight: 1,
          color: "#4338CA",
          fontWeight: 900,
        }}
      >
        ×
      </button>
    </span>
  );
}

/**
 * List raw responses and download CSV/XLSX exports (consultant).
 */
export default function ConsultantResponsesPage({
  ui,
  busy: appBusy,
  focus,
  evalId,
  selectedTemplate,
  selectedVersion,
  apiGet,
  lockReason,
  go,
  renderFlowBar,
  tableWrapStyle,
  tdStyle,
}) {
  const { Card, Badge, Button } = ui || {};

  const [loading, setLoading] = useState(false);
  const [analyticsLoading, setAnalyticsLoading] = useState(false);
  const [analyticsData, setAnalyticsData] = useState(null);
  const [analyticsErr, setAnalyticsErr] = useState("");
  const [err, setErr] = useState("");
  const [exportMsg, setExportMsg] = useState("");
  const [exportManualUrl, setExportManualUrl] = useState("");
  const [exportManualName, setExportManualName] = useState("");
  const [exportBusy, setExportBusy] = useState(false);
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [assignments, setAssignments] = useState([]);
  const [tracks, setTracks] = useState([]);

  const [filterAssignmentId, setFilterAssignmentId] = useState("");
  const [filterAssignmentType, setFilterAssignmentType] = useState("");
  const [filterTrackCode, setFilterTrackCode] = useState("");
  const [filterQuestionTemplate, setFilterQuestionTemplate] = useState("");
  const [filterQuestionVersion, setFilterQuestionVersion] = useState("");

  const debouncedQuestionTemplate = useDebouncedValue(filterQuestionTemplate, 450);
  const debouncedQuestionVersion = useDebouncedValue(filterQuestionVersion, 450);

  const missing = [];
  if (!ui?.Card) missing.push("ui.Card");
  if (!ui?.Badge) missing.push("ui.Badge");
  if (!ui?.Button) missing.push("ui.Button");
  if (typeof renderFlowBar !== "function") missing.push("renderFlowBar");
  if (typeof lockReason !== "function") missing.push("lockReason");
  if (typeof go !== "function") missing.push("go");
  if (typeof apiGet !== "function") missing.push("apiGet");
  if (typeof tableWrapStyle !== "function") missing.push("tableWrapStyle");
  if (typeof tdStyle !== "function") missing.push("tdStyle");

  if (missing.length) {
    return (
      <div style={{ padding: 16, border: "1px solid #FECACA", background: "#FEF2F2", borderRadius: 12 }}>
        <div style={{ fontWeight: 900, color: "#991B1B" }}>ConsultantResponsesPage: Missing props</div>
        <div style={{ marginTop: 8, color: "#991B1B", fontFamily: "monospace", fontSize: 12 }}>{missing.join(", ")}</div>
      </div>
    );
  }

  const reason = lockReason("responses");

  const loadMeta = useCallback(async () => {
    if (!String(evalId || "").trim()) return;
    try {
      const [a, t] = await Promise.all([
        apiGet(`/api/v1/evaluations/${encodeURIComponent(evalId)}/assignments`),
        apiGet(`/api/v1/evaluations/${encodeURIComponent(evalId)}/tracks`),
      ]);
      setAssignments(Array.isArray(a?.items) ? a.items : []);
      setTracks(Array.isArray(t?.items) ? t.items : []);
    } catch {
      setAssignments([]);
      setTracks([]);
    }
  }, [apiGet, evalId]);

  const buildQuery = useCallback(() => {
    const q = new URLSearchParams();
    if (filterAssignmentId.trim()) q.set("assignment_id", filterAssignmentId.trim());
    if (filterAssignmentType.trim()) q.set("assignment_type", filterAssignmentType.trim());
    if (filterTrackCode.trim()) q.set("track_code", filterTrackCode.trim());
    if (debouncedQuestionTemplate.trim()) q.set("question_template_code", debouncedQuestionTemplate.trim());
    if (debouncedQuestionVersion.trim()) q.set("question_version", debouncedQuestionVersion.trim());
    return q.toString();
  }, [
    filterAssignmentId,
    filterAssignmentType,
    filterTrackCode,
    debouncedQuestionTemplate,
    debouncedQuestionVersion,
  ]);

  const loadResponses = useCallback(async () => {
    if (!String(evalId || "").trim()) return;
    setErr("");
    setLoading(true);
    try {
      const qs = buildQuery();
      const path =
        `/api/v1/evaluations/${encodeURIComponent(evalId)}/responses` +
        (qs ? `?${qs}&limit=500` : "?limit=500");
      const data = await apiGet(path);
      setItems(Array.isArray(data?.items) ? data.items : []);
      setTotal(Number(data?.total ?? data?.items?.length ?? 0));
    } catch (e) {
      setErr(e?.message || String(e));
      setItems([]);
      setTotal(0);
    } finally {
      setLoading(false);
    }
  }, [apiGet, buildQuery, evalId]);

  const loadScopedAnalytics = useCallback(async () => {
    if (!String(evalId || "").trim()) return;
    setAnalyticsErr("");
    setAnalyticsLoading(true);
    try {
      const qs = buildQuery();
      const path =
        `/api/v1/evaluations/${encodeURIComponent(evalId)}/analytics` +
        (qs ? `?${qs}&include_trends=true` : "?include_trends=true");
      const data = await apiGet(path);
      setAnalyticsData(data);
    } catch (e) {
      setAnalyticsErr(e?.message || String(e));
      setAnalyticsData(null);
    } finally {
      setAnalyticsLoading(false);
    }
  }, [apiGet, buildQuery, evalId]);

  useEffect(() => {
    loadMeta();
  }, [loadMeta]);

  useEffect(() => {
    loadResponses();
  }, [loadResponses]);

  useEffect(() => {
    return () => {
      if (exportManualUrl) releaseResponsesExportUrl(exportManualUrl);
    };
  }, [exportManualUrl]);

  const exportFilterParams = useMemo(
    () => ({
      assignment_id: filterAssignmentId.trim() || undefined,
      assignment_type: filterAssignmentType.trim() || undefined,
      track_code: filterTrackCode.trim() || undefined,
      question_template_code: debouncedQuestionTemplate.trim() || undefined,
      question_version: debouncedQuestionVersion.trim() || undefined,
    }),
    [
      filterAssignmentId,
      filterAssignmentType,
      filterTrackCode,
      debouncedQuestionTemplate,
      debouncedQuestionVersion,
    ]
  );

  const runExport = useCallback(
    async (format) => {
      if (!String(evalId || "").trim()) return;
      setExportMsg("");
      if (exportManualUrl) {
        releaseResponsesExportUrl(exportManualUrl);
        setExportManualUrl("");
        setExportManualName("");
      }
      setExportBusy(true);
      try {
        const result = await downloadResponsesExport(API_BASE, evalId, format, exportFilterParams);
        if (result.needsManualLink && result.objectUrl) {
          setExportManualUrl(result.objectUrl);
          setExportManualName(result.filename);
          setExportMsg(
            `Export ready (${result.filename}, ${Math.round(result.bytes / 1024)} KB). If nothing appeared in Downloads, use Save link below or allow downloads for this site.`
          );
        } else {
          setExportMsg(`Saved ${result.filename} (${Math.round(result.bytes / 1024)} KB)`);
        }
      } catch (e) {
        setExportMsg("");
        setErr(e?.message || String(e));
      } finally {
        setExportBusy(false);
      }
    },
    [evalId, exportFilterParams, exportManualUrl]
  );

  const assignmentTypes = useMemo(() => {
    const s = new Set();
    for (const a of assignments) {
      const t = String(a.assignment_type || "").trim();
      if (t) s.add(t);
    }
    return [...s].sort();
  }, [assignments]);

  const trackCodes = useMemo(() => {
    const out = [];
    for (const tr of tracks) {
      const c = String(tr.code || "").trim();
      if (c) out.push({ code: c, name: tr.name || c });
    }
    return out.sort((a, b) => a.code.localeCompare(b.code));
  }, [tracks]);

  const selectedAssignmentLabel = useMemo(() => {
    const a = assignments.find((x) => x.assignment_id === filterAssignmentId);
    if (!a) return filterAssignmentId ? String(filterAssignmentId).slice(0, 8) + "…" : "";
    const bits = [a.assignment_type, a.committee_name].filter(Boolean).join(" — ");
    return bits || filterAssignmentId;
  }, [assignments, filterAssignmentId]);

  const activeChips = useMemo(() => {
    const chips = [];
    if (filterAssignmentId.trim()) {
      chips.push({
        key: "assignment",
        label: `Assignment: ${selectedAssignmentLabel}`,
        onRemove: () => setFilterAssignmentId(""),
      });
    }
    if (filterAssignmentType.trim()) {
      chips.push({
        key: "type",
        label: `Assignment type: ${filterAssignmentType}`,
        onRemove: () => setFilterAssignmentType(""),
      });
    }
    if (filterTrackCode.trim()) {
      chips.push({
        key: "track",
        label: `Track: ${filterTrackCode}`,
        onRemove: () => setFilterTrackCode(""),
      });
    }
    if (debouncedQuestionTemplate.trim() || debouncedQuestionVersion.trim()) {
      const qLabel = [debouncedQuestionTemplate.trim() || "any", debouncedQuestionVersion.trim() || "any"].join(" v");
      chips.push({
        key: "qbank",
        label: `Question bank: ${qLabel}`,
        onRemove: () => {
          setFilterQuestionTemplate("");
          setFilterQuestionVersion("");
        },
      });
    }
    return chips;
  }, [
    filterAssignmentId,
    filterAssignmentType,
    filterTrackCode,
    debouncedQuestionTemplate,
    debouncedQuestionVersion,
    selectedAssignmentLabel,
  ]);

  const clearAllFilters = useCallback(() => {
    setFilterAssignmentId("");
    setFilterAssignmentType("");
    setFilterTrackCode("");
    setFilterQuestionTemplate("");
    setFilterQuestionVersion("");
  }, []);

  const questionBankPending =
    filterQuestionTemplate.trim() !== debouncedQuestionTemplate.trim() ||
    filterQuestionVersion.trim() !== debouncedQuestionVersion.trim();

  const busy = !!appBusy || loading || exportBusy;

  // App `index.css` sets :root light text when OS prefers dark; native selects use white
  // backgrounds by default → invisible white-on-white. Force readable light-theme controls.
  const consultantFormSurfaceStyle = {
    color: "#0F172A",
    colorScheme: "light",
  };

  const selectStyle = {
    minWidth: 200,
    maxWidth: 280,
    padding: "8px 10px",
    borderRadius: 10,
    border: "1px solid #E2E8F0",
    backgroundColor: "#FFFFFF",
    color: "#0F172A",
    colorScheme: "light",
  };

  const questionBankInputStyle = {
    width: 140,
    padding: "8px 10px",
    borderRadius: 10,
    border: "1px solid #E2E8F0",
    backgroundColor: "#FFFFFF",
    color: "#0F172A",
    colorScheme: "light",
  };

  return (
    <Card
      title="Responses & export"
      subtitle="Filtered preview and downloads use the same rules as the table below."
    >
      {focus}

      {reason ? (
        <div
          style={{
            marginTop: 12,
            padding: 12,
            borderRadius: 12,
            border: "1px solid #FDE68A",
            background: "#FFFBEB",
            color: "#92400E",
            fontWeight: 600,
          }}
        >
          {reason}
        </div>
      ) : null}

      {!reason && String(evalId || "").trim() ? (
        <div
          className="consultant-form-surface"
          style={{
            marginTop: 16,
            display: "flex",
            flexDirection: "column",
            gap: 14,
            ...consultantFormSurfaceStyle,
          }}
        >
          <div
            style={{
              padding: 14,
              borderRadius: 12,
              border: "1px solid #CBD5F5",
              background: "#F8FAFF",
            }}
          >
            <div style={{ fontWeight: 800, color: "#1E3A8A", marginBottom: 8 }}>How to use this page</div>
            <ul style={{ margin: 0, paddingLeft: 20, color: "#334155", fontSize: 13, lineHeight: 1.5 }}>
              <li>
                Select an evaluation in the header first. Rows are one answer per question (plus who answered and which assignment).
              </li>
              <li>
                Use filters to narrow rows, then export. Several filters combine: you only see answers that match <em>all</em> chosen
                filters.
              </li>
              <li>
                Leave <strong>Question bank</strong> empty unless you intentionally want to restrict by questionnaire template/version.
                (Mismatch with stored answers is the most common reason for “no rows”.)
              </li>
              <li>
                Only answers submitted through an assignment portal appear here with assignment filters. Demo seed responses without an
                assignment do not match assignment/track filters.
              </li>
              <li>
                Downloads use the same filters as the table. Prefer <strong>Assignment (exact)</strong> for “this person’s link”;
                use <strong>Track</strong> or <strong>Assignment type</strong> for rollups across assignments.
              </li>
            </ul>
          </div>

          {activeChips.length > 0 ? (
            <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8 }}>
              <span style={{ fontSize: 12, fontWeight: 800, color: "#475569" }}>Active filters</span>
              {activeChips.map((c) => (
                <FilterChip key={c.key} label={c.label} onRemove={c.onRemove} />
              ))}
              <Button variant="secondary" disabled={busy} onClick={clearAllFilters}>
                Clear all
              </Button>
            </div>
          ) : (
            <div style={{ fontSize: 13, color: "#64748B" }}>
              No filters applied — showing every response for this evaluation (preview capped at 500 rows).
            </div>
          )}

          <div style={{ fontSize: 12, color: "#64748B" }}>
            Filters apply automatically when you change dropdowns. Question bank fields wait briefly while you type.
            Use <strong>Refresh</strong> if something failed or data changed elsewhere.
            {questionBankPending ? (
              <span style={{ marginLeft: 8, fontWeight: 800, color: "#B45309" }}>(Updating question bank filter…)</span>
            ) : null}
          </div>

          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))",
              gap: 16,
              alignItems: "stretch",
            }}
          >
            <FilterBlock
              title="Assignment (exact)"
              hint="One generated task / portal link. Each line shows how many answers are stored for that assignment — choose one with a positive count to see data."
            >
              <select
                value={filterAssignmentId}
                onChange={(e) => setFilterAssignmentId(e.target.value)}
                disabled={busy}
                style={selectStyle}
                aria-label="Assignment exact filter"
              >
                <option value="">All assignments</option>
                {[...assignments]
                  .sort((x, y) => {
                    const cx = Number(x.response_count) || 0;
                    const cy = Number(y.response_count) || 0;
                    if (cy !== cx) return cy - cx;
                    return String(x.assignment_type || "").localeCompare(String(y.assignment_type || ""));
                  })
                  .map((a) => {
                    const n = Number(a.response_count);
                    const cnt =
                      Number.isFinite(n) && n > 0 ? `${n} answer${n === 1 ? "" : "s"}` : "no answers yet";
                    return (
                      <option key={a.assignment_id} value={a.assignment_id}>
                        {a.assignment_type}
                        {a.committee_name ? ` — ${a.committee_name}` : ""} · {cnt} · ({String(a.assignment_id).slice(0, 8)}…)
                      </option>
                    );
                  })}
              </select>
            </FilterBlock>

            <FilterBlock
              title="Assignment type (category)"
              hint="Groups every assignment with this type across the evaluation (many respondents/tasks)."
            >
              <select
                value={filterAssignmentType}
                onChange={(e) => setFilterAssignmentType(e.target.value)}
                disabled={busy}
                style={selectStyle}
                aria-label="Assignment type filter"
              >
                <option value="">Any assignment type</option>
                {assignmentTypes.map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
            </FilterBlock>

            <FilterBlock
              title="Track (from Assessment tracks)"
              hint="Matches assignments created from this track template (type + instrument for this evaluation)."
            >
              <select
                value={filterTrackCode}
                onChange={(e) => setFilterTrackCode(e.target.value)}
                disabled={busy}
                style={selectStyle}
                aria-label="Track filter"
              >
                <option value="">Any track</option>
                {trackCodes.map((t) => (
                  <option key={t.code} value={t.code}>
                    {t.code}
                    {t.name && t.name !== t.code ? ` — ${t.name}` : ""}
                  </option>
                ))}
              </select>
            </FilterBlock>

            <FilterBlock
              title="Question bank (optional)"
              hint="Restricts rows to questions from this template/version. Leave both blank first while testing assignment filters — otherwise you can easily get zero rows if the header questionnaire does not match stored answers."
            >
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
                <input
                  value={filterQuestionTemplate}
                  onChange={(e) => setFilterQuestionTemplate(e.target.value)}
                  placeholder="template_code"
                  disabled={busy}
                  aria-label="Question template code"
                  style={questionBankInputStyle}
                />
                <input
                  value={filterQuestionVersion}
                  onChange={(e) => setFilterQuestionVersion(e.target.value)}
                  placeholder="version"
                  disabled={busy}
                  aria-label="Questionnaire version number"
                  style={{ ...questionBankInputStyle, width: 72 }}
                />
                <Button
                  variant="secondary"
                  disabled={busy}
                  title="Copy template/version from the evaluation header into these fields"
                  onClick={() => {
                    const t = String(selectedTemplate || "").trim();
                    const v = String(selectedVersion || "").trim();
                    setFilterQuestionTemplate(t);
                    setFilterQuestionVersion(v);
                  }}
                >
                  Use header questionnaire
                </Button>
              </div>
            </FilterBlock>
          </div>

          <div style={{ display: "flex", flexWrap: "wrap", gap: 10, alignItems: "center" }}>
            <Button variant="secondary" disabled={busy} onClick={() => loadResponses()}>
              Refresh
            </Button>

            <button
              type="button"
              disabled={busy || !!reason}
              style={linkDownloadStyle(busy || !!reason, true)}
              onClick={() => runExport("csv")}
            >
              {exportBusy ? "Downloading…" : "Download CSV"}
            </button>
            <button
              type="button"
              disabled={busy || !!reason}
              style={linkDownloadStyle(busy || !!reason, false)}
              onClick={() => runExport("xlsx")}
            >
              {exportBusy ? "Downloading…" : "Download Excel"}
            </button>
            {exportMsg ? (
              <span style={{ fontSize: 12, color: "#047857", fontWeight: 700 }}>{exportMsg}</span>
            ) : null}
            {exportManualUrl ? (
              <a
                href={exportManualUrl}
                download={exportManualName || "responses.csv"}
                style={{
                  fontSize: 12,
                  fontWeight: 800,
                  color: "#1D4ED8",
                  textDecoration: "underline",
                }}
              >
                Save {exportManualName || "export"} manually
              </a>
            ) : null}
          </div>

          <div
            style={{
              padding: 14,
              borderRadius: 12,
              border: "1px solid #E2E8F0",
              background: "#F8FAFC",
            }}
          >
            <div style={{ fontWeight: 800, color: "#0F172A", marginBottom: 6 }}>Scoped analytics (rating scores)</div>
            <div style={{ fontSize: 12, color: "#64748B", marginBottom: 10 }}>
              Uses the same filters as the table and export. Overall score is weighted by question weights (ratings only). Trend history is
              omitted when any scope filter is applied.
            </div>
            <Button variant="secondary" disabled={busy || !!reason || analyticsLoading} onClick={() => loadScopedAnalytics()}>
              {analyticsLoading ? "Loading…" : "Load scoped analytics"}
            </Button>
            {analyticsErr ? (
              <div style={{ marginTop: 10, color: "#991B1B", fontSize: 13 }}>{analyticsErr}</div>
            ) : null}
            {analyticsData?.metrics ? (
              <div style={{ marginTop: 14 }}>
                <div style={{ fontSize: 14, fontWeight: 800, color: "#1E293B" }}>
                  Overall:{" "}
                  <strong>{analyticsData.metrics.overall_score ?? "—"}</strong>
                  <span style={{ fontWeight: 600, color: "#64748B" }}> / 100</span>
                </div>
                {analyticsData.scope ? (
                  <div style={{ marginTop: 6, fontSize: 12, color: "#64748B" }}>
                    Rating rows used: <strong>{analyticsData.scope.rating_rows_used ?? 0}</strong>
                    {analyticsData.scope.scoped ? " (scoped)" : " (full evaluation)"}
                  </div>
                ) : null}
                {Array.isArray(analyticsData.metrics.dimensions) && analyticsData.metrics.dimensions.length > 0 ? (
                  <ul style={{ margin: "10px 0 0", paddingLeft: 18, fontSize: 13, color: "#334155" }}>
                    {analyticsData.metrics.dimensions.map((d) => (
                      <li key={d.name}>
                        <strong>{d.name}</strong>: {d.score}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <div style={{ marginTop: 8, fontSize: 13, color: "#64748B" }}>No rating rows in scope.</div>
                )}
              </div>
            ) : null}
          </div>

          {err ? (
            <div
              style={{ padding: 12, borderRadius: 12, border: "1px solid #FCA5A5", background: "#FEF2F2", color: "#7F1D1D" }}
            >
              {err}
            </div>
          ) : null}

          {!busy && !err && total === 0 ? (
            <div
              style={{
                padding: 14,
                borderRadius: 12,
                border: "1px solid #FDE68A",
                background: "#FFFBEB",
                color: "#78350F",
                fontSize: 13,
                lineHeight: 1.55,
              }}
            >
              <div style={{ fontWeight: 800, marginBottom: 8 }}>No rows match these filters</div>
              <div style={{ marginBottom: 8 }}>Typical causes:</div>
              <ul style={{ margin: "0 0 10px 18px", padding: 0 }}>
                <li>
                  <strong>Question bank</strong> is too narrow — clear template/version fields (or click <strong>Clear all</strong>) and
                  try again.
                </li>
                <li>
                  No one has submitted answers through the <strong>portal assignments</strong> yet for this evaluation (assignment/track
                  filters only include responses linked to an assignment).
                </li>
                <li>
                  Only <strong>seed demo responses</strong> exist — those are often stored without an assignment; clear assignment/track
                  filters or submit via a portal link to create assignment-linked responses.
                </li>
              </ul>
              <Button variant="secondary" disabled={busy} onClick={clearAllFilters}>
                Clear all filters
              </Button>
            </div>
          ) : null}

          <div style={{ fontSize: 13, color: "#475569" }}>
            Showing <strong>{items.length}</strong> of <strong>{total}</strong> matching rows (preview limited to 500).
          </div>

          <div style={tableWrapStyle()}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
              <thead>
                <tr style={{ textAlign: "left", borderBottom: "1px solid #E2E8F0" }}>
                  {[
                    "Respondent",
                    "Assignment",
                    "Dimension",
                    "Question",
                    "Type",
                    "Score",
                    "Comment",
                  ].map((h) => (
                    <th key={h} style={{ padding: "8px 6px", fontWeight: 800, whiteSpace: "nowrap" }}>
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {items.map((row) => (
                  <tr key={row.response_id} style={{ borderBottom: "1px solid #F1F5F9", verticalAlign: "top" }}>
                    <td style={tdStyle()}>{row.respondent_email || row.respondent_participant_id}</td>
                    <td style={tdStyle()}>
                      {row.assignment_type || "—"}
                      {row.committee_name ? (
                        <div style={{ fontSize: 11, color: "#64748B" }}>{row.committee_name}</div>
                      ) : null}
                    </td>
                    <td style={tdStyle()}>{row.dimension}</td>
                    <td style={{ ...tdStyle(), maxWidth: 360, whiteSpace: "pre-wrap" }}>{row.question_text}</td>
                    <td style={tdStyle()}>{row.answer_type}</td>
                    <td style={tdStyle()}>{row.score ?? ""}</td>
                    <td style={{ ...tdStyle(), maxWidth: 280, whiteSpace: "pre-wrap" }}>{row.comment || ""}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}
    </Card>
  );
}
