import React, { useEffect } from "react";

/**
 * On/off switch for the evaluation in focus. Only one row can be on; turning it off clears the focus.
 */
function FocusSwitch({ on, disabled, label, onToggle }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={on}
      aria-label={label}
      title={on ? "Stop working on this evaluation" : "Work on this evaluation"}
      disabled={disabled}
      onClick={(e) => {
        e.stopPropagation(); // don't also trigger the row's click
        onToggle();
      }}
      style={{
        position: "relative",
        width: 40,
        height: 22,
        padding: 0,
        borderRadius: 999,
        border: `1px solid ${on ? "#1D4ED8" : "#94A3B8"}`,
        background: on ? "#2563EB" : "#E2E8F0",
        cursor: disabled ? "not-allowed" : "pointer",
        opacity: disabled ? 0.6 : 1,
        transition: "background 120ms",
        verticalAlign: "middle",
      }}
    >
      <span
        aria-hidden
        style={{
          position: "absolute",
          top: 2,
          left: on ? 20 : 2,
          width: 16,
          height: 16,
          borderRadius: "50%",
          background: "white",
          boxShadow: "0 1px 2px rgba(0,0,0,0.3)",
          transition: "left 120ms",
        }}
      />
    </button>
  );
}

/**
 * List Evaluations page (router-based)
 */
export default function ListEvaluationsPage({
  ui,

  // data
  evaluations,
  evalsLoadedAt,
  evalId,

  // global state
  busy,

  // actions
  listEvaluations,
  setFocusFromEvaluationRow,
  clearFocus,

  // router nav
  go, // ✅ required: go("/consultant/...")

  // helpers
  formatDateMaybe,

  // styles
  tableWrapStyle,
  tdStyle,
  rowHoverStyle,
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

  return (
    <Card
      title="Evaluations"
      subtitle="Select the evaluation you want to work on. The sidebar then shows your progress and the next step."
      right={
        <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
          <Button onClick={listEvaluations} disabled={busy} variant="secondary">
            {busy ? "Loading…" : "Refresh"}
          </Button>
          <Button onClick={() => go("/consultant/evaluations/create")} disabled={busy} variant="primary">
            Create evaluation
          </Button>
        </div>
      }
    >
      <div>
        <div style={tableWrapStyle()}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
            <thead style={{ background: "#F8FAFC" }}>
              <tr>
                {["Evaluation", "Client", "Sector", "Year", "Regulators", "Created", "In focus"].map((h) => (
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
                  <td style={{ padding: 14, color: "#64748B" }} colSpan={7}>
                    {!evalsLoadedAt ? (
                      "Loading evaluations…"
                    ) : (
                      <>
                        No evaluations yet. Click <b>Create evaluation</b> to set one up.
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
                      title="Click to work on this evaluation"
                    >
                      <td style={tdStyle()}>
                        <div style={{ fontWeight: 900, color: "#0F172A" }}>{ev.evaluation_id}</div>
                      </td>

                      <td style={tdStyle()}>{ev.tenant_name || "—"}</td>
                      <td style={tdStyle()}>{ev.sector || "—"}</td>
                      <td style={tdStyle()}>{ev.year ?? "—"}</td>
                      <td style={tdStyle()}>
                        {(ev.regulators || []).length ? (ev.regulators || []).join(", ") : "—"}
                      </td>
                      <td style={tdStyle()}>{formatDateMaybe?.(ev.created_at)}</td>
                      <td style={{ ...tdStyle(), textAlign: "right", whiteSpace: "nowrap" }}>
                        <FocusSwitch
                          on={isFocused}
                          disabled={busy}
                          label={`In focus: ${ev.evaluation_id}`}
                          onToggle={() => (isFocused ? clearFocus?.() : setFocusFromEvaluationRow?.(ev))}
                        />
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>
    </Card>
  );
}
