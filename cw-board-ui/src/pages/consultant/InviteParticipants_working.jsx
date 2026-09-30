import React from "react";

/**
 * Invite Participants page (router-based)
 */
export default function InviteParticipantsPage({
  ui,
  busy,
  focus,
  inviteText,
  setInviteText,
  inviteParticipants,
  listParticipants,
  lockReason,

  go, // ✅ router navigation function e.g. go("/consultant/participants")

  // optional shared UI helpers
  renderNextActionBar,
  textareaStyle,
}) {
  const { Card, Badge, Field, Button } = ui;

  // guards (prevents blank screen)
  const missing = [];
  if (!ui?.Card) missing.push("ui.Card");
  if (!ui?.Badge) missing.push("ui.Badge");
  if (!ui?.Field) missing.push("ui.Field");
  if (!ui?.Button) missing.push("ui.Button");
  if (typeof textareaStyle !== "function") missing.push("textareaStyle (function)");
  if (typeof lockReason !== "function") missing.push("lockReason (function)");
  if (typeof go !== "function") missing.push("go (function)");

  if (missing.length) {
    return (
      <div style={{ padding: 16, border: "1px solid #FECACA", background: "#FEF2F2", borderRadius: 12 }}>
        <div style={{ fontWeight: 900, color: "#991B1B" }}>InviteParticipantsPage: Missing props</div>
        <div style={{ marginTop: 8, color: "#991B1B", fontFamily: "monospace", fontSize: 12 }}>
          {missing.join(", ")}
        </div>
      </div>
    );
  }

  const reasonEval = lockReason("evaluation");
  const disabled = busy || !!reasonEval;

  const goParticipants = () => go("/consultant/participants"); // ✅ adjust if your route differs

  return (
    <Card
      title="Invite Participants"
      subtitle="Add board members/directors to an evaluation (idempotent by email)."
      right={<Badge tone="blue">Consultant</Badge>}
    >
      <div style={{ marginTop: 6 }}>{focus}</div>

      <div style={{ marginTop: 14 }}>
        <Field
          label="Participants (one per line)"
          hint='Formats: "email" OR "email,Full Name" OR "email,Full Name,Role"'
        >
          <textarea
            value={inviteText}
            onChange={(e) => setInviteText(e.target.value)}
            style={textareaStyle(160)}
            spellCheck={false}
          />
        </Field>
      </div>

      <div
        style={{
          marginTop: 14,
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 12,
          flexWrap: "wrap",
        }}
      >
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
          <Button
            onClick={inviteParticipants}
            disabled={disabled}
            title={reasonEval || "Invite participants"}
            variant="primary"
          >
            {busy ? "Inviting..." : "Invite Participants"}
          </Button>

          <Button
            onClick={() => {
              if (disabled) return;
              // keep your existing pattern: fetch then navigate
              listParticipants?.();
              goParticipants();
            }}
            disabled={disabled}
            title={reasonEval || "View participants"}
            variant="soft"
          >
            View Participants
          </Button>

          {reasonEval ? <Badge tone="amber">{reasonEval}</Badge> : null}
        </div>

        {typeof renderNextActionBar === "function"
          ? renderNextActionBar({
              onRefresh: () => {
                if (disabled) return;
                listParticipants?.();
                goParticipants();
              },

              // router-based destinations
              onBack: () => go("/consultant/evaluations"),
              backLabel: "Back to Evaluations →",
              backDisabled: busy,
            })
          : null}
      </div>
    </Card>
  );
}
