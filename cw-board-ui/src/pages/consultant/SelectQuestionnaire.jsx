import React, { useMemo } from "react";

/**
 * Select Questionnaire page (router version)
 */
export default function SelectQuestionnairePage({
  ui,

  // state
  busy,
  focus,
  evalId,
  selectedTemplate,
  selectedVersion,
  questionnaireSavedForEvalId,
  questionnaireSavedAt,

  // setters
  setSelectedTemplate,
  setSelectedVersion,
  setQuestionnaireSavedForEvalId,
  setQuestionnaireSavedAt,

  setEvaluationQuestionnaire,

  // helpers
  lockReason,

  // ui helpers/styles
  inputStyle,
}) {
  const { Card, Badge, Field, Button } = ui;

  // Locks
  const reasonEval = useMemo(() => lockReason("evaluation"), [lockReason]); // needs eval
  const reasonQuestionnaire = useMemo(() => lockReason("questionnaire"), [lockReason]); // needs eval + template/version

  const disabledEvalOnly = busy || !!reasonEval;

  const markQuestionnaireDirty = () => {
    setQuestionnaireSavedForEvalId("");
    setQuestionnaireSavedAt("");
  };

  // Saved cue (persisted questionnaire/instrument)
  const savedForThisEval = useMemo(() => {
    return String(questionnaireSavedForEvalId || "").trim() === String(evalId || "").trim();
  }, [questionnaireSavedForEvalId, evalId]);

  return (
    <Card
      title="Select Questionnaire"
      subtitle="Choose template + version for this evaluation, then save so the backend and all question tools use the same instrument."
    >
      {focus}

      <div style={{ marginTop: 12, color: "#64748B", fontSize: 13 }}>
        When you change the evaluation in focus, the template and version load from the API. If you edit them here,
        click <b>Save questionnaire</b> before other steps (or your changes exist only in this browser until saved).
      </div>

      {/* Current selection */}
      <div style={{ marginTop: 10, display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
        <Badge tone="gray">
          Selected: {String(selectedTemplate || "—")} v{String(selectedVersion || "—")}
        </Badge>

        {savedForThisEval ? (
          <Badge tone="green">
            ✓ Questionnaire saved for this evaluation
            {questionnaireSavedAt ? ` • ${questionnaireSavedAt}` : ""}
          </Badge>
        ) : (
          <Badge tone="amber">Not saved yet — click Save questionnaire</Badge>
        )}

        {reasonEval ? <Badge tone="amber">{reasonEval}</Badge> : null}
        {!reasonEval && reasonQuestionnaire ? <Badge tone="amber">{reasonQuestionnaire}</Badge> : null}
      </div>

      {/* Inputs */}
      <div style={{ marginTop: 14, display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
        <Field label="Template">
          <input
            value={selectedTemplate || ""}
            onChange={(e) => {
              setSelectedTemplate(e.target.value);
              markQuestionnaireDirty();
            }}
            style={inputStyle()}
            disabled={disabledEvalOnly}
            placeholder="e.g., DEFAULT"
          />
        </Field>

        <Field label="Version">
          <input
            value={selectedVersion || ""}
            onChange={(e) => {
              setSelectedVersion(e.target.value);
              markQuestionnaireDirty();
            }}
            style={inputStyle()}
            disabled={disabledEvalOnly}
            placeholder="e.g., 1"
          />
        </Field>
      </div>

      <div style={{ marginTop: 14, display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
        <Button
          variant="primary"
          disabled={busy || !!reasonEval || !!reasonQuestionnaire}
          onClick={setEvaluationQuestionnaire}
          title={reasonEval || reasonQuestionnaire || "PATCH instrument on this evaluation"}
        >
          {busy ? "Saving…" : "Save questionnaire"}
        </Button>
        {!reasonEval && !reasonQuestionnaire ? (
          <span style={{ fontSize: 12, color: "#64748B" }}>Persists to the API (same as Step 2 on Create Evaluation).</span>
        ) : null}
      </div>

      {/* Flow / navigation */}
    </Card>
  );
}
