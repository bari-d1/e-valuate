import React from "react";

/**
 * Seed Demo Responses page (router version)
 */
export default function SeedDemoResponsesPage({
  ui,

  // state
  busy,
  focus,
  invited,
  setInvited,
  responded,
  setResponded,
  randomSeed,
  setRandomSeed,
  selectedTemplate,
  selectedVersion,

  // actions / helpers
  lockReason,
  seedDemoResponses,
  listParticipants,

  // router nav
  go,

  // optional UI helper
  renderNextActionBar,
}) {
  // ---- UI guards (avoid blank pages) ----
  const requiredUI = ["Card", "Badge", "Button", "Field", "inputStyle"];
  const missingUI = requiredUI.filter((k) => !ui?.[k]);

  if (missingUI.length) {
    return (
      <div style={{ padding: 20 }}>
        <b>SeedDemoResponsesPage:</b> missing UI helpers:
        <div style={{ marginTop: 8, fontFamily: "monospace", fontSize: 12 }}>
          {missingUI.join(", ")}
        </div>
        <div style={{ marginTop: 8, fontFamily: "monospace", fontSize: 12 }}>
          ui keys: {Object.keys(ui || {}).join(", ")}
        </div>
      </div>
    );
  }

  // ---- function guards ----
  const requiredFns = [
    ["lockReason", lockReason],
    ["seedDemoResponses", seedDemoResponses],
    ["go", go],
  ];
  const missingFns = requiredFns
    .filter(([_, fn]) => typeof fn !== "function")
    .map(([name]) => name);

  if (missingFns.length) {
    return (
      <div style={{ padding: 20 }}>
        <b>SeedDemoResponsesPage:</b> missing functions:
        <div style={{ marginTop: 8, fontFamily: "monospace", fontSize: 12 }}>
          {missingFns.join(", ")}
        </div>
      </div>
    );
  }

  const { Card, Badge, Button, Field, inputStyle } = ui;

  const reasonSeed = lockReason("seed"); // needs eval + participants + questions
  const reasonEval = lockReason("evaluation");
  const reasonManual = lockReason("manual_questions");

  // ---- Next/Back bar ----
  const nextBar =
    typeof renderNextActionBar === "function" ? (
      renderNextActionBar({
        label: "Next: Generate Report →",
        nextReason: reasonSeed,
        onNext: () => go("/consultant/report"),
        onRefresh: () => {
          if (typeof listParticipants === "function") listParticipants();
          go("/consultant/participants");
        },
        onBack: () => go("/consultant/evaluations"),
      })
    ) : (
      <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
        <Button
          onClick={() => go("/consultant/report")}
          disabled={busy || !!reasonSeed}
          variant="primary"
          title={reasonSeed || "Go to report generation"}
        >
          Next: Generate Report →
        </Button>

        <Button onClick={() => go("/consultant/evaluations")} disabled={busy} variant="soft">
          Back to Evaluations →
        </Button>
      </div>
    );

  return (
    <Card
      title="Seed Demo Responses"
      subtitle="Creates demo participants + responses so analytics and reports are based on real DB rows."
    >
      <div style={{ marginTop: 6 }}>{focus}</div>

      {/* Inputs */}
      <div style={{ marginTop: 14, display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 12 }}>
        <Field label="Invited">
          <input
            inputMode="numeric"
            value={invited}
            onChange={(e) => setInvited?.(e.target.value)}
            style={inputStyle()}
          />
        </Field>

        <Field label="Responded">
          <input
            inputMode="numeric"
            value={responded}
            onChange={(e) => setResponded?.(e.target.value)}
            style={inputStyle()}
          />
        </Field>

        <Field label="Random Seed">
          <input
            inputMode="numeric"
            value={randomSeed}
            onChange={(e) => setRandomSeed?.(e.target.value)}
            style={inputStyle()}
          />
        </Field>
      </div>

      {/* Context */}
      <div style={{ marginTop: 10, display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
        <Badge tone="gray">
          Target questionnaire: {String(selectedTemplate || "DEFAULT")} v{String(selectedVersion || "1")}
        </Badge>
        <Badge tone="gray">Tip: Seed once, then generate the report.</Badge>
        {reasonSeed ? <Badge tone="amber">{reasonSeed}</Badge> : null}
      </div>

      {/* Primary action row */}
      <div style={{ marginTop: 14, display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
        <Button
          onClick={seedDemoResponses}
          disabled={busy || !!reasonSeed}
          variant="primary"
          title={reasonSeed || "Seed demo participants + responses"}
        >
          {busy ? "Seeding..." : "Seed Demo Responses"}
        </Button>

        <Button
          onClick={() => go("/consultant/participants")}
          disabled={busy || !!reasonEval}
          variant="soft"
          title={reasonEval || "Verify the demo participants were created"}
        >
          View Participants
        </Button>

        <Button
          onClick={() => go("/consultant/questions/manual")}
          disabled={busy || !!reasonManual}
          variant="secondary"
          title={reasonManual || "Back to questions"}
        >
          Back: Questions →
        </Button>
      </div>

      {/* Navigation */}
      <div style={{ marginTop: 12 }}>{nextBar}</div>
    </Card>
  );
}
