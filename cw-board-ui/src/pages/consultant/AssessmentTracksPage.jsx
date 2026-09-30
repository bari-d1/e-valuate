import React, { useCallback, useEffect, useMemo, useState } from "react";
import CommitteeTrackConfigEditor from "./CommitteeTrackConfigEditor.jsx";
import {
  buildCommitteeConfigForApi,
  defaultCommitteeEditorState,
  isCommitteeTemplate,
  parseCommitteeConfigFromApi,
  validateCommitteeEditorState,
} from "./committeeTrackConfig.js";

/**
 * Consultant: multi-track configuration — templates, enable tracks, generate assignments, copy portal URLs.
 */

function parseConfigJson(text) {
  const t = String(text || "").trim();
  if (!t) return {};
  try {
    return JSON.parse(t);
  } catch {
    throw new Error("Invalid JSON in track config");
  }
}

function _hasInstrumentOverride(row) {
  if (!row) return false;
  const tc = row.instrument_template_code;
  const ver = row.instrument_version;
  const hasT = tc != null && String(tc).trim() !== "";
  const hasV = ver != null;
  return hasT || hasV;
}

function buildInstrumentStateFromTracks(templatesList, evalTrackRows, evalDefault) {
  const evT = (evalDefault?.template_code || "DEFAULT").trim() || "DEFAULT";
  const evV = Number(evalDefault?.version ?? 1) || 1;
  const byCode = {};
  for (const r of evalTrackRows || []) {
    if (r?.code) byCode[r.code] = r;
  }
  const out = {};
  for (const t of templatesList || []) {
    const code = t.code;
    const row = byCode[code];
    if (!row || !_hasInstrumentOverride(row)) {
      out[code] = {
        useEvalDefault: true,
        template: evT,
        version: String(evV),
      };
    } else {
      const tc = String(row.instrument_template_code || "").trim() || evT;
      const ver = row.instrument_version != null ? Number(row.instrument_version) : evV;
      out[code] = {
        useEvalDefault: false,
        template: tc,
        version: String(Number.isFinite(ver) && ver > 0 ? ver : evV),
      };
    }
  }
  return out;
}

export default function AssessmentTracksPage({
  ui,
  busy,
  focus,
  evalId,
  apiGet,
  apiPost,
  notifyParticipantLinks,
  go,
  renderFlowBar,
  onTracksWorkflowUpdate,
  tableWrapStyle,
  tdStyle,
}) {
  const { Card, Badge, Field, Button } = ui;
  const hasEval = !!String(evalId || "").trim();
  const disabledBase = busy || !hasEval;

  const [errLocal, setErrLocal] = useState("");
  const [loading, setLoading] = useState(false);

  const [templates, setTemplates] = useState([]);
  const [evalTracks, setEvalTracks] = useState([]);
  const [assignments, setAssignments] = useState([]);
  const [participantsById, setParticipantsById] = useState({});

  const [selectedCodes, setSelectedCodes] = useState(() => new Set());
  const [configByCode, setConfigByCode] = useState({});
  const [committeeStateByCode, setCommitteeStateByCode] = useState({});
  const [showAdvancedJson, setShowAdvancedJson] = useState(false);
  /** Per track code: questionnaire override (or "same as evaluation") */
  const [instrumentByCode, setInstrumentByCode] = useState(() => ({}));
  /** Evaluation default from GET /evaluations/{id} — for labels and prefilling */
  const [evalInstrument, setEvalInstrument] = useState(() => ({
    template_code: "DEFAULT",
    version: 1,
  }));

  const [dryRunResult, setDryRunResult] = useState(null);
  const [genResult, setGenResult] = useState(null);
  const [sendEmailNotifications, setSendEmailNotifications] = useState(true);
  const [notifyResult, setNotifyResult] = useState(null);

  const participantCount = useMemo(() => Object.keys(participantsById).length, [participantsById]);
  const participantList = useMemo(() => Object.values(participantsById), [participantsById]);
  const participantEmailSet = useMemo(
    () => new Set(participantList.map((p) => String(p.email || "").trim().toLowerCase()).filter(Boolean)),
    [participantList]
  );
  const needsParticipantsToGenerate = participantCount === 0;
  const generateDisabled = disabledBase || needsParticipantsToGenerate;

  const selectedCommitteeTemplates = useMemo(
    () => templates.filter((t) => selectedCodes.has(t.code) && isCommitteeTemplate(t)),
    [templates, selectedCodes]
  );

  const selectedNonCommitteeWithConfig = useMemo(
    () => templates.filter((t) => selectedCodes.has(t.code) && !isCommitteeTemplate(t)),
    [templates, selectedCodes]
  );

  const reportStats = useCallback(
    (tracksItems, assignmentItems) => {
      if (typeof onTracksWorkflowUpdate !== "function") return;
      const enabled = (tracksItems || []).filter((t) => Number(t.enabled) === 1).length;
      onTracksWorkflowUpdate({
        enabledTracksCount: enabled,
        assignmentsCount: Array.isArray(assignmentItems) ? assignmentItems.length : 0,
      });
    },
    [onTracksWorkflowUpdate]
  );

  const loadAll = useCallback(async () => {
    if (!evalId?.trim()) return;
    setErrLocal("");
    setLoading(true);
    try {
      const [tplRes, etRes, asRes, partRes, evRes] = await Promise.all([
        apiGet("/api/v1/track-templates?active_only=true"),
        apiGet(`/api/v1/evaluations/${encodeURIComponent(evalId)}/tracks`),
        apiGet(`/api/v1/evaluations/${encodeURIComponent(evalId)}/assignments`),
        apiGet(`/api/v1/evaluations/${encodeURIComponent(evalId)}/participants`),
        apiGet(`/api/v1/evaluations/${encodeURIComponent(evalId)}`),
      ]);

      const tItems = Array.isArray(tplRes?.items) ? tplRes.items : [];
      setTemplates(tItems);

      const etItems = Array.isArray(etRes?.items) ? etRes.items : [];
      setEvalTracks(etItems);

      const inst = evRes?.instrument || {};
      const evalDefault = {
        template_code: (inst.template_code || "DEFAULT").trim() || "DEFAULT",
        version: Number(inst.version ?? 1) || 1,
      };
      setEvalInstrument(evalDefault);
      setInstrumentByCode(buildInstrumentStateFromTracks(tItems, etItems, evalDefault));

      const asItems = Array.isArray(asRes?.items) ? asRes.items : [];
      setAssignments(asItems);

      const pmap = {};
      for (const p of partRes?.items || []) {
        if (p?.participant_id) pmap[p.participant_id] = p;
      }
      setParticipantsById(pmap);

      const sel = new Set();
      const cfg = {};
      const committeeState = {};
      for (const row of etItems) {
        if (row?.code && Number(row.enabled) === 1) sel.add(row.code);
        const tplRow = tItems.find((x) => x.code === row.code);
        if (row?.code && tplRow && isCommitteeTemplate(tplRow)) {
          committeeState[row.code] = parseCommitteeConfigFromApi(row.config || {});
        } else if (row?.code && row.config && Object.keys(row.config).length) {
          cfg[row.code] = JSON.stringify(row.config, null, 2);
        }
      }
      setSelectedCodes(sel);
      setConfigByCode(cfg);
      setCommitteeStateByCode(committeeState);

      reportStats(etItems, asItems);
    } catch (e) {
      setErrLocal(e?.message || String(e));
    } finally {
      setLoading(false);
    }
  }, [evalId, apiGet, reportStats]);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  const toggleCode = (code) => {
    const tpl = templates.find((t) => t.code === code);
    setSelectedCodes((prev) => {
      const next = new Set(prev);
      if (next.has(code)) {
        next.delete(code);
      } else {
        next.add(code);
        if (tpl && isCommitteeTemplate(tpl) && !committeeStateByCode[code]) {
          setCommitteeStateByCode((cprev) => ({
            ...cprev,
            [code]: defaultCommitteeEditorState(),
          }));
        }
      }
      return next;
    });
  };

  const buildConfigForTrack = (tpl, code) => {
    if (tpl && isCommitteeTemplate(tpl)) {
      const st = committeeStateByCode[code] || defaultCommitteeEditorState();
      return buildCommitteeConfigForApi(st);
    }
    if (selectedCodes.has(code) && configByCode[code]) {
      return parseConfigJson(configByCode[code]);
    }
    return {};
  };

  const setInstrumentUseEvalDefault = (code, useEval) => {
    setInstrumentByCode((prev) => {
      const cur = prev[code] || {
        useEvalDefault: true,
        template: evalInstrument.template_code,
        version: String(evalInstrument.version),
      };
      if (useEval) {
        return {
          ...prev,
          [code]: {
            useEvalDefault: true,
            template: evalInstrument.template_code,
            version: String(evalInstrument.version),
          },
        };
      }
      return {
        ...prev,
        [code]: {
          useEvalDefault: false,
          template: cur.template || evalInstrument.template_code,
          version: cur.version || String(evalInstrument.version),
        },
      };
    });
  };

  const updateInstrumentField = (code, field, value) => {
    setInstrumentByCode((prev) => {
      const cur = prev[code] || {
        useEvalDefault: true,
        template: evalInstrument.template_code,
        version: String(evalInstrument.version),
      };
      return { ...prev, [code]: { ...cur, [field]: value } };
    });
  };

  const applyEnabledTracks = async () => {
    if (!evalId?.trim()) return;
    setErrLocal("");
    for (const t of selectedCommitteeTemplates) {
      const st = committeeStateByCode[t.code] || defaultCommitteeEditorState();
      const msg = validateCommitteeEditorState(st, { participantEmails: participantEmailSet });
      if (msg) {
        setErrLocal(`Committee track "${t.code}": ${msg}`);
        return;
      }
    }
    setLoading(true);
    try {
      const tracks = templates.map((t) => {
        const code = t.code;
        const enabled = selectedCodes.has(code) ? 1 : 0;
        let config = {};
        if (selectedCodes.has(code)) {
          config = buildConfigForTrack(t, code);
        }
        const st = instrumentByCode[code] || {
          useEvalDefault: true,
          template: evalInstrument.template_code,
          version: String(evalInstrument.version),
        };
        let instrument_template_code = null;
        let instrument_version = null;
        if (!st.useEvalDefault) {
          const tpl = String(st.template || "").trim();
          if (!tpl) {
            throw new Error(
              `Per-track questionnaire: enter a template code for "${code}" or check "Use evaluation default".`
            );
          }
          const v = parseInt(String(st.version ?? "1"), 10);
          instrument_template_code = tpl;
          instrument_version = Number.isFinite(v) && v > 0 ? v : 1;
        }
        return {
          code,
          enabled,
          config,
          instrument_template_code,
          instrument_version,
        };
      });
      await apiPost(`/api/v1/evaluations/${encodeURIComponent(evalId)}/tracks`, { tracks });
      await loadAll();
    } catch (e) {
      setErrLocal(e?.message || String(e));
    } finally {
      setLoading(false);
    }
  };

  const runGenerate = async (dryRun) => {
    if (!evalId?.trim()) return;
    if (Object.keys(participantsById).length === 0) {
      setErrLocal("Invite at least one participant before generating assignments.");
      return;
    }
    setErrLocal("");
    setLoading(true);
    try {
      const data = await apiPost(`/api/v1/evaluations/${encodeURIComponent(evalId)}/tracks/generate-assignments`, {
        dry_run: dryRun,
        send_email_notifications: !dryRun && sendEmailNotifications,
      });
      if (dryRun) {
        setDryRunResult(data);
        setGenResult(null);
        setNotifyResult(null);
      } else {
        setGenResult(data);
        setDryRunResult(null);
        setNotifyResult(null);
      }
      await loadAll();
    } catch (e) {
      setErrLocal(e?.message || String(e));
    } finally {
      setLoading(false);
    }
  };

  const runNotifyLinks = async (onlyPending = false) => {
    if (!evalId?.trim() || typeof notifyParticipantLinks !== "function") return;
    setErrLocal("");
    setLoading(true);
    try {
      const data = await notifyParticipantLinks({ onlyPending, includeHubOnly: true });
      setNotifyResult(data);
    } catch (e) {
      setErrLocal(e?.message || String(e));
    } finally {
      setLoading(false);
    }
  };

  const copyText = async (text) => {
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      const ta = document.createElement("textarea");
      ta.value = text;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      document.body.removeChild(ta);
    }
  };

  const respondentLabel = (participantId) => {
    const p = participantsById[participantId];
    if (!p) return participantId;
    return [p.full_name, p.email].filter(Boolean).join(" — ") || p.email;
  };

  const subjectLabel = (participantId) => {
    if (!participantId) return "—";
    return respondentLabel(participantId);
  };

  const templatesEmpty = templates.length === 0;

  const selectionSummary = useMemo(() => {
    const codes = templates.filter((t) => selectedCodes.has(t.code)).map((t) => t.code);
    return codes.join(", ") || "—";
  }, [templates, selectedCodes]);

  return (
    <Card
      title="Assessment tracks & assignments"
      subtitle="Configure which programmes run for this evaluation (you can save tracks before participants exist). Generating assignment tasks requires a participant list."
      right={<Badge tone="blue">Consultant</Badge>}
    >
      <div style={{ marginTop: 6 }}>{focus}</div>

      {(errLocal || loading) && (
        <div style={{ marginTop: 10, display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
          {loading ? <Badge tone="amber">Loading…</Badge> : null}
          {errLocal ? (
            <span style={{ color: "#B91C1C", fontWeight: 700, whiteSpace: "pre-wrap" }}>{errLocal}</span>
          ) : null}
        </div>
      )}

      {templatesEmpty ? (
        <div style={{ marginTop: 14, padding: 12, background: "#FFFBEB", border: "1px solid #FDE68A", borderRadius: 12 }}>
          <b>No track templates in the database.</b> Insert rows into <code>assessment_track_templates</code> (or seed
          data) so tracks can be enabled. The API <code>GET /api/v1/track-templates</code> is empty.
        </div>
      ) : null}

      <div style={{ marginTop: 16 }}>
        <div style={{ fontWeight: 900, fontSize: 14, marginBottom: 8 }}>1) Track template library</div>
        <div style={tableWrapStyle()}>
          <table
            style={{
              width: "100%",
              borderCollapse: "collapse",
              fontSize: 13,
              tableLayout: "fixed",
            }}
          >
            <colgroup>
              <col style={{ width: "52px" }} />
              <col style={{ width: "13%" }} />
              <col />
              <col style={{ width: "17%" }} />
              <col style={{ width: "14%" }} />
              <col style={{ width: "16%" }} />
            </colgroup>
            <thead>
              <tr style={{ background: "#F8FAFC", borderBottom: "1px solid #E5E7EB" }}>
                <th
                  style={{
                    ...tdStyle(),
                    fontWeight: 800,
                    textAlign: "center",
                    verticalAlign: "bottom",
                  }}
                >
                  Enable
                </th>
                <th
                  style={{
                    ...tdStyle(),
                    fontWeight: 800,
                    textAlign: "left",
                    verticalAlign: "bottom",
                  }}
                >
                  Code
                </th>
                <th
                  style={{
                    ...tdStyle(),
                    fontWeight: 800,
                    textAlign: "left",
                    verticalAlign: "bottom",
                  }}
                >
                  Name
                </th>
                <th
                  style={{
                    ...tdStyle(),
                    fontWeight: 800,
                    textAlign: "left",
                    verticalAlign: "bottom",
                  }}
                >
                  Assignment type
                </th>
                <th
                  style={{
                    ...tdStyle(),
                    fontWeight: 800,
                    textAlign: "left",
                    verticalAlign: "bottom",
                  }}
                >
                  Subject mode
                </th>
                <th
                  style={{
                    ...tdStyle(),
                    fontWeight: 800,
                    textAlign: "left",
                    verticalAlign: "bottom",
                  }}
                >
                  Default instrument
                </th>
              </tr>
            </thead>
            <tbody>
              {templates.map((t) => (
                <tr key={t.id || t.code} style={{ borderBottom: "1px solid #F1F5F9" }}>
                  <td
                    style={{
                      ...tdStyle(),
                      textAlign: "center",
                      verticalAlign: "middle",
                    }}
                  >
                    <input
                      type="checkbox"
                      checked={selectedCodes.has(t.code)}
                      onChange={() => toggleCode(t.code)}
                      disabled={disabledBase}
                      style={{ margin: 0, verticalAlign: "middle" }}
                    />
                  </td>
                  <td
                    style={{
                      ...tdStyle(),
                      fontWeight: 800,
                      fontFamily:
                        'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace',
                      fontSize: 12,
                      verticalAlign: "middle",
                      whiteSpace: "nowrap",
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                    }}
                    title={t.code}
                  >
                    {t.code}
                  </td>
                  <td
                    style={{
                      ...tdStyle(),
                      verticalAlign: "middle",
                      wordBreak: "break-word",
                    }}
                  >
                    {t.name}
                  </td>
                  <td
                    style={{
                      ...tdStyle(),
                      verticalAlign: "middle",
                      fontFamily:
                        'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace',
                      fontSize: 12,
                      whiteSpace: "nowrap",
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                    }}
                    title={t.assignment_type}
                  >
                    {t.assignment_type}
                  </td>
                  <td
                    style={{
                      ...tdStyle(),
                      verticalAlign: "middle",
                      whiteSpace: "nowrap",
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                    }}
                    title={t.subject_mode}
                  >
                    {t.subject_mode}
                  </td>
                  <td
                    style={{
                      ...tdStyle(),
                      verticalAlign: "middle",
                      fontFamily:
                        'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace',
                      fontSize: 12,
                      whiteSpace: "nowrap",
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                    }}
                    title={`${t.default_template_code} v${t.default_version}`}
                  >
                    {t.default_template_code} v{t.default_version}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {selectedCommitteeTemplates.length > 0 ? (
        <div style={{ marginTop: 16 }}>
          <div style={{ fontWeight: 900, fontSize: 14, marginBottom: 8 }}>1b) Committee evaluation</div>
          {selectedCommitteeTemplates.map((t) => (
            <div key={t.code} style={{ marginBottom: 12 }}>
              <Field label={`${t.name || t.code} (${t.code})`}>
                <CommitteeTrackConfigEditor
                  ui={ui}
                  disabled={disabledBase}
                  participants={participantList}
                  state={committeeStateByCode[t.code] || defaultCommitteeEditorState()}
                  onChange={(next) =>
                    setCommitteeStateByCode((prev) => ({
                      ...prev,
                      [t.code]: next,
                    }))
                  }
                />
              </Field>
            </div>
          ))}
        </div>
      ) : null}

      {selectedNonCommitteeWithConfig.length > 0 ? (
        <div style={{ marginTop: 16 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 8 }}>
            <div style={{ fontWeight: 900, fontSize: 14 }}>1b) Other track config (advanced JSON)</div>
            <Button variant="soft" disabled={disabledBase} onClick={() => setShowAdvancedJson((v) => !v)}>
              {showAdvancedJson ? "Hide" : "Show"}
            </Button>
          </div>
          {showAdvancedJson ? (
            <div style={{ fontSize: 12, color: "#64748B", marginBottom: 8 }}>
              Only needed for unusual track settings. Committee tracks use the editor above.
            </div>
          ) : null}
          {showAdvancedJson
            ? selectedNonCommitteeWithConfig.map((t) => (
                <Field key={t.code} label={`Config: ${t.code}`}>
                  <textarea
                    value={configByCode[t.code] || ""}
                    onChange={(e) => setConfigByCode((prev) => ({ ...prev, [t.code]: e.target.value }))}
                    disabled={disabledBase}
                    rows={4}
                    style={{ width: "100%", fontFamily: "monospace", fontSize: 12 }}
                    spellCheck={false}
                    placeholder="{}"
                  />
                </Field>
              ))
            : null}
        </div>
      ) : null}

      <div style={{ marginTop: 16 }}>
        <div style={{ fontWeight: 900, fontSize: 14, marginBottom: 8 }}>1c) Per-track questionnaire (optional)</div>
        <div style={{ fontSize: 12, color: "#64748B", marginBottom: 10 }}>
          By default each track uses the <b>evaluation</b> instrument from Step 2 (Questionnaire):{" "}
          <code>
            {evalInstrument.template_code} v{evalInstrument.version}
          </code>
          . Uncheck &quot;Use evaluation default&quot; to point a track at a different template/version (must exist in
          your question bank).
        </div>
        <div style={tableWrapStyle()}>
          <table
            style={{
              width: "100%",
              borderCollapse: "collapse",
              fontSize: 13,
              tableLayout: "fixed",
            }}
          >
            <colgroup>
              <col style={{ width: "14%" }} />
              <col style={{ width: "24%" }} />
              <col />
              <col style={{ width: 100 }} />
            </colgroup>
            <thead>
              <tr style={{ background: "#F8FAFC", borderBottom: "1px solid #E5E7EB" }}>
                <th style={{ ...tdStyle(), fontWeight: 800, textAlign: "left", verticalAlign: "bottom" }}>Code</th>
                <th style={{ ...tdStyle(), fontWeight: 800, textAlign: "left", verticalAlign: "bottom" }}>
                  Use evaluation default
                </th>
                <th style={{ ...tdStyle(), fontWeight: 800, textAlign: "left", verticalAlign: "bottom" }}>Template</th>
                <th style={{ ...tdStyle(), fontWeight: 800, textAlign: "left", verticalAlign: "bottom" }}>Version</th>
              </tr>
            </thead>
            <tbody>
              {templates.map((t) => {
                const st = instrumentByCode[t.code] || {
                  useEvalDefault: true,
                  template: evalInstrument.template_code,
                  version: String(evalInstrument.version),
                };
                const useDef = !!st.useEvalDefault;
                return (
                  <tr key={`inst-${t.code}`} style={{ borderBottom: "1px solid #F1F5F9" }}>
                    <td
                      style={{
                        ...tdStyle(),
                        fontWeight: 800,
                        fontFamily:
                          'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace',
                        fontSize: 12,
                        verticalAlign: "middle",
                      }}
                    >
                      {t.code}
                    </td>
                    <td style={{ ...tdStyle(), verticalAlign: "middle" }}>
                      <label
                        style={{
                          display: "flex",
                          gap: 8,
                          alignItems: "center",
                          cursor: disabledBase ? "default" : "pointer",
                        }}
                      >
                        <input
                          type="checkbox"
                          checked={useDef}
                          disabled={disabledBase}
                          onChange={(e) => setInstrumentUseEvalDefault(t.code, e.target.checked)}
                        />
                        <span style={{ fontSize: 12 }}>{useDef ? "Yes (Step 2)" : "No (custom)"}</span>
                      </label>
                    </td>
                    <td style={{ ...tdStyle(), verticalAlign: "middle" }}>
                      <input
                        type="text"
                        value={st.template}
                        disabled={disabledBase || useDef}
                        onChange={(e) => updateInstrumentField(t.code, "template", e.target.value)}
                        style={{
                          width: "100%",
                          boxSizing: "border-box",
                          padding: "6px 8px",
                          fontSize: 13,
                          fontFamily:
                            'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace',
                        }}
                        placeholder={evalInstrument.template_code}
                        spellCheck={false}
                      />
                    </td>
                    <td style={{ ...tdStyle(), verticalAlign: "middle", width: 100 }}>
                      <input
                        type="number"
                        min={1}
                        value={st.version}
                        disabled={disabledBase || useDef}
                        onChange={(e) => updateInstrumentField(t.code, "version", e.target.value)}
                        style={{ width: "100%", boxSizing: "border-box", padding: "6px 8px", fontSize: 13 }}
                      />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      <div style={{ marginTop: 14, display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
        <Button
          variant="primary"
          disabled={disabledBase || templatesEmpty}
          onClick={applyEnabledTracks}
          title={!hasEval ? "Select an evaluation first." : "Save"}
        >
          {loading ? "Saving…" : "Save enabled tracks"}
        </Button>
        <Badge tone="gray">Selected: {selectionSummary}</Badge>
        <Button variant="soft" disabled={busy} onClick={loadAll}>
          Refresh
        </Button>
      </div>

      <div style={{ marginTop: 20 }}>
        <div style={{ fontWeight: 900, fontSize: 14, marginBottom: 8 }}>2) Tracks on this evaluation</div>
        <div style={tableWrapStyle()}>
          <table
            style={{
              width: "100%",
              borderCollapse: "collapse",
              fontSize: 13,
              tableLayout: "fixed",
            }}
          >
            <colgroup>
              <col style={{ width: "14%" }} />
              <col style={{ width: "22%" }} />
              <col style={{ width: "10%" }} />
              <col style={{ width: "22%" }} />
              <col />
            </colgroup>
            <thead>
              <tr style={{ background: "#F8FAFC", borderBottom: "1px solid #E5E7EB" }}>
                <th style={{ ...tdStyle(), fontWeight: 800, textAlign: "left", verticalAlign: "bottom" }}>Code</th>
                <th style={{ ...tdStyle(), fontWeight: 800, textAlign: "left", verticalAlign: "bottom" }}>Name</th>
                <th style={{ ...tdStyle(), fontWeight: 800, textAlign: "center", verticalAlign: "bottom" }}>
                  Enabled
                </th>
                <th style={{ ...tdStyle(), fontWeight: 800, textAlign: "left", verticalAlign: "bottom" }}>
                  instrument override
                </th>
                <th style={{ ...tdStyle(), fontWeight: 800, textAlign: "left", verticalAlign: "bottom" }}>config</th>
              </tr>
            </thead>
            <tbody>
              {evalTracks.length === 0 ? (
                <tr>
                  <td colSpan={5} style={{ ...tdStyle(), color: "#64748B" }}>
                    No rows yet. Select templates above and save.
                  </td>
                </tr>
              ) : (
                evalTracks.map((r) => (
                  <tr key={r.evaluation_track_id} style={{ borderBottom: "1px solid #F1F5F9" }}>
                    <td
                      style={{
                        ...tdStyle(),
                        fontWeight: 800,
                        fontFamily:
                          'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace',
                        fontSize: 12,
                        verticalAlign: "middle",
                      }}
                    >
                      {r.code ?? "—"}
                    </td>
                    <td style={{ ...tdStyle(), verticalAlign: "middle", wordBreak: "break-word" }}>{r.name ?? "—"}</td>
                    <td style={{ ...tdStyle(), textAlign: "center", verticalAlign: "middle" }}>
                      {Number(r.enabled) === 1 ? "yes" : "no"}
                    </td>
                    <td style={{ ...tdStyle(), verticalAlign: "middle", fontSize: 12 }}>
                      {r.instrument_template_code == null && r.instrument_version == null ? (
                        <span style={{ color: "#64748B" }}>
                          {evalInstrument.template_code} v{evalInstrument.version}{" "}
                          <span style={{ fontWeight: 600 }}>(evaluation default)</span>
                        </span>
                      ) : (
                        <>
                          {r.instrument_template_code || "—"}{" "}
                          {r.instrument_version != null ? `v${r.instrument_version}` : ""}
                        </>
                      )}
                    </td>
                    <td
                      style={{
                        ...tdStyle(),
                        verticalAlign: "middle",
                        fontFamily:
                          'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace',
                        fontSize: 11,
                        wordBreak: "break-word",
                      }}
                    >
                      {JSON.stringify(r.config || {}).slice(0, 120)}
                      {JSON.stringify(r.config || {}).length > 120 ? "…" : ""}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div style={{ marginTop: 20 }}>
        <div style={{ fontWeight: 900, fontSize: 14, marginBottom: 8 }}>3) Generate assignments from enabled tracks</div>
        {needsParticipantsToGenerate ? (
          <div
            style={{
              marginBottom: 10,
              padding: "10px 12px",
              background: "#FFFBEB",
              border: "1px solid #FDE68A",
              borderRadius: 10,
              fontSize: 13,
              color: "#92400E",
            }}
          >
            <b>Participants required.</b> Invite at least one participant first — assignment generation needs people in
            the roster. You can still enable tracks and save configuration above.
          </div>
        ) : null}
        <label style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 10, fontSize: 13, cursor: "pointer" }}>
          <input
            type="checkbox"
            checked={sendEmailNotifications}
            onChange={(e) => setSendEmailNotifications(e.target.checked)}
            disabled={generateDisabled}
          />
          <span>
            After generate, email each person their <b>hub + all task links</b> (recommended). Requires{" "}
            <code>EMAIL_ENABLED=true</code> and SMTP.
          </span>
        </label>
        {genResult && !sendEmailNotifications ? (
          <div
            style={{
              marginBottom: 10,
              padding: "10px 12px",
              background: "#EFF6FF",
              border: "1px solid #BFDBFE",
              borderRadius: 10,
              fontSize: 13,
              color: "#1E3A8A",
            }}
          >
            <b>Assignments created.</b> Email was not sent — use <b>Resend links</b> below when ready.
          </div>
        ) : null}
        {genResult && Number(genResult.email_sent) > 0 ? (
          <div
            style={{
              marginBottom: 10,
              padding: "10px 12px",
              background: "#ECFDF5",
              border: "1px solid #A7F3D0",
              borderRadius: 10,
              fontSize: 13,
              color: "#065F46",
            }}
          >
            Link emails sent to <b>{genResult.email_sent}</b> participant(s).
          </div>
        ) : null}
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
          <Button
            variant="soft"
            disabled={generateDisabled}
            onClick={() => runGenerate(true)}
            title={
              needsParticipantsToGenerate
                ? "Invite participants first"
                : "Preview counts only"
            }
          >
            Dry run (no DB writes)
          </Button>
          <Button
            variant="primary"
            disabled={generateDisabled}
            onClick={() => runGenerate(false)}
            title={
              needsParticipantsToGenerate
                ? "Invite participants first"
                : "Create assignment rows + tokens"
            }
          >
            Generate assignments
          </Button>
          {participantCount > 0 ? (
            <Badge tone="gray">
              Participants: {participantCount}
            </Badge>
          ) : null}
        </div>
        {dryRunResult?.skipped_items?.length > 0 ? (
          <div
            style={{
              marginTop: 10,
              padding: 12,
              background: "#FFFBEB",
              border: "1px solid #FDE68A",
              borderRadius: 8,
              fontSize: 13,
              color: "#92400E",
            }}
          >
            <b>Skipped tracks</b>
            <ul style={{ margin: "8px 0 0", paddingLeft: 18 }}>
              {dryRunResult.skipped_items.map((s, i) => (
                <li key={i}>
                  <code>{s.track_code || "—"}</code>: {s.detail || s.reason}
                </li>
              ))}
            </ul>
          </div>
        ) : null}
        {dryRunResult ? (
          <pre style={{ marginTop: 10, padding: 12, background: "#F8FAFC", borderRadius: 8, fontSize: 12, overflow: "auto" }}>
            {JSON.stringify(dryRunResult, null, 2)}
          </pre>
        ) : null}
        {genResult?.skipped_items?.length > 0 ? (
          <div
            style={{
              marginTop: 10,
              padding: 12,
              background: "#FFFBEB",
              border: "1px solid #FDE68A",
              borderRadius: 8,
              fontSize: 13,
              color: "#92400E",
            }}
          >
            <b>Skipped tracks</b>
            <ul style={{ margin: "8px 0 0", paddingLeft: 18 }}>
              {genResult.skipped_items.map((s, i) => (
                <li key={i}>
                  <code>{s.track_code || "—"}</code>: {s.detail || s.reason}
                </li>
              ))}
            </ul>
          </div>
        ) : null}
        {genResult ? (
          <pre style={{ marginTop: 10, padding: 12, background: "#ECFDF5", borderRadius: 8, fontSize: 12, overflow: "auto" }}>
            {JSON.stringify(genResult, null, 2)}
          </pre>
        ) : null}
      </div>

      <div style={{ marginTop: 20 }}>
        <div style={{ fontWeight: 900, fontSize: 14, marginBottom: 8 }}>3b) Notify participants</div>
        <div style={{ fontSize: 12, color: "#64748B", marginBottom: 10, lineHeight: 1.45 }}>
          Resend hub and questionnaire links without re-inviting. Use after generate if email was skipped, or to nudge
          people who have not finished.
        </div>
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center", marginBottom: 10 }}>
          <Button
            variant="primary"
            disabled={disabledBase || assignments.length === 0 || typeof notifyParticipantLinks !== "function"}
            onClick={() => runNotifyLinks(false)}
          >
            {loading ? "Sending…" : "Resend links (all tasks)"}
          </Button>
          <Button
            variant="soft"
            disabled={disabledBase || assignments.length === 0 || typeof notifyParticipantLinks !== "function"}
            onClick={() => runNotifyLinks(true)}
            title="Only assignments not yet marked responded"
          >
            Resend (pending tasks only)
          </Button>
        </div>
        {notifyResult ? (
          <div
            style={{
              marginBottom: 12,
              padding: 12,
              borderRadius: 10,
              background: "#ECFDF5",
              border: "1px solid #A7F3D0",
              fontSize: 13,
              color: "#065F46",
            }}
          >
            Sent to <b>{notifyResult.email_sent ?? 0}</b> participant(s).
            {(notifyResult.email_failed || []).length > 0 ? (
              <span style={{ marginLeft: 8 }}>Failed: {(notifyResult.email_failed || []).length}</span>
            ) : null}
            {(notifyResult.skipped_no_links || []).length > 0 ? (
              <span style={{ marginLeft: 8, color: "#64748B" }}>
                Skipped: {(notifyResult.skipped_no_links || []).length}
              </span>
            ) : null}
          </div>
        ) : null}
      </div>

      <div style={{ marginTop: 20 }}>
        <div style={{ fontWeight: 900, fontSize: 14, marginBottom: 8 }}>4) Assignments (portal links)</div>
        <div style={tableWrapStyle()}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
            <thead style={{ background: "#F8FAFC" }}>
              <tr>
                {["Respondent", "Subject", "Type", "Committee", "Status", "Portal URL"].map((h) => (
                  <th key={h} style={{ ...tdStyle(), fontWeight: 800 }}>
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {assignments.length === 0 ? (
                <tr>
                  <td colSpan={6} style={{ ...tdStyle(), color: "#64748B" }}>
                    No assignments yet. Invite participants, enable tracks, then generate.
                  </td>
                </tr>
              ) : (
                assignments.map((a) => (
                  <tr key={a.assignment_id} style={{ borderBottom: "1px solid #F1F5F9" }}>
                    <td style={tdStyle()}>{respondentLabel(a.respondent_participant_id)}</td>
                    <td style={tdStyle()}>{subjectLabel(a.subject_participant_id)}</td>
                    <td style={tdStyle()}>{a.assignment_type}</td>
                    <td style={tdStyle()}>{a.committee_name || "—"}</td>
                    <td style={tdStyle()}>{a.status}</td>
                    <td style={tdStyle()}>
                      {a.portal_url ? (
                        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
                          <a href={a.portal_url} target="_blank" rel="noreferrer" style={{ fontWeight: 800 }}>
                            Open
                          </a>
                          <Button variant="soft" onClick={() => copyText(a.portal_url)}>
                            Copy
                          </Button>
                        </div>
                      ) : (
                        "—"
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {renderFlowBar({
        left: [
          { key: "back", label: "← Participants", onClick: () => go("/consultant/participants/invite"), variant: "secondary" },
        ],
        right: [
          { key: "next", label: "Questions →", onClick: () => go("/consultant/questions"), variant: "primary" },
        ],
      })}
    </Card>
  );
}
