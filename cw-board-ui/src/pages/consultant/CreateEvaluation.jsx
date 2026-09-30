import React, { useMemo } from "react";

/**
 * Create Evaluation page (router-based)
 * - No setTask
 * - Uses go("/route") navigation helper passed from AppLegacy
 */
export default function CreateEvaluationPage({
  ui,

  // state + setters
  tenantName,
  setTenantName,
  sector,
  setSector,
  year,
  setYear,
  newEvalId,
  setNewEvalId,
  regulatorsText,
  setRegulatorsText,

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
  createEvaluation,
  setEvaluationQuestionnaire,
  go,

  // styles
  inputStyle,
}) {
  const { Card, Badge, Field, Button } = ui;

  const canCreate = useMemo(() => {
    return !!tenantName.trim() && !!sector.trim() && !!String(year || "").trim();
  }, [tenantName, sector, year]);

  // ✅ stable ID source (do not rely on `result.action`)
  const effectiveEvalId = useMemo(() => {
    return String(evalId || lastCreatedEvalId || "").trim();
  }, [evalId, lastCreatedEvalId]);

  // Step locks
  const reasonCreate = !canCreate ? "Tenant, Sector, and Year are required." : "";
  const reasonNeedsEval = !effectiveEvalId
    ? "Create an evaluation first (so an Evaluation ID exists)."
    : "";

  // Questionnaire inputs are only usable after eval exists
  const disableQuestionnaireSection = busy || !effectiveEvalId;

  // ✅ success cue for questionnaire save (Step 2)
  const savedForThisEval =
    String(questionnaireSavedForEvalId || "").trim() === String(effectiveEvalId || "").trim();

  return (
    <Card
      title="Create Evaluation"
      subtitle="Create an evaluation cycle (client + sector + year + regulators)."
    >
      {focus}

      {/* ---------------- Step 1: Create Evaluation ---------------- */}
      <div style={{ marginTop: 14, fontWeight: 900, color: "#0F172A" }}>
        Step 1 — Evaluation Details
      </div>

      <div style={{ marginTop: 10, display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
        <Field label="Evaluation ID (optional)">
          <input
            value={newEvalId}
            onChange={(e) => setNewEvalId(e.target.value)}
            placeholder="Leave blank to auto-generate"
            style={inputStyle()}
            autoComplete="off"
            spellCheck={false}
          />
        </Field>

        <Field label="Year">
          <input
            inputMode="numeric"
            value={year}
            onChange={(e) => setYear(e.target.value)}
            style={inputStyle()}
          />
        </Field>

        <Field label="Tenant Name">
          <input
            value={tenantName}
            onChange={(e) => setTenantName(e.target.value)}
            placeholder="e.g. Acme Insurance Plc"
            style={inputStyle()}
            autoComplete="off"
            spellCheck={false}
          />
        </Field>

        <Field label="Sector">
          <input
            value={sector}
            onChange={(e) => setSector(e.target.value)}
            placeholder="e.g. insurance"
            style={inputStyle()}
            autoComplete="off"
            spellCheck={false}
          />
        </Field>

        <div style={{ gridColumn: "1 / -1" }}>
          <Field label="Regulators (comma-separated)" hint='Example: "NAICOM, FRC"'>
            <input
              value={regulatorsText}
              onChange={(e) => setRegulatorsText(e.target.value)}
              placeholder="e.g. NAICOM, FRC"
              style={inputStyle()}
              autoComplete="off"
              spellCheck={false}
            />
          </Field>
        </div>
      </div>

      {/* Status */}
      <div style={{ marginTop: 10, display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
        <Badge tone="gray">Evaluation in focus: {effectiveEvalId || "—"}</Badge>
        {lastCreatedEvalId ? <Badge tone="green">Created: {lastCreatedEvalId}</Badge> : null}
      </div>

      {/* Step 1 buttons */}
      <div style={{ marginTop: 14, display: "flex", gap: 10, flexWrap: "wrap" }}>
        <Button
          onClick={createEvaluation}
          disabled={busy || !canCreate}
          variant="primary"
          title={reasonCreate || "Create evaluation"}
        >
          {busy ? "Creating..." : "Create Evaluation"}
        </Button>

        <Button onClick={() => go("/consultant/evaluations")} disabled={busy} variant="soft">
          Back to Evaluations →
        </Button>

        {!canCreate ? <Badge tone="amber">Locked: {reasonCreate}</Badge> : null}
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
