import React, { useState } from "react";

export default function SeedDefaultQuestionsPage({
  ui,
  busy,
  focus,
  lockReason,
  seedQuestions,
  listQuestionsTask,
  go,
  renderNextActionBar,
}) {
  // guards
  const missing = [];
  if (!ui?.Card) missing.push("ui.Card");
  if (!ui?.Button) missing.push("ui.Button");
  if (typeof lockReason !== "function") missing.push("lockReason (function)");
  if (typeof seedQuestions !== "function") missing.push("seedQuestions (function)");
  if (typeof go !== "function") missing.push("go (function)");

  if (missing.length) {
    return (
      <div style={{ padding: 16, border: "1px solid #FECACA", background: "#FEF2F2", borderRadius: 12 }}>
        <div style={{ fontWeight: 900, color: "#991B1B" }}>SeedDefaultQuestionsPage: Missing props</div>
        <div style={{ marginTop: 8, color: "#991B1B", fontFamily: "monospace", fontSize: 12 }}>
          {missing.join(", ")}
        </div>
      </div>
    );
  }

  const { Card, Button } = ui;

  const [preset, setPreset] = useState("default");

  const reason = lockReason("questionnaire"); // needs eval + questionnaire
  const reasonNext = lockReason("participants"); // needs eval

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      {focus}

      <Card
        title="Seed Default Questionnaire"
        subtitle="Creates a default set of questions for the selected template/version."
      >
        {reason ? <div style={{ marginBottom: 12, fontWeight: 800 }}>{reason}</div> : null}

        <div style={{ marginBottom: 12, display: "flex", flexDirection: "column", gap: 6, maxWidth: 420 }}>
          <label style={{ fontSize: 12, fontWeight: 800, color: "#334155" }}>Questionnaire preset</label>
          <select
            value={preset}
            onChange={(e) => setPreset(e.target.value)}
            disabled={busy}
            style={{
              padding: "10px 12px",
              borderRadius: 10,
              border: "1px solid #E2E8F0",
              background: "#fff",
              color: "#0F172A",
              colorScheme: "light",
              fontWeight: 600,
            }}
          >
            <option value="default">Default (10) — core board dimensions + 2 open comments</option>
            <option value="expanded">Expanded (20) — default + audit, remuneration, compliance, management</option>
          </select>
          <div style={{ fontSize: 12, color: "#64748B", lineHeight: 1.4 }}>
            Idempotent: questions that already exist for this template/version (same text) are skipped. Run preset{" "}
            <strong>expanded</strong> after <strong>default</strong> to add the extra items without duplicating the core set.
          </div>
        </div>

        <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
          <Button
            variant="primary"
            disabled={busy || !!reason}
            onClick={async () => {
              await seedQuestions(preset);
              if (typeof listQuestionsTask === "function") await listQuestionsTask();
              go("/consultant/questions");
            }}
            title={reason || "Seed default questions"}
          >
            Seed Now
          </Button>

          <Button
            variant="secondary"
            disabled={busy}
            onClick={() => go("/consultant/questions")}
            title="View questions"
          >
            View Questions
          </Button>
        </div>

        {typeof renderNextActionBar === "function"
          ? renderNextActionBar({
              nextLabel: "Next: Invite Participants →",
              nextReason: reasonNext,
              onNext: () => go("/consultant/participants/invite"),
            })
          : null}
      </Card>
    </div>
  );
}
