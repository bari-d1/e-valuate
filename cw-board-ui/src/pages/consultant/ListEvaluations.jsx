import React, { useEffect, useMemo } from "react";

/**
 * List Evaluations page (router-based)
 */
export default function ListEvaluationsPage({
  ui,

  // data
  evaluations,
  evalsLoadedAt,
  evalId,
  selectedTemplate,
  selectedVersion,

  // global state
  busy,

  // actions
  listEvaluations,
  setFocusFromEvaluationRow,

  // router nav
  go, // ✅ required: go("/consultant/...")

  // locks / helpers
  lockReason,
  formatDateMaybe,

  // styles
  tableWrapStyle,
  tdStyle,
  rowHoverStyle,

  // flow UI
  renderFlowBar,
}) {
  const { Card, Badge, Button } = ui || {};

  // Load the list when the page opens
  useEffect(() => {
    if (typeof listEvaluations === "function") listEvaluations();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // guards
  const missing = [];
  if (!ui?.Card) missing.push("ui.Card");
  if (!ui?.Badge) missing.push("ui.Badge");
  if (!ui?.Button) missing.push("ui.Button");
  if (typeof tableWrapStyle !== "function") missing.push("tableWrapStyle (function)");
  if (typeof tdStyle !== "function") missing.push("tdStyle (function)");
  if (typeof rowHoverStyle !== "function") missing.push("rowHoverStyle (function)");
  if (typeof renderFlowBar !== "function") missing.push("renderFlowBar (function)");
  if (typeof lockReason !== "function") missing.push("lockReason (function)");
  if (typeof go !== "function") missing.push("go (function)");

  if (missing.length) {
    return (
      <div style={{ padding: 16, border: "1px solid #FECACA", background: "#FEF2F2", borderRadius: 12 }}>
        <div style={{ fontWeight: 900, color: "#991B1B" }}>ListEvaluationsPage: Missing props</div>
        <div style={{ marginTop: 8, color: "#991B1B", fontFamily: "monospace", fontSize: 12 }}>
          {missing.join(", ")}
        </div>
      </div>
    );
  }

  const count = evaluations?.length || 0;
  const latestId = evaluations?.[0]?.evaluation_id;

  // Precompute lock reasons once per render
  const reasonParticipants = useMemo(() => lockReason("participants"), [lockReason]);
  const reasonQuestionnaire = useMemo(() => lockReason("questionnaire"), [lockReason]);
  const reasonListQuestions = useMemo(() => lockReason("list_questions"), [lockReason]);
  const reasonAiQuestions = useMemo(() => lockReason("ai_questions"), [lockReason]);

    // routes (MUST match AppLegacy.jsx <Routes>)
  const ROUTES = {
    createEval: "/consultant/evaluations/create",
    questionnaire: "/consultant/questionnaire/select",
    invite: "/consultant/participants/invite",
    participants: "/consultant/participants",
    listQuestions: "/consultant/questions",
    editQuestions: "/consultant/questions/edit",
    genAI: "/consultant/questions/ai",
    report: "/consultant/analysis/report",
  };


  const focusAndGo = (ev, path) => {
    // keep your existing focus setter; pass a path if your function supports it
    try {
      setFocusFromEvaluationRow?.(ev);
    } finally {
      if (path) go(path);
    }
  };

  return (
    <Card
      title="Evaluations"
      subtitle="Browse evaluations. Click a row to set the evaluation in focus."
      right={<Badge tone="blue">Consultant</Badge>}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
        <Button onClick={listEvaluations} disabled={busy} variant="primary">
          {busy ? "Loading..." : "Refresh Evaluations"}
        </Button>

        <Button onClick={() => go(ROUTES.createEval)} disabled={busy} variant="secondary">
          Create New →
        </Button>

        <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
          <Badge tone="gray">Count: {count}</Badge>
          {latestId ? <Badge tone="green">Latest: {latestId}</Badge> : null}
          {evalsLoadedAt ? <Badge tone="gray">Loaded: {evalsLoadedAt}</Badge> : null}
        </div>
      </div>

      <div style={{ marginTop: 14 }}>
        <div
          style={{
            marginBottom: 8,
            display: "flex",
            gap: 10,
            flexWrap: "wrap",
            alignItems: "center",
          }}
        >
          <Badge tone="gray">Focus: {evalId || "—"}</Badge>
          <Badge tone="gray">
            Questionnaire: {String(selectedTemplate || "DEFAULT")} v{String(selectedVersion || "1")}
          </Badge>
          <span style={{ fontSize: 13, color: "#64748B" }}>
            Tip: click a row → focus set → questionnaire auto-loads → then Invite / Questions / Generate.
          </span>
        </div>

        <div style={tableWrapStyle()}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
            <thead style={{ background: "#F8FAFC" }}>
              <tr>
                {["Evaluation ID", "Tenant", "Sector", "Year", "Regulators", "Created At"].map((h) => (
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
              {count === 0 ? (
                <tr>
                  <td style={{ padding: 14, color: "#64748B" }} colSpan={6}>
                    {!evalsLoadedAt ? (
                      "Loading evaluations…"
                    ) : (
                      <>
                        No evaluations yet. Click <b>Create New</b> to set one up.
                      </>
                    )}
                  </td>
                </tr>
              ) : (
                evaluations.map((ev) => {
                  const isFocused = String(ev.evaluation_id) === String(evalId);

                  return (
                    <tr
                      key={ev.evaluation_id}
                      style={{
                        borderBottom: "1px solid #F1F5F9",
                        background: isFocused ? "#EEF2FF" : "transparent",
                        ...rowHoverStyle(),
                      }}
                      onClick={() => setFocusFromEvaluationRow?.(ev)}
                      onMouseEnter={(e) => {
                        if (!isFocused) e.currentTarget.style.background = "#F8FAFC";
                      }}
                      onMouseLeave={(e) => {
                        if (!isFocused) e.currentTarget.style.background = "transparent";
                      }}
                      title="Click to set focus"
                    >
                      <td style={tdStyle()}>
                        <div style={{ fontWeight: 900, color: "#0F172A" }}>{ev.evaluation_id}</div>

                        <div style={{ marginTop: 6, display: "flex", gap: 8, flexWrap: "wrap" }}>
                          <Button
                            variant="soft"
                            disabled={busy}
                            title="Focus + Invite Participants"
                            onClick={(e) => {
                              e.stopPropagation();
                              focusAndGo(ev, ROUTES.invite);
                            }}
                          >
                            Invite →
                          </Button>

                          <Button
                            variant="secondary"
                            disabled={busy}
                            title="Focus + View Questions"
                            onClick={(e) => {
                              e.stopPropagation();
                              focusAndGo(ev, ROUTES.listQuestions);
                            }}
                          >
                            View Qs →
                          </Button>

                          <Button
                            variant="secondary"
                            disabled={busy}
                            title="Focus + Add / Edit Questions"
                            onClick={(e) => {
                              e.stopPropagation();
                              focusAndGo(ev, ROUTES.editQuestions);
                            }}
                          >
                            Edit Qs →
                          </Button>

                          <Button
                            variant="secondary"
                            disabled={busy}
                            title="Focus + Generate Report"
                            onClick={(e) => {
                              e.stopPropagation();
                              focusAndGo(ev, ROUTES.report);
                            }}
                          >
                            Report →
                          </Button>
                        </div>
                      </td>

                      <td style={tdStyle()}>{ev.tenant_name || "—"}</td>
                      <td style={tdStyle()}>{ev.sector || "—"}</td>
                      <td style={tdStyle()}>{ev.year ?? "—"}</td>
                      <td style={tdStyle()}>
                        {(ev.regulators || []).length ? (ev.regulators || []).join(", ") : "—"}
                      </td>
                      <td style={tdStyle()}>{formatDateMaybe?.(ev.created_at)}</td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>

        {renderFlowBar({
          left: [
            {
              key: "continue",
              label: "Continue with Focus →",
              onClick: () => go(ROUTES.invite),
              disabled: busy || !!reasonParticipants,
              title: reasonParticipants || "Invite participants",
              variant: "primary",
            },
            {
              key: "questionnaire",
              label: "Questionnaire →",
              onClick: () => go(ROUTES.questionnaire),
              disabled: busy || !!reasonQuestionnaire,
              title: reasonQuestionnaire || "Select questionnaire",
              variant: "secondary",
            },
            {
              key: "questions",
              label: "Questions →",
              onClick: () => go(ROUTES.listQuestions),
              disabled: busy || !!reasonListQuestions,
              title: reasonListQuestions || "View questions",
              variant: "secondary",
            },
            {
              key: "ai",
              label: "Generate (AI) →",
              onClick: () => go(ROUTES.genAI),
              disabled: busy || !!reasonAiQuestions,
              title: reasonAiQuestions || "Generate questions with AI",
              variant: "highlight",
            },
          ],
          right: [
            {
              key: "hint",
              label: "Next: Confirm questionnaire → Invite participants → Prepare questions → Generate report",
              disabled: true,
              title: "",
              variant: "soft",
            },
          ],
          tone: "gray",
        })}
      </div>
    </Card>
  );
}
