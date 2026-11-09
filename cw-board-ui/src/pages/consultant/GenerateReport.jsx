import React from "react";

/**
 * Generate Report page (router-based)
 * - No setTask
 * - Uses go("/route") navigation helper passed from AppLegacy
 * - The report is built from the latest completed analysis: approved findings and conclusions only,
 *   each finding with the evidence it rests on. Earlier reports (executive summary + recommendations)
 *   still display in their own layout.
 */

const when = (iso) =>
  iso ? new Date(iso).toLocaleString("en-GB", { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" }) : "—";
const cap = (s) => (s ? s[0].toUpperCase() + s.slice(1) : s);

function ReportFinding({ f, ui }) {
  const { Badge } = ui;
  return (
    <li style={{ listStyle: "none", padding: 12, borderRadius: 12, border: "1px solid #E5E7EB", background: "#FFFFFF" }}>
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center" }}>
        <Badge tone={f.kind === "strength" ? "green" : f.kind === "concern" ? "red" : f.kind === "practice_gap" ? "amber" : "gray"}>{f.kind_label}</Badge>
        <Badge tone={f.support === "conflicting" ? "amber" : "gray"}>{f.support_label}</Badge>
        {f.theme_label ? <span style={{ fontSize: 12, color: "#64748B" }}>{f.theme_label}</span> : null}
        {f.draft_signal ? <Badge tone="amber">Draft signal, thresholds not approved</Badge> : null}
      </div>
      <div style={{ marginTop: 8, color: "#0F172A" }}>{f.statement}</div>
      {f.clauses.length ? (
        <div style={{ marginTop: 6, fontSize: 12, color: "#64748B" }}>
          {f.clauses.map((c) => `${c.label}${c.heading ? `: ${c.heading}` : ""}`).join(" · ")}
        </div>
      ) : null}
      <details style={{ marginTop: 6, fontSize: 13 }}>
        <summary style={{ cursor: "pointer", color: "#1D4ED8" }}>Evidence ({f.evidence.length})</summary>
        <ul style={{ margin: "6px 0 0", paddingLeft: 18, display: "grid", gap: 4 }}>
          {f.evidence.map((e) => (
            <li key={e.evidence_id}>
              “{e.question}” <span style={{ color: "#64748B" }}>· {e.respondent_category} {e.respondent} · evidence {e.evidence_id.slice(0, 8)}</span>
            </li>
          ))}
        </ul>
      </details>
    </li>
  );
}

function FindingsReport({ report, reportId, createdAt, ui }) {
  const { Badge, miniTitleStyle } = ui;
  const trace = report.traceability || {};
  const settings = trace.analysis_settings || {};
  const overall = report.overall || {};
  return (
    <div style={{ marginTop: 16, padding: 14, borderRadius: 14, border: "1px solid #E5E7EB", background: "#F8FAFC", display: "grid", gap: 14 }}>
      <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
        <Badge tone="green">Latest Report</Badge>
        <Badge tone="gray">Report ID: {reportId}</Badge>
        <Badge tone="gray">Created: {createdAt}</Badge>
        <Badge tone="gray">Analysis completed {when(trace.run_completed_at)}{trace.run_completed_by ? ` by ${trace.run_completed_by}` : ""}</Badge>
      </div>
      <div style={{ fontSize: 13, color: "#64748B" }}>
        Only findings and conclusions approved in the analysis, each with the answers it rests on. Respondents are never named; individual directors appear by role.
        {settings.thresholds_status !== "approved" ? " Findings marked “draft signal” were drafted from scoring thresholds the client hasn't approved." : ""}
      </div>

      <div>
        <h3 style={{ margin: "0 0 6px", color: "#0F172A" }}>Overall conclusion</h3>
        <div style={{ color: "#0F172A", whiteSpace: "pre-wrap" }}>{overall.conclusion?.text || "No overall conclusion was approved."}</div>
        {overall.findings?.length ? (
          <ul style={{ margin: "10px 0 0", padding: 0, display: "grid", gap: 8 }}>
            {overall.findings.map((f) => <ReportFinding key={f.finding_id} f={f} ui={ui} />)}
          </ul>
        ) : null}
      </div>

      {(report.subjects || []).map((s) => (
        <div key={s.subject_id}>
          <h3 style={{ margin: "0 0 6px", color: "#0F172A" }}>{cap(s.name)}</h3>
          {s.conclusion?.text ? <div style={{ color: "#0F172A", marginBottom: 8, whiteSpace: "pre-wrap" }}>{s.conclusion.text}</div> : null}
          {s.findings.length ? (
            <ul style={{ margin: 0, padding: 0, display: "grid", gap: 8 }}>
              {s.findings.map((f) => <ReportFinding key={f.finding_id} f={f} ui={ui} />)}
            </ul>
          ) : s.conclusion?.text ? null : (
            <div style={{ fontSize: 13, color: "#64748B" }}>{s.conclusion?.no_findings ? "Nothing to report." : "No approved findings."}</div>
          )}
        </div>
      ))}

      <details style={{ fontSize: 13 }}>
        <summary style={{ cursor: "pointer", ...miniTitleStyle() }}>Traceability</summary>
        <div style={{ display: "grid", gap: 4, marginTop: 6, color: "#334155" }}>
          <div>Analysis run: {trace.run_id}</div>
          <div>Findings used: {(trace.finding_ids || []).length} · conclusions used: {(trace.conclusion_ids || []).length}</div>
          <div>
            Minimum people per result {settings.min_raters} · {settings.include_unsubmitted ? "includes unsubmitted forms" : "submitted forms only"} · thresholds{" "}
            {Object.entries(settings.thresholds || {}).map(([k, v]) => `${k.replace(/_/g, " ")} ${v}`).join(", ")} ({settings.thresholds_status || "unapproved"})
          </div>
          <div>Generated {when(trace.generated_at)}</div>
        </div>
      </details>
    </div>
  );
}
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
  go,
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
    ["go", go],
    ["generateAndLoadLatestReport", generateAndLoadLatestReport],
  ];
  const missingFns = requiredFns
    .filter(([, fn]) => typeof fn !== "function")
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
  const reasonSeed = lockReason("seed"); // participants + questions
  const reasonListQs = lockReason("list_questions");
  const hasLatest = !!latestSummary?.exec || !!latestSummary?.report;

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
      subtitle="Builds the report from the latest completed analysis: approved findings and conclusions only, each traced to its evidence."
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
          <Button
            onClick={doDownload}
            disabled={busy}
            variant="soft"
            title="Download the latest report as DOCX"
          >
            Download DOCX
          </Button>
        ) : null}

        {reasonReport ? <Badge tone="amber">{reasonReport}</Badge> : null}
      </div>

      {/* ✅ Next/Back bar (router-based) */}
      <div style={{ marginTop: 12 }}>
        {typeof renderNextActionBar === "function" ? (
          renderNextActionBar({
            onRefresh: () => generateAndLoadLatestReport(),
            refreshLabel: hasLatest ? "Refresh Latest" : "Generate + Load Latest",
            refreshDisabled: busy || !!reasonReport,
            refreshTitle: reasonReport || "Refresh / generate latest report",

            // "Back" should navigate
            backTo: null, // we won't use backTo with router
            onBack: () => go("/consultant/analysis/seed-demo"),
            backLabel: "Back: Seed Demo Responses →",
            backDisabled: busy || !!reasonSeed,
            backTitle: reasonSeed || "Back to seeding demo data",

            // "Next" should navigate
            onNext: () => go("/consultant/evaluations"),
            nextLabel: "Done: Back to Evaluations →",
            nextDisabled: busy,
            nextTitle: "Return to evaluations",

            extra: (
              <>
                <Button
                  onClick={() => go("/consultant/participants")}
                  disabled={busy || !!reasonEval}
                  title={reasonEval || "View participants"}
                  variant="secondary"
                >
                  View Participants
                </Button>

                <Button
                  onClick={() => go("/consultant/questions")}
                  disabled={busy || !!reasonListQs}
                  title={reasonListQs || "View questions"}
                  variant="secondary"
                >
                  View Questions
                </Button>
              </>
            ),
          })
        ) : (
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
            <Button
              onClick={() => go("/consultant/analysis/seed-demo")}
              disabled={busy || !!reasonSeed}
              variant="soft"
              title={reasonSeed || "Back to Seed Demo"}
            >
              Back: Seed Demo →
            </Button>

            <Button
              onClick={() => go("/consultant/evaluations")}
              disabled={busy}
              variant="secondary"
              title="Back to evaluations"
            >
              Done: Evaluations →
            </Button>

            <Button
              onClick={() => go("/consultant/participants")}
              disabled={busy || !!reasonEval}
              variant="soft"
              title={reasonEval || "View participants"}
            >
              View Participants
            </Button>

            <Button
              onClick={() => go("/consultant/questions")}
              disabled={busy || !!reasonListQs}
              variant="soft"
              title={reasonListQs || "View questions"}
            >
              View Questions
            </Button>
          </div>
        )}
      </div>

      {/* ✅ Report body */}
      {latestSummary?.report ? (
        <FindingsReport report={latestSummary.report} reportId={reportId} createdAt={result?.data?.created_at} ui={ui} />
      ) : latestSummary?.exec ? (
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
