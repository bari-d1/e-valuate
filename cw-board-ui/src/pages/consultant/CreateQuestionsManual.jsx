import React from "react";

export default function CreateQuestionsManualPage(props) {
  const {
    ui,
    busy,
    focus,

    // data
    questions,
    qsLoadedAt,

    // questionnaire
    selectedTemplate,
    selectedVersion,

    // locks + actions
    lockReason,
    listQuestionsManual,
    createQuestionManual,
    toggleQuestionActive,
    go,

    // form state
    qCreateStatus,
    qDimension,
    setQDimension,
    qAnswerType,
    setQAnswerType,
    qWeight,
    setQWeight,
    qActive,
    setQActive,
    qText,
    setQText,

    // constants
    ANSWER_TYPES,

    // UI helpers + styles (all FUNCTIONS in App.jsx)
    renderFlowBar,
    miniPanelStyle,
    miniTitleStyle,
    inputStyle,
    textareaStyle,
    tdStyle,
  } = props;

  // UI components come from ui
  const Card = ui?.Card;
  const Badge = ui?.Badge;
  const Field = ui?.Field;
  const Button = ui?.Button;

  // ✅ Centralized routes (prevents typos/mismatches)
  const ROUTES = {
    listQuestions: "/consultant/questions",
    genAI: "/consultant/questions/ai",
    seedDemo: "/consultant/analysis/seed-demo",
    evaluations: "/consultant/evaluations",
  };

  // ✅ Hard guard: show what is missing instead of blank screen
  const missing = [];
  if (!ui) missing.push("ui");
  if (!Card) missing.push("ui.Card");
  if (!Badge) missing.push("ui.Badge");
  if (!Field) missing.push("ui.Field");
  if (!Button) missing.push("ui.Button");
  if (typeof go !== "function") missing.push("go (function)");
  if (typeof renderFlowBar !== "function") missing.push("renderFlowBar (function)");
  if (typeof miniPanelStyle !== "function") missing.push("miniPanelStyle (function)");
  if (typeof miniTitleStyle !== "function") missing.push("miniTitleStyle (function)");
  if (typeof inputStyle !== "function") missing.push("inputStyle (function)");
  if (typeof textareaStyle !== "function") missing.push("textareaStyle (function)");
  if (typeof tdStyle !== "function") missing.push("tdStyle (function)");
  if (!Array.isArray(ANSWER_TYPES)) missing.push("ANSWER_TYPES (array)");

  if (missing.length) {
    return (
      <div
        style={{
          padding: 16,
          border: "1px solid #FECACA",
          background: "#FEF2F2",
          borderRadius: 12,
        }}
      >
        <div style={{ fontWeight: 900, color: "#991B1B" }}>
          CreateQuestionsManualPage: Missing props
        </div>
        <div style={{ marginTop: 8, color: "#991B1B" }}>{missing.join(", ")}</div>
      </div>
    );
  }

  const safeQuestions = Array.isArray(questions) ? questions : [];
  const qCount = safeQuestions.length;

  // ✅ Lock reasons (use correct key for "Load Questions")
  const reasonLoad = lockReason?.("list_questions") || "";
  const reasonManual = lockReason?.("manual_questions") || "";
  const reasonAI = lockReason?.("ai_questions") || "";
  const reasonSeed = lockReason?.("seed") || "";

  return (
    <Card
      title="Add / Edit Questions"
      subtitle="Creates questions in the evaluation’s selected questionnaire. Toggle Active without deleting."
      right={<Badge tone="blue">Consultant</Badge>}
    >
      {focus}

      {renderFlowBar({
        left: [
          {
            key: "load_questions",
            label: busy ? "Loading..." : "Load Questions",
            onClick: listQuestionsManual,
            disabled: busy || !!reasonLoad,
            variant: "primary",
            title: reasonLoad || "Load questions for the focused evaluation/questionnaire",
          },
          {
            key: "view_table",
            label: "View as Table →",
            onClick: () => go(ROUTES.listQuestions),
            disabled: busy,
            variant: "secondary",
          },
        ],
        meta: (
          <>
            <Badge tone="gray">
              Target: {String(selectedTemplate || "DEFAULT")} v{String(selectedVersion || "1")}
            </Badge>
            <Badge tone="gray">Count: {qCount}</Badge>
            {qsLoadedAt ? <Badge tone="gray">Loaded: {qsLoadedAt}</Badge> : null}
            {reasonLoad ? <Badge tone="amber">{reasonLoad}</Badge> : null}
          </>
        ),
        right: [
          {
            key: "gen_ai",
            label: "Generate (AI) →",
            onClick: () => go(ROUTES.genAI),
            disabled: busy || !!reasonAI,
            variant: "highlight",
            title: reasonAI || "Use AI helper to draft questions",
          },
          {
            key: "next_seed",
            label: "Next: Seed Demo Responses →",
            onClick: () => go(ROUTES.seedDemo),
            disabled: busy || !!reasonSeed,
            variant: "secondary",
            title: reasonSeed || "Seed demo participants + responses (for report testing)",
          },
          {
            key: "back",
            label: "Back →",
            onClick: () => go(ROUTES.evaluations),
            disabled: busy,
            variant: "soft",
          },
        ],
        marginTop: 10,
      })}

      <div style={{ marginTop: 16, display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
        {/* Left */}
        <div style={miniPanelStyle()}>
          <div style={miniTitleStyle()}>New Question</div>

          {qCreateStatus ? (
            <div style={{ marginBottom: 10 }}>
              <Badge tone={qCreateStatus.created ? "green" : "amber"}>
                {qCreateStatus.created ? "Created" : "Already exists"} • {qCreateStatus.message}
              </Badge>
            </div>
          ) : null}

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
            <Field label="Dimension">
              <input value={qDimension} onChange={(e) => setQDimension(e.target.value)} style={inputStyle()} />
            </Field>

            <Field label="Answer Type">
              <select value={qAnswerType} onChange={(e) => setQAnswerType(e.target.value)} style={inputStyle()}>
                {ANSWER_TYPES.map((x) => (
                  <option key={x.key} value={x.key}>
                    {x.label}
                  </option>
                ))}
              </select>
            </Field>

            <Field label="Weight">
              <input
                inputMode="numeric"
                value={qWeight}
                onChange={(e) => setQWeight(e.target.value)}
                style={inputStyle()}
              />
            </Field>

            <Field label="Active">
              <select value={qActive ? "1" : "0"} onChange={(e) => setQActive(e.target.value === "1")} style={inputStyle()}>
                <option value="1">Active</option>
                <option value="0">Inactive</option>
              </select>
            </Field>
          </div>

          <div style={{ marginTop: 12 }}>
            <Field label="Question Text">
              <textarea
                value={qText}
                onChange={(e) => setQText(e.target.value)}
                style={textareaStyle(140)}
                spellCheck={false}
              />
            </Field>
          </div>

          <div style={{ marginTop: 12, display: "flex", gap: 10, flexWrap: "wrap" }}>
            <Button
              onClick={createQuestionManual}
              disabled={busy || !!reasonManual}
              variant="primary"
              title={reasonManual || "Create question"}
            >
              {busy ? "Creating..." : "Create Question"}
            </Button>

            <Button
              variant="secondary"
              disabled={busy}
              onClick={() => {
                setQDimension("Risk Oversight");
                setQAnswerType("rating");
                setQWeight("1");
                setQActive(true);
                setQText("The board actively oversees emerging risks, including technology and cyber risks.");
              }}
              title="Quick fill example"
            >
              Use Sample →
            </Button>
          </div>
        </div>

        {/* Right */}
        <div style={miniPanelStyle()}>
          <div style={miniTitleStyle()}>Questions Loaded</div>

          {qCount === 0 ? (
            <div style={{ fontSize: 13, color: "#64748B" }}>
              {reasonLoad ? (
                <>
                  <b>Locked:</b> {reasonLoad}
                </>
              ) : (
                <>
                  Click <b>Load Questions</b> to view questions for this questionnaire.
                </>
              )}
            </div>
          ) : (
            <div style={{ maxHeight: 380, overflow: "auto", border: "1px solid #E5E7EB", borderRadius: 12 }}>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
                <thead style={{ background: "#F8FAFC" }}>
                  <tr>
                    {["Dimension", "Type", "Weight", "Status", "Text", "Action"].map((h) => (
                      <th
                        key={h}
                        style={{
                          textAlign: "left",
                          padding: "10px 12px",
                          borderBottom: "1px solid #E5E7EB",
                          color: "#0F172A",
                          fontWeight: 800,
                          whiteSpace: "nowrap",
                        }}
                      >
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>

                <tbody>
                  {safeQuestions.map((q) => {
                    const isActive = Boolean(q.active);
                    return (
                      <tr key={q.question_id || q.id} style={{ borderBottom: "1px solid #F1F5F9" }}>
                        <td style={tdStyle()}>{q.dimension || "—"}</td>
                        <td style={tdStyle()}>{q.answer_type || "—"}</td>
                        <td style={tdStyle()}>{q.weight ?? "—"}</td>
                        <td style={tdStyle()}>
                          <Badge tone={isActive ? "green" : "gray"}>{isActive ? "Active" : "Inactive"}</Badge>
                        </td>
                        <td style={tdStyle()}>{q.text || "—"}</td>
                        <td style={tdStyle()}>
                          <Button
                            variant={isActive ? "soft" : "primary"}
                            disabled={busy}
                            title={isActive ? "Deactivate this question" : "Activate this question"}
                            onClick={() => toggleQuestionActive(q)}
                          >
                            {isActive ? "Deactivate" : "Activate"}
                          </Button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </Card>
  );
}
