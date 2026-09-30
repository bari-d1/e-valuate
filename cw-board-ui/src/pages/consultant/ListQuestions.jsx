import React, { useEffect } from "react";

/**
 * View Questions page (router-based)
 */
export default function ListQuestionsPage({
  // state / data
  busy,
  focus,
  questions,

  // actions
  listQuestionsTask,

  // guards
  lockReason,

  // helpers
  formatDateMaybe,
  renderFlowBar,

  // router nav
  go, // ✅ required: go("/consultant/...")

  // ui bundle (components + styles)
  ui,
}) {
  // Load questions as soon as the evaluation's questionnaire is known
  const autoLoadBlocked = typeof lockReason === "function" ? lockReason("list_questions") : "missing";
  useEffect(() => {
    if (!autoLoadBlocked && typeof listQuestionsTask === "function") listQuestionsTask();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoLoadBlocked]);

  // guards
  const missing = [];
  if (!ui?.Card) missing.push("ui.Card");
  if (!ui?.Badge) missing.push("ui.Badge");
  if (typeof ui?.tdStyle !== "function") missing.push("ui.tdStyle (function)");
  if (typeof ui?.tableWrapStyle !== "function") missing.push("ui.tableWrapStyle (function)");
  if (typeof renderFlowBar !== "function") missing.push("renderFlowBar (function)");
  if (typeof lockReason !== "function") missing.push("lockReason (function)");
  if (typeof listQuestionsTask !== "function") missing.push("listQuestionsTask (function)");
  if (typeof formatDateMaybe !== "function") missing.push("formatDateMaybe (function)");
  if (typeof go !== "function") missing.push("go (function)");

  if (missing.length) {
    return (
      <div style={{ padding: 16, border: "1px solid #FECACA", background: "#FEF2F2", borderRadius: 12 }}>
        <div style={{ fontWeight: 900, color: "#991B1B" }}>ListQuestionsPage: Missing props</div>
        <div style={{ marginTop: 8, color: "#991B1B", fontFamily: "monospace", fontSize: 12 }}>
          {missing.join(", ")}
        </div>
      </div>
    );
  }

  const { Card, Badge, tdStyle, tableWrapStyle } = ui;

  const qCount = Array.isArray(questions) ? questions.length : 0;

  const reasonLoad = lockReason("list_questions"); // requires eval + questionnaire



   // routes (must match AppLegacy.jsx <Routes>)
  const ROUTES = {
    editManual: "/consultant/questions/edit",
    genAI: "/consultant/questions/ai",
    evaluations: "/consultant/evaluations",
  };


  return (
    <Card
      title="View Questions"
      subtitle="Lists questions for the questionnaire selected on this evaluation (template/version)."
    >
      {focus}

      {renderFlowBar({
        left: [
          {
            key: "load_questions",
            label: busy ? "Loading..." : "Load Questions",
            onClick: listQuestionsTask,
            disabled: busy || !!reasonLoad,
            variant: "primary",
            title: reasonLoad || "Load questions for the focused evaluation",
          },
        ],
        meta: (
          <>
            <Badge tone="gray">Count: {qCount}</Badge>
            {reasonLoad ? <Badge tone="amber">{reasonLoad}</Badge> : null}
          </>
        ),
        marginTop: 14,
      })}

      <div style={tableWrapStyle()}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
          <thead style={{ background: "#F8FAFC" }}>
            <tr>
              {["Dimension", "Type", "Weight", "Active", "Text", "Created At"].map((h) => (
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
            {qCount === 0 ? (
              <tr>
                <td style={{ padding: 14, color: "#64748B" }} colSpan={6}>
                  No questions loaded yet.{" "}
                  {reasonLoad ? (
                    <>
                      <span style={{ fontWeight: 800 }}>Locked:</span> {reasonLoad}
                    </>
                  ) : (
                    <>
                      Click <b>Load Questions</b>.
                    </>
                  )}
                </td>
              </tr>
            ) : (
              (questions || []).map((q) => (
                <tr key={q.question_id || q.id} style={{ borderBottom: "1px solid #F1F5F9" }}>
                  <td style={tdStyle()}>{q.dimension || "—"}</td>
                  <td style={tdStyle()}>{q.answer_type || "—"}</td>
                  <td style={tdStyle()}>{q.weight ?? "—"}</td>
                  <td style={tdStyle()}>
                    <Badge tone={q.active ? "green" : "gray"}>{q.active ? "Active" : "Inactive"}</Badge>
                  </td>
                  <td style={tdStyle()}>{q.text || "—"}</td>
                  <td style={tdStyle()}>{formatDateMaybe(q.created_at)}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </Card>
  );
}
