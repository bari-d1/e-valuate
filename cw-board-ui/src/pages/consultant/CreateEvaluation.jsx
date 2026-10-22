import React, { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { orgApi, sectorLabel } from "../../api/orgApi.js";
import { color, font, space } from "../../theme.js";

function yearOf(iso) {
  const y = iso ? Number(String(iso).slice(0, 4)) : NaN;
  return Number.isFinite(y) && y > 1900 ? y : new Date().getFullYear();
}

/**
 * Create Evaluation page (router-based)
 * Step 1: the company (organisation) and the evaluation's own details.
 * Step 2: the questionnaire template (kept for now; a later task removes it).
 */
export default function CreateEvaluationPage({
  ui,

  // evaluation id sources / success cues
  evalId,
  lastCreatedEvalId,
  questionnaireSavedAt,
  questionnaireSavedForEvalId,
  setQuestionnaireSavedAt,
  setQuestionnaireSavedForEvalId,

  // questionnaire selection
  selectedTemplate,
  setSelectedTemplate,
  selectedVersion,
  setSelectedVersion,

  // global UI state
  busy,
  focus,

  // actions / navigation
  createEvaluation, // async (fields) => created evaluation
  setEvaluationQuestionnaire,
  go,

  // styles
  inputStyle,
}) {
  const { Card, Badge, Field, Button } = ui;
  const [params] = useSearchParams();
  const lockedOrgId = params.get("organisation") || "";

  const [orgs, setOrgs] = useState(null);
  const [subjectTypes, setSubjectTypes] = useState([]);
  const [loadError, setLoadError] = useState("");
  const [organisationId, setOrganisationId] = useState(lockedOrgId);
  const [periodStart, setPeriodStart] = useState("");
  const [periodEnd, setPeriodEnd] = useState("");
  const [deadline, setDeadline] = useState("");
  const [brief, setBrief] = useState("");
  const [scope, setScope] = useState(null); // null until subject types load: then all ticked
  const [name, setName] = useState("");
  const [nameEdited, setNameEdited] = useState(false);
  const [newEvalId, setNewEvalId] = useState("");
  const [created, setCreated] = useState(null);

  useEffect(() => {
    let alive = true;
    Promise.all([orgApi.list(), orgApi.taxonomy()])
      .then(([o, t]) => {
        if (!alive) return;
        setOrgs(o.items);
        setSubjectTypes(t.subject_types);
        setScope((prev) => prev || t.subject_types.map((s) => s.code));
      })
      .catch((e) => alive && setLoadError(e?.message || String(e)));
    return () => {
      alive = false;
    };
  }, []);

  const defaultName = `${yearOf(periodEnd || deadline)} Board Evaluation`;
  const effectiveName = nameEdited ? name : defaultName;
  const lockedOrg = lockedOrgId && orgs ? orgs.find((o) => o.organisation_id === lockedOrgId) : null;
  const scopeCount = scope ? scope.length : 0;
  const periodError = periodStart && periodEnd && periodEnd < periodStart ? "The review period ends before it starts." : "";

  const reasonCreate = !organisationId
    ? "Choose the company this evaluation is for."
    : !scopeCount
    ? "Tick at least one subject type."
    : periodError;
  const canCreate = !reasonCreate;

  // ✅ stable ID source (do not rely on `result.action`)
  const effectiveEvalId = useMemo(() => {
    return String(evalId || lastCreatedEvalId || "").trim();
  }, [evalId, lastCreatedEvalId]);

  const reasonNeedsEval = !effectiveEvalId
    ? "Create an evaluation first (so an Evaluation ID exists)."
    : "";

  // Questionnaire inputs are only usable after eval exists
  const disableQuestionnaireSection = busy || !effectiveEvalId;

  // ✅ success cue for questionnaire save (Step 2)
  const savedForThisEval =
    !!effectiveEvalId &&
    String(questionnaireSavedForEvalId || "").trim() === String(effectiveEvalId || "").trim();

  const submit = async () => {
    const data = await createEvaluation({
      evaluation_id: newEvalId.trim() || undefined,
      organisation_id: organisationId,
      name: effectiveName.trim(),
      review_period_start: periodStart || null,
      review_period_end: periodEnd || null,
      deadline: deadline || null,
      brief: brief.trim() || null,
      subject_type_codes: scope,
    });
    if (data) setCreated(data);
  };

  const toggleScope = (code) =>
    setScope((prev) => (prev.includes(code) ? prev.filter((c) => c !== code) : [...prev, code]));

  return (
    <Card
      title="Create evaluation"
      subtitle="Choose the company, then set this year's review period, deadline and scope."
    >
      {focus}

      {/* ---------------- Step 1: Company and evaluation details ---------------- */}
      <h2 style={{ margin: `${space.md}px 0 ${space.sm}px`, fontSize: 15, fontWeight: font.weight.heavy, color: color.text }}>
        Step 1 — Company and details
      </h2>

      {loadError ? (
        <div role="alert" style={{ marginBottom: space.md, color: color.danger, fontWeight: font.weight.bold }}>{loadError}</div>
      ) : null}

      <div style={{ display: "grid", gap: space.md, gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))" }}>
        <div style={{ gridColumn: "1 / -1" }}>
          {lockedOrgId ? (
            <Field label="Company">
              <div style={{ ...inputStyle(), background: color.surfaceMuted, display: "flex", justifyContent: "space-between", gap: space.sm, flexWrap: "wrap" }}>
                <span style={{ fontWeight: font.weight.bold }}>{lockedOrg ? lockedOrg.name : orgs ? "Unknown company" : "Loading…"}</span>
                {lockedOrg ? <span style={{ color: color.textMuted }}>{sectorLabel(lockedOrg.sector_key, lockedOrg.sector_sub_type)}</span> : null}
              </div>
            </Field>
          ) : (
            <Field label="Company" hint="Not listed? Add it on the Companies page first.">
              <select value={organisationId} onChange={(e) => setOrganisationId(e.target.value)} style={inputStyle()} disabled={!orgs}>
                <option value="">{orgs ? "Choose a company…" : "Loading…"}</option>
                {(orgs || []).map((o) => (
                  <option key={o.organisation_id} value={o.organisation_id}>
                    {o.name}
                  </option>
                ))}
              </select>
            </Field>
          )}
        </div>

        <Field label="Evaluation name">
          <input
            value={effectiveName}
            onChange={(e) => {
              setNameEdited(true);
              setName(e.target.value);
            }}
            style={inputStyle()}
            autoComplete="off"
          />
        </Field>

        <Field label="Deadline">
          <input type="date" value={deadline} onChange={(e) => setDeadline(e.target.value)} style={inputStyle()} />
        </Field>

        <Field label="Review period start">
          <input type="date" value={periodStart} onChange={(e) => setPeriodStart(e.target.value)} style={inputStyle()} />
        </Field>

        <Field label="Review period end" hint={periodError || undefined}>
          <input type="date" value={periodEnd} onChange={(e) => setPeriodEnd(e.target.value)} style={inputStyle()} />
        </Field>

        <div style={{ gridColumn: "1 / -1" }}>
          <Field label="Brief" hint="What the client wants from this evaluation, in a few sentences.">
            <textarea value={brief} onChange={(e) => setBrief(e.target.value)} rows={3} style={{ ...inputStyle(), resize: "vertical" }} />
          </Field>
        </div>

        <fieldset style={{ gridColumn: "1 / -1", margin: 0, padding: 0, border: 0, minWidth: 0 }}>
          <legend style={{ padding: 0, fontSize: 13, fontWeight: font.weight.bold, color: color.text }}>Subject types in scope</legend>
          <div style={{ marginTop: 2, fontSize: font.small, color: color.textMuted }}>Who or what this evaluation covers. All are included by default.</div>
          <div style={{ marginTop: space.sm, display: "grid", gap: space.sm, gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))" }}>
            {subjectTypes.map((s) => (
              <label key={s.code} style={{ display: "flex", gap: 8, alignItems: "flex-start", fontSize: font.body, color: color.text, cursor: "pointer" }}>
                <input type="checkbox" checked={!!scope && scope.includes(s.code)} onChange={() => toggleScope(s.code)} style={{ marginTop: 3 }} />
                <span>{s.name}</span>
              </label>
            ))}
          </div>
        </fieldset>

        <details style={{ gridColumn: "1 / -1" }}>
          <summary style={{ cursor: "pointer", fontSize: 13, color: color.textMuted }}>Advanced: choose the evaluation ID</summary>
          <div style={{ marginTop: space.sm, maxWidth: 320 }}>
            <Field label="Evaluation ID (optional)">
              <input value={newEvalId} onChange={(e) => setNewEvalId(e.target.value)} placeholder="Leave blank to generate one" style={inputStyle()} autoComplete="off" spellCheck={false} />
            </Field>
          </div>
        </details>
      </div>

      {/* Status */}
      <div style={{ marginTop: 14, display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
        <Button onClick={submit} disabled={busy || !canCreate} variant="primary" title={reasonCreate || "Create evaluation"}>
          {busy ? "Creating…" : "Create evaluation"}
        </Button>
        <Button onClick={() => go(lockedOrgId ? `/consultant/companies/${lockedOrgId}/evaluations` : "/consultant/evaluations")} disabled={busy} variant="secondary">
          Cancel
        </Button>
        {reasonCreate ? <span style={{ fontSize: 13, color: "#92400E" }}>{reasonCreate}</span> : null}
        {created || lastCreatedEvalId ? (
          <Badge tone="green">Created: {(created && created.name) || lastCreatedEvalId}</Badge>
        ) : null}
      </div>

      {/* ---------------- Step 2: Questionnaire ---------------- */}
      <div style={{ marginTop: 18, paddingTop: 14, borderTop: "1px solid #E5E7EB" }}>
        <div style={{ fontWeight: 900, color: "#0F172A", marginBottom: 6 }}>
          Step 2 — Questionnaire (Template + Version)
        </div>

        <div style={{ marginTop: 6, color: "#64748B", fontSize: 13 }}>
          This saves the questionnaire selection to the backend for this evaluation.
        </div>

        {savedForThisEval ? (
          <div style={{ marginTop: 10 }}>
            <Badge tone="green">
              ✓ Questionnaire saved for this evaluation
              {questionnaireSavedAt ? ` • ${questionnaireSavedAt}` : ""}
            </Badge>
          </div>
        ) : null}

        <div style={{ marginTop: 12, display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
          <Field label="Template">
            <input
              value={selectedTemplate || ""}
              onChange={(e) => {
                setSelectedTemplate(e.target.value);
                setQuestionnaireSavedForEvalId("");
                setQuestionnaireSavedAt("");
              }}
              style={inputStyle()}
              disabled={disableQuestionnaireSection}
              placeholder="e.g., DEFAULT"
            />
          </Field>

          <Field label="Version">
            <input
              value={selectedVersion || ""}
              onChange={(e) => {
                setSelectedVersion(e.target.value);
                setQuestionnaireSavedForEvalId("");
                setQuestionnaireSavedAt("");
              }}
              style={inputStyle()}
              disabled={disableQuestionnaireSection}
              placeholder="e.g., 1"
            />
          </Field>
        </div>

        <div style={{ marginTop: 12, display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
          <Button
            onClick={setEvaluationQuestionnaire}
            disabled={busy || !effectiveEvalId}
            variant="secondary"
            title={reasonNeedsEval || "Save questionnaire to backend"}
          >
            Save Questionnaire
          </Button>

          <Button
            onClick={() => go("/consultant/participants/invite")}
            disabled={busy || !effectiveEvalId}
            variant="primary"
            title={reasonNeedsEval || "Continue to invite participants"}
          >
            Next: Invite Participants →
          </Button>

          {!effectiveEvalId ? <Badge tone="amber">Locked: {reasonNeedsEval}</Badge> : null}
        </div>
      </div>
    </Card>
  );
}
