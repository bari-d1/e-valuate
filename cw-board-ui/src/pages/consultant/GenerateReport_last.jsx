import React from "react";

/**
 * Generate Report page (extracted from App.jsx)
 */
export default function GenerateReportPage({
  ui,

  // state
  busy,
  focus,
  result,
  latestSummary,
  selectedTemplate,
  selectedVersion,

  // actions / helpers
  lockReason,
  setTask,
  generateAndLoadLatestReport,

  // optional download hook (may be undefined)
  downloadReportDocx,

  // optional UI helper (may be undefined)
  renderNextActionBar,
}) {
  // ---------- UI guards ----------
  const requiredComponents = ["Card", "Badge", "Button"];
  const missingComponents = requiredComponents.filter((k) => !ui?.[k]);

  const requiredStyleFns = ["miniPanelStyle", "miniTitleStyle"];
  const missingStyleFns = requiredStyleFns.filter((k) => typeof ui?.[k] !== "function");

  if (missingComponents.length || missingStyleFns.length) {
    return (
      <div style={{ padding: 20 }}>
        <b>GenerateReportPage:</b> missing UI helpers:
        <div style={{ marginTop: 8, fontFamily: "monospace", fontSize: 12 }}>
          {[
            ...missingComponents.map((x) => `${x} (component)`),
            ...missingStyleFns.map((x) => `${x} (function)`),
          ].join(", ")}
        </div>
        <div style={{ marginTop: 8, fontFamily: "monospace", fontSize: 12 }}>
          ui keys: {Object.keys(ui || {}).join(", ")}
        </div>
      </div>
    );
  }

  const { Card, Badge, Button, miniPanelStyle, miniTitleStyle } = ui;

  // ---------- function guards ----------
  const requiredFns = [
    ["lockReason", lockReason],
    ["setTask", setTask],
    ["generateAndLoadLatestReport", generateAndLoadLatestReport],
  ];
  const missingFns = requiredFns
    .filter(([_, fn]) => typeof fn !== "function")
    .map(([name]) => name);

  if (missingFns.length) {
    return (
      <div style={{ padding: 20 }}>
        <b>GenerateReportPage:</b> missing functions:
        <div style={{ marginTop: 8, fontFamily: "monospace", fontSize: 12 }}>
          {missingFns.join(", ")}
        </div>
      </div>
    );
  }

  const reasonReport = lockReason("report"); // requires eval + questions
  const reasonEval = lockReason("evaluation"); // requires eval
  const hasLatest = !!latestSummary?.exec;

  const reportId = result?.data?.report_id;

  // ✅ Download handler: prefer prop, fallback to window
  const downloadFn =
    typeof downloadReportDocx === "function"
      ? downloadReportDocx
      : typeof window !== "undefined" && typeof window.downloadReportDocx === "function"
      ? window.downloadReportDocx
      : null;

  const canDownload = !!reportId && !!downloadFn;

  const doDownload = () => {
    if (!downloadFn || !reportId) return;
    downloadFn(reportId);
  };

  return (
    <Card
      title="Generate Report"
      subtitle="One click: generate a new report, then fetch the latest report for the evaluation."
      right={<Badge tone="blue">Consultant</Badge>}
    >
      {focus}

      {/* ✅ Clean action row */}
      <div
        style={{
          marginTop: 14,
          display: "flex",
          gap: 10,
          flexWrap: "wrap",
          alignItems: "center",
        }}
      >
        <Button
          onClick={generateAndLoadLatestReport}
          disabled={busy || !!reasonReport}
          title={reasonReport || "Generate a fresh report and load the latest"}
          variant="primary"
        >
          {busy ? "Working..." : "Generate + Load Latest"}
        </Button>

        {canDownload ? (
          <Button onClick={doDownload} disabled={busy} variant="soft" title="Download the latest report as DOCX">
            Download DOCX
          </Button>
        ) : null}

        {reasonReport ? <Badge tone="amber">{reasonReport}</Badge> : null}
      </div>

      {/* ✅ Next/Back bar (use if provided; otherwise show simple buttons) */}
      <div style={{ marginTop: 12 }}>
        {typeof renderNextActionBar === "function" ? (
          renderNextActionBar({
            onRefresh: () => generateAndLoadLatestReport(),
            refreshLabel: hasLatest ? "Refresh Latest" : "Generate + Load Latest",
            refreshDisabled: busy || !!reasonReport,
            refreshTitle: reasonReport || "Refresh / generate latest report",

            backTo: "seed_demo_responses",
            backLabel: "Back: Seed Demo Responses →",
            backDisabled: busy || !!lockReason("seed"),
            backTitle: lockReason("seed") || "Back to seeding demo data",

            onNext: () => setTask("list_evaluations"),
            nextLabel: "Done: Back to Evaluations →",
            nextDisabled: busy,
            nextTitle: "Return to evaluations",

            extra: (
              <>
                <Button
                  onClick={() => setTask("list_participants")}
                  disabled={busy || !!reasonEval}
                  title={reasonEval || "View participants"}
                  variant="secondary"
                >
                  View Participants
                </Button>

                <Button
                  onClick={() => setTask("list_questions")}
                  disabled={busy || !!lockReason("list_questions")}
                  title={lockReason("list_questions") || "View questions"}
                  variant="secondary"
                >
                  View Questions
                </Button>
              </>
            ),
          })
        ) : (
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
            <Button onClick={() => ("seed_demo_responses")} disabled={busy} variant="soft">
              Back: Seed Demo →
            </Button>
            <Button onClick={() => setTask("list_evaluations")} disabled={busy} variant="secondary">
              Done: Evaluations →
            </Button>
            <Button onClick={() => setTask("list_participants")} disabled={busy || !!reasonEval} variant="soft">
              View Participants
            </Button>
            <Button onClick={() => setTask("list_questions")} disabled={busy || !!lockReason("list_questions")} variant="soft">
              View Questions
            </Button>
          </div>
        )}
      </div>

      {/* ✅ Report body */}
      {latestSummary?.exec ? (
        <div style={{ marginTop: 16 }}>
          <div
            style={{
              padding: 14,
              borderRadius: 14,
              border: "1px solid #E5E7EB",
              background: "#F8FAFC",
            }}
          >
            <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
              <Badge tone="green">Latest Report</Badge>
              <Badge tone="gray">Report ID: {reportId}</Badge>
              <Badge tone="gray">Created: {result?.data?.created_at}</Badge>
              <Badge tone="gray">
                Questionnaire: {String(selectedTemplate || "DEFAULT")} v{String(selectedVersion || "1")}
              </Badge>
            </div>

            <h3 style={{ marginTop: 12, marginBottom: 8, color: "#0F172A" }}>Executive Summary</h3>
            <div style={{ color: "#0F172A" }}>{latestSummary.exec.overall_message}</div>

            <div style={{ marginTop: 14, display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
              <div style={miniPanelStyle()}>
                <div style={miniTitleStyle()}>Key Strengths</div>
                <ul style={{ margin: 0, paddingLeft: 18 }}>
                  {(latestSummary.exec.key_strengths || []).map((x, i) => (
                    <li key={i} style={{ marginBottom: 6 }}>
                      {x}
                    </li>
                  ))}
                </ul>
              </div>

              <div style={miniPanelStyle()}>
                <div style={miniTitleStyle()}>Key Weaknesses</div>
                <ul style={{ margin: 0, paddingLeft: 18 }}>
                  {(latestSummary.exec.key_weaknesses || []).map((x, i) => (
                    <li key={i} style={{ marginBottom: 6 }}>
                      {x}
                    </li>
                  ))}
                </ul>
              </div>
            </div>

            <div style={{ marginTop: 14 }}>
              <div style={miniTitleStyle()}>Outlook</div>
              <div style={{ color: "#0F172A" }}>{latestSummary.exec.outlook}</div>
            </div>

            <div style={{ marginTop: 14 }}>
              <div style={miniTitleStyle()}>Recommendations</div>
              <ol style={{ margin: 0, paddingLeft: 18 }}>
                {(latestSummary.recs || []).map((r, i) => (
                  <li key={i} style={{ marginBottom: 10 }}>
                    <div style={{ fontWeight: 800, color: "#0F172A" }}>
                      {r.theme}{" "}
                      <span style={{ fontWeight: 700, color: "#64748B" }}>• {r.priority}</span>
                    </div>
                    <div style={{ color: "#0F172A" }}>{r.action}</div>
                    <div style={{ fontSize: 12, color: "#64748B", marginTop: 4 }}>
                      Owner: {r.owner_suggestion} • Timeline: {r.timeline} • Metric: {r.success_metric}
                    </div>
                  </li>
                ))}
              </ol>
            </div>
          </div>
        </div>
      ) : (
        <div style={{ marginTop: 12, color: "#64748B", fontSize: 13 }}>
          Click <b>Generate + Load Latest</b> to produce and display the report.
        </div>
      )}
    </Card>
  );
}
