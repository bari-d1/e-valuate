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

const monoFont = 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace';
const sectionTitleStyle = { fontWeight: 900, fontSize: 15, color: "#0F172A" };
const sectionHintStyle = { marginTop: 2, fontSize: 13, color: "#64748B", lineHeight: 1.45 };
const thStyle = { fontWeight: 800, textAlign: "left", verticalAlign: "bottom" };
const visuallyHidden = {
  position: "absolute",
  width: 1,
  height: 1,
  overflow: "hidden",
  clip: "rect(0 0 0 0)",
  whiteSpace: "nowrap",
};
const linkButtonStyle = {
  padding: 0,
  border: 0,
  background: "none",
  color: "#1D4ED8",
  fontWeight: 700,
  fontSize: 13,
  cursor: "pointer",
  textDecoration: "underline",
};
const compactInputStyle = {
  display: "block",
  width: "100%",
  marginTop: 2,
  padding: "6px 8px",
  fontSize: 13,
  border: "1px solid #CBD5E1",
  borderRadius: 8,
};

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

  // Name on top, email underneath, for the tasks table
  const personCell = (participantId) => {
    const p = participantsById[participantId];
    if (!p) return participantId;
    return (
      <>
        <div style={{ fontWeight: 700, color: "#0F172A" }}>{p.full_name || p.email}</div>
        {p.full_name ? <div style={{ fontSize: 12, color: "#64748B" }}>{p.email}</div> : null}
      </>
    );
  };

  // Track codes (also used as assignment types) → the template's display name
  const trackName = (code) => templates.find((t) => t.code === code)?.name || code || "—";

  const templatesEmpty = templates.length === 0;

  // Tracks currently saved as enabled on the evaluation
  const savedEnabledCodes = useMemo(
    () => new Set(evalTracks.filter((r) => Number(r.enabled) === 1).map((r) => r.code)),
    [evalTracks]
  );
  const selectionDirty =
    savedEnabledCodes.size !== selectedCodes.size || [...selectedCodes].some((c) => !savedEnabledCodes.has(c));

  return (
    <Card
      title="Assessment tracks & assignments"
      subtitle="Choose the assessments to run, then generate a questionnaire task for each participant."
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

      {templatesEmpty && !loading ? (
        <div style={{ marginTop: 14, padding: 12, background: "#FFFBEB", border: "1px solid #FDE68A", borderRadius: 12 }}>
          <b>No assessment tracks are set up yet.</b> Ask an administrator to load the track templates.
        </div>
      ) : null}

      <div style={{ marginTop: 16 }}>
        <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 10, flexWrap: "wrap" }}>
          <div>
            <div style={sectionTitleStyle}>Tracks</div>
            <div style={sectionHintStyle}>
              Tick the assessments to run in this evaluation, then save. Each track uses the evaluation questionnaire (
              {evalInstrument.template_code} v{evalInstrument.version}) unless you customise it.
            </div>
          </div>
          <label style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 13, color: "#475569", cursor: "pointer" }}>
            <input type="checkbox" checked={showAdvancedJson} onChange={(e) => setShowAdvancedJson(e.target.checked)} />
            Show technical details
          </label>
        </div>

        <div style={{ ...tableWrapStyle(), marginTop: 10 }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
            <thead>
              <tr style={{ background: "#F8FAFC", borderBottom: "1px solid #E5E7EB" }}>
                <th style={{ ...tdStyle(), ...thStyle, width: 44 }}>
                  <span style={visuallyHidden}>Include</span>
                </th>
                <th style={{ ...tdStyle(), ...thStyle }}>Track</th>
                <th style={{ ...tdStyle(), ...thStyle, width: 150 }}>Status</th>
                <th style={{ ...tdStyle(), ...thStyle, width: "34%" }}>Questionnaire</th>
              </tr>
            </thead>
            <tbody>
              {templates.map((t) => {
                const selected = selectedCodes.has(t.code);
                const saved = savedEnabledCodes.has(t.code);
                const status = selected
                  ? saved
                    ? { tone: "green", label: "Active" }
                    : { tone: "amber", label: "Will be added" }
                  : saved
                  ? { tone: "amber", label: "Will be removed" }
                  : { tone: "gray", label: "Not included" };
                const st = instrumentByCode[t.code] || {
                  useEvalDefault: true,
                  template: evalInstrument.template_code,
                  version: String(evalInstrument.version),
                };
                const useDef = !!st.useEvalDefault;
                const checkboxId = `track-${t.code}`;

                return (
                  <tr key={t.id || t.code} style={{ borderBottom: "1px solid #F1F5F9", opacity: selected ? 1 : 0.75 }}>
                    <td style={{ ...tdStyle(), textAlign: "center", verticalAlign: "top" }}>
                      <input
                        id={checkboxId}
                        type="checkbox"
                        checked={selected}
                        onChange={() => toggleCode(t.code)}
                        disabled={disabledBase}
                        style={{ marginTop: 3 }}
                      />
                    </td>
                    <td style={{ ...tdStyle(), verticalAlign: "top" }}>
                      <label htmlFor={checkboxId} style={{ fontWeight: 800, color: "#0F172A", cursor: "pointer" }}>
                        {t.name || t.code}
                      </label>
                      {t.description ? (
                        <div style={{ marginTop: 2, color: "#64748B" }}>{t.description}</div>
                      ) : null}
                      {showAdvancedJson ? (
                        <div style={{ marginTop: 4, fontFamily: monoFont, fontSize: 11, color: "#64748B" }}>
                          {t.code} · {t.assignment_type} · {t.subject_mode}
                        </div>
                      ) : null}
                    </td>
                    <td style={{ ...tdStyle(), verticalAlign: "top" }}>
                      <Badge tone={status.tone}>{status.label}</Badge>
                    </td>
                    <td style={{ ...tdStyle(), verticalAlign: "top" }}>
                      {useDef ? (
                        <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
                          <span style={{ color: "#475569" }}>Evaluation default</span>
                          {selected ? (
                            <button
                              type="button"
                              style={linkButtonStyle}
                              disabled={disabledBase}
                              onClick={() => setInstrumentUseEvalDefault(t.code, false)}
                            >
                              Customise
                            </button>
                          ) : null}
                        </div>
                      ) : (
                        <div style={{ display: "flex", gap: 8, alignItems: "flex-end", flexWrap: "wrap" }}>
                          <label style={{ fontSize: 12, color: "#475569", flex: "1 1 120px" }}>
                            Template
                            <input
                              type="text"
                              value={st.template}
                              disabled={disabledBase}
                              onChange={(e) => updateInstrumentField(t.code, "template", e.target.value)}
                              placeholder={evalInstrument.template_code}
                              spellCheck={false}
                              style={{ ...compactInputStyle, fontFamily: monoFont }}
                            />
                          </label>
                          <label style={{ fontSize: 12, color: "#475569", width: 70 }}>
                            Version
                            <input
                              type="number"
                              min={1}
                              value={st.version}
                              disabled={disabledBase}
                              onChange={(e) => updateInstrumentField(t.code, "version", e.target.value)}
                              style={compactInputStyle}
                            />
                          </label>
                          <button
                            type="button"
                            style={{ ...linkButtonStyle, marginBottom: 8 }}
                            disabled={disabledBase}
                            onClick={() => setInstrumentUseEvalDefault(t.code, true)}
                          >
                            Use default
                          </button>
                        </div>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        <div style={{ marginTop: 12, display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
          <Button
            variant="primary"
            disabled={disabledBase || templatesEmpty}
            onClick={applyEnabledTracks}
            title={!hasEval ? "Select an evaluation first." : "Save the selected tracks"}
          >
            {loading ? "Saving…" : "Save tracks"}
          </Button>
          <Button variant="secondary" disabled={busy} onClick={loadAll}>
            Refresh
          </Button>
          {selectionDirty ? (
            <span style={{ fontSize: 13, color: "#92400E", fontWeight: 700 }}>You have unsaved changes.</span>
          ) : (
            <span style={{ fontSize: 13, color: "#64748B" }}>
              {savedEnabledCodes.size} track{savedEnabledCodes.size === 1 ? "" : "s"} active
            </span>
          )}
        </div>
      </div>

      {selectedCommitteeTemplates.length > 0 ? (
        <div style={{ marginTop: 20 }}>
          <div style={sectionTitleStyle}>Committee setup</div>
          {selectedCommitteeTemplates.map((t) => (
            <div key={t.code} style={{ marginTop: 8, marginBottom: 12 }}>
              <Field label={t.name || t.code}>
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

      {showAdvancedJson && selectedNonCommitteeWithConfig.length > 0 ? (
        <div style={{ marginTop: 20 }}>
          <div style={sectionTitleStyle}>Advanced track settings (JSON)</div>
          <div style={sectionHintStyle}>Only needed for unusual track settings.</div>
          {selectedNonCommitteeWithConfig.map((t) => (
            <Field key={t.code} label={`${t.name || t.code} settings`}>
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
          ))}
        </div>
      ) : null}

      <div style={{ marginTop: 20 }}>
        <div style={sectionTitleStyle}>Generate questionnaire tasks</div>
        <div style={{ ...sectionHintStyle, marginBottom: 10 }}>
          Creates a task for each participant on every active track. Running it again only adds missing tasks.
        </div>
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
          <span>Email each participant their links after generating (recommended)</span>
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
            variant="primary"
            disabled={generateDisabled}
            onClick={() => runGenerate(false)}
            title={
              needsParticipantsToGenerate
                ? "Invite participants first"
                : "Create assignment rows + tokens"
            }
          >
            Generate tasks
          </Button>
          <Button
            variant="secondary"
            disabled={generateDisabled}
            onClick={() => runGenerate(true)}
            title={needsParticipantsToGenerate ? "Invite participants first" : "See what would be created, without saving"}
          >
            Preview
          </Button>
          {participantCount > 0 ? (
            <span style={{ fontSize: 13, color: "#64748B" }}>
              {participantCount} participant{participantCount === 1 ? "" : "s"}
            </span>
          ) : null}
        </div>
        {dryRunResult ? (
          <div style={{ marginTop: 10, fontSize: 13, color: "#1E3A8A" }}>
            <b>Preview:</b> {dryRunResult.created ?? 0} new task{dryRunResult.created === 1 ? "" : "s"} would be
            created; {dryRunResult.existing ?? 0} already exist
            {dryRunResult.skipped ? `; ${dryRunResult.skipped} skipped` : ""}. Nothing has been saved.
          </div>
        ) : null}
        {genResult ? (
          <div style={{ marginTop: 10, fontSize: 13, color: "#065F46" }}>
            <b>Done:</b> {genResult.created ?? 0} new task{genResult.created === 1 ? "" : "s"} created;{" "}
            {genResult.existing ?? 0} already existed
            {genResult.skipped ? `; ${genResult.skipped} skipped` : ""}.
          </div>
        ) : null}
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
                  <b>{trackName(s.track_code)}</b>: {s.detail || s.reason}
                </li>
              ))}
            </ul>
          </div>
        ) : null}
        {showAdvancedJson && dryRunResult ? (
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
                  <b>{trackName(s.track_code)}</b>: {s.detail || s.reason}
                </li>
              ))}
            </ul>
          </div>
        ) : null}
        {showAdvancedJson && genResult ? (
          <pre style={{ marginTop: 10, padding: 12, background: "#ECFDF5", borderRadius: 8, fontSize: 12, overflow: "auto" }}>
            {JSON.stringify(genResult, null, 2)}
          </pre>
        ) : null}
      </div>

      <div style={{ marginTop: 20 }}>
        <div style={sectionTitleStyle}>Send links</div>
        <div style={{ ...sectionHintStyle, marginBottom: 10 }}>
          Email participants their links again, for example if email was off when you generated, or as a reminder.
        </div>
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center", marginBottom: 10 }}>
          <Button
            variant="secondary"
            disabled={disabledBase || assignments.length === 0 || typeof notifyParticipantLinks !== "function"}
            onClick={() => runNotifyLinks(true)}
            title="Only tasks not yet completed"
          >
            {loading ? "Sending…" : "Remind people who haven't finished"}
          </Button>
          <Button
            variant="secondary"
            disabled={disabledBase || assignments.length === 0 || typeof notifyParticipantLinks !== "function"}
            onClick={() => runNotifyLinks(false)}
          >
            Resend to everyone
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
        <div style={sectionTitleStyle}>Questionnaire tasks</div>
        <div style={{ ...tableWrapStyle(), marginTop: 10 }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
            <thead style={{ background: "#F8FAFC" }}>
              <tr>
                {["Answered by", "About", "Track", "Committee", "Status", "Link"].map((h) => (
                  <th key={h} style={{ ...tdStyle(), ...thStyle }}>
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {assignments.length === 0 ? (
                <tr>
                  <td colSpan={6} style={{ ...tdStyle(), color: "#64748B" }}>
                    No tasks yet. Invite participants, save tracks, then generate tasks.
                  </td>
                </tr>
              ) : (
                assignments.map((a) => (
                  <tr key={a.assignment_id} style={{ borderBottom: "1px solid #F1F5F9" }}>
                    <td style={tdStyle()}>{personCell(a.respondent_participant_id)}</td>
                    <td style={tdStyle()}>{a.subject_participant_id ? personCell(a.subject_participant_id) : "—"}</td>
                    <td style={tdStyle()}>{trackName(a.assignment_type)}</td>
                    <td style={tdStyle()}>{a.committee_name || "—"}</td>
                    <td style={tdStyle()}>
                      {a.status === "responded" ? (
                        <Badge tone="green">Completed</Badge>
                      ) : (
                        <Badge tone="gray">Not started</Badge>
                      )}
                    </td>
                    <td style={tdStyle()}>
                      {a.portal_url ? (
                        <div style={{ display: "flex", gap: 12, alignItems: "center", whiteSpace: "nowrap" }}>
                          <a href={a.portal_url} target="_blank" rel="noreferrer" style={{ fontWeight: 700 }}>
                            Open
                          </a>
                          <button type="button" style={linkButtonStyle} onClick={() => copyText(a.portal_url)}>
                            Copy
                          </button>
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

    </Card>
  );
}
