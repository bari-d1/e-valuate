import React from "react";

/**
 * Generate Questions (AI) page (extracted from App.jsx)
 */
export default function GenerateQuestionsAIPage({
  ui,

  busy,
  focus,
  aiDrafts,
  aiSelectedIds,
  aiGeneratedAt,
  aiAddStatus,

  aiFile,
  aiFileName,
  aiFileTextPreview,
  aiFileInputRef,

  aiNQuestions,
  setAiNQuestions,
  aiAllowedTypes,
  setAiAllowedTypes,
  aiDimensionHints,
  setAiDimensionHints,

  ANSWER_TYPES,

  deriveQuestionnaireTarget,
  lockReason,
  handleAiFilePick,
  generateQuestionsFromFile,

  selectAllDrafts,
  toggleDraftSelected,
  setDraftField,
  addSelectedDraftsToQuestionnaire,

  go, // ✅ router navigation
}) {
  // ✅ Guard: prevents blank screen + tells you what's missing
  const required = [
    "Card",
    "Badge",
    "Field",
    "Button",
    "renderFlowBar",
    "miniPanelStyle",
    "miniTitleStyle",
    "tableWrapStyle",
    "tdStyle",
    "inputStyle",
    "textareaStyle",
  ];
  const missing = required.filter((k) => !ui?.[k]);
  if (missing.length || typeof go !== "function") {
    return (
      <div style={{ padding: 20 }}>
        <b>GenerateQuestionsAIPage:</b> missing helpers:
        <div style={{ marginTop: 8, fontFamily: "monospace", fontSize: 12 }}>
          {[
            ...missing.map((x) => `ui.${x}`),
            ...(typeof go !== "function" ? ["go (function)"] : []),
          ].join(", ")}
        </div>
        <div style={{ marginTop: 8, fontFamily: "monospace", fontSize: 12 }}>
          ui keys: {Object.keys(ui || {}).join(", ")}
        </div>
      </div>
    );
  }

  const {
    Card,
    Badge,
    Field,
    Button,
    renderFlowBar,
    miniPanelStyle,
    miniTitleStyle,
    tableWrapStyle,
    tdStyle,
    inputStyle,
    textareaStyle,
  } = ui;

  const { t, v } = deriveQuestionnaireTarget();
  const draftCount = aiDrafts?.length || 0;
  const selectedCount = (aiDrafts || []).filter((d) => aiSelectedIds?.[d._local_id]).length;

  // Locks
  const reasonAI = lockReason("ai_questions");

  // File requirement
  const reasonFile = !reasonAI && !aiFile ? "Choose a file first." : "";

  const disabledAI = busy || !!reasonAI;
  const disabledGenerate = busy || !!reasonAI || !!reasonFile;
  const disabledAdd = busy || !!reasonAI || draftCount === 0 || selectedCount === 0;

  return (
    <Card
      title="Generate Questions (AI)"
      subtitle="Upload a file and generate draft questions. Review, edit, select, then add to the questionnaire."
      right={<Badge tone="purple">AI</Badge>}
    >
      {focus}

      <div style={{ marginTop: 10, display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
        <Badge tone="gray">
          Target questionnaire: {String(t)} v{String(v)}
        </Badge>
        {aiGeneratedAt ? <Badge tone="gray">Generated: {aiGeneratedAt}</Badge> : null}
        {reasonAI ? <Badge tone="amber">{reasonAI}</Badge> : null}
      </div>

      <div style={{ marginTop: 14, display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
        {/* Panel 1: File */}
        <div style={miniPanelStyle()}>
          <div style={miniTitleStyle()}>1) Upload Source File</div>

          <Field
            label="File"
            hint="Supported uploads: .txt, .md, .docx (extracted on the server). PDF and legacy .doc are not supported yet."
          >
            <input
              ref={aiFileInputRef}
              type="file"
              accept=".txt,.md,.markdown,.docx"
              onChange={(e) => handleAiFilePick(e.target.files?.[0] || null)}
              style={{ display: "none" }}
            />

            <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
              <Button
                variant="soft"
                disabled={disabledAI}
                onClick={() => aiFileInputRef.current?.click()}
                title={reasonAI || "Choose a file"}
              >
                Browse file…
              </Button>

              <span style={{ fontSize: 13, color: aiFileName ? "#0F172A" : "#64748B", fontWeight: 700 }}>
                {aiFileName || "No file selected"}
              </span>

              {aiFileName ? (
                <Button
                  variant="soft"
                  disabled={disabledAI}
                  onClick={() => {
                    handleAiFilePick(null);
                    if (aiFileInputRef.current) aiFileInputRef.current.value = "";
                  }}
                  title={reasonAI || "Clear selected file"}
                >
                  Clear
                </Button>
              ) : null}
            </div>
          </Field>

          {!aiFileName ? (
            <div style={{ marginTop: 10, fontSize: 13, color: "#64748B" }}>
              {reasonAI ? (
                <>
                  <b>Locked:</b> {reasonAI}
                </>
              ) : (
                <>Upload a policy/framework document to generate questions.</>
              )}
            </div>
          ) : null}

          {aiFileTextPreview ? (
            <div style={{ marginTop: 12 }}>
              <Field label="Preview (first ~3000 chars)">
                <textarea value={aiFileTextPreview} readOnly style={textareaStyle(160)} />
              </Field>
            </div>
          ) : null}
        </div>

        {/* Panel 2: Settings */}
        <div style={miniPanelStyle()}>
          <div style={miniTitleStyle()}>2) Generate Settings</div>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
            <Field label="Number of questions">
              <input
                inputMode="numeric"
                value={aiNQuestions}
                onChange={(e) => setAiNQuestions(e.target.value)}
                style={inputStyle()}
                disabled={disabledAI}
              />
            </Field>

            <Field label="Allowed answer types">
              <div style={{ display: "flex", flexWrap: "wrap", gap: 10, paddingTop: 6 }}>
                {ANSWER_TYPES.map((a) => {
                  const checked = aiAllowedTypes.includes(a.key);
                  return (
                    <label key={a.key} style={{ display: "flex", gap: 8, alignItems: "center", color: "#0F172A" }}>
                      <input
                        type="checkbox"
                        checked={checked}
                        disabled={disabledAI}
                        onChange={(e) => {
                          const next = new Set(aiAllowedTypes);
                          if (e.target.checked) next.add(a.key);
                          else next.delete(a.key);
                          setAiAllowedTypes(Array.from(next));
                        }}
                      />
                      <span style={{ fontSize: 13, fontWeight: 700 }}>{a.label}</span>
                    </label>
                  );
                })}
              </div>
            </Field>
          </div>

          <div style={{ marginTop: 12 }}>
            <Field label="Dimension hints (comma-separated)" hint="Optional: helps AI map questions into your preferred dimensions">
              <input
                value={aiDimensionHints}
                onChange={(e) => setAiDimensionHints(e.target.value)}
                style={inputStyle()}
                autoComplete="off"
                spellCheck={false}
                disabled={disabledAI}
              />
            </Field>
          </div>

          <div style={{ marginTop: 12, display: "flex", gap: 10, flexWrap: "wrap" }}>
            <Button
              onClick={generateQuestionsFromFile}
              disabled={disabledGenerate}
              variant="primary"
              title={reasonAI || reasonFile || "Generate draft questions"}
            >
              {busy ? "Generating..." : "Generate Drafts"}
            </Button>

            <Button
              variant="secondary"
              disabled={disabledAI}
              onClick={() => {
                setAiNQuestions("10");
                setAiAllowedTypes(["rating", "comment"]);
                setAiDimensionHints("Board Composition, Risk Oversight, Strategy & Performance, Controls & Compliance");
              }}
              title={reasonAI || "Load demo defaults"}
            >
              Use Demo Defaults →
            </Button>
          </div>

          <div style={{ marginTop: 10, fontSize: 12, color: "#64748B" }}>
            Tip: Generate drafts first; then edit/select; then add to questionnaire.
          </div>
        </div>
      </div>

      {renderFlowBar({
        left: [
          {
            key: "select_all",
            label: "Select all",
            onClick: () => selectAllDrafts(true),
            disabled: busy || draftCount === 0 || !!reasonAI,
            title: reasonAI || "Select all drafts",
            variant: "soft",
          },
          {
            key: "select_none",
            label: "Select none",
            onClick: () => selectAllDrafts(false),
            disabled: busy || draftCount === 0 || !!reasonAI,
            title: reasonAI || "Deselect all drafts",
            variant: "soft",
          },
        ],
        meta: (
          <>
            <Badge tone="gray">Drafts: {draftCount}</Badge>
            <Badge tone="gray">Selected: {selectedCount}</Badge>
            {aiAddStatus ? (
              <>
                <Badge tone="green">Created: {aiAddStatus.created}</Badge>
                <Badge tone="amber">Skipped: {aiAddStatus.skipped}</Badge>
                <Badge tone={aiAddStatus.errors?.length ? "red" : "gray"}>Errors: {aiAddStatus.errors?.length || 0}</Badge>
              </>
            ) : null}
          </>
        ),
        right: [
          {
            key: "add_selected",
            label: busy ? "Adding..." : "Add Selected →",
            onClick: addSelectedDraftsToQuestionnaire,
            disabled: disabledAdd,
            variant: "primary",
            title: reasonAI ? reasonAI : selectedCount === 0 ? "Select at least one draft" : "Bulk insert selected questions",
          },
        ],
        marginTop: 14,
      })}

      <div style={{ marginTop: 12 }}>
        <div style={tableWrapStyle()}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
            <thead style={{ background: "#F8FAFC" }}>
              <tr>
                {["Select", "Dimension", "Type", "Weight", "Active", "Text"].map((h) => (
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
              {draftCount === 0 ? (
                <tr>
                  <td style={{ padding: 14, color: "#64748B" }} colSpan={6}>
                    {reasonAI ? (
                      <>
                        <b>Locked:</b> {reasonAI}
                      </>
                    ) : (
                      <>
                        No drafts yet. Upload a file and click <b>Generate Drafts</b>.
                      </>
                    )}
                  </td>
                </tr>
              ) : (
                aiDrafts.map((d) => {
                  const sel = !!aiSelectedIds?.[d._local_id];
                  return (
                    <tr key={d._local_id} style={{ borderBottom: "1px solid #F1F5F9" }}>
                      <td style={tdStyle()}>
                        <input
                          type="checkbox"
                          checked={sel}
                          disabled={busy || !!reasonAI}
                          onChange={() => toggleDraftSelected(d._local_id)}
                        />
                      </td>

                      <td style={tdStyle()}>
                        <input
                          value={d.dimension}
                          disabled={busy || !!reasonAI}
                          onChange={(e) => setDraftField(d._local_id, "dimension", e.target.value)}
                          style={inputStyle()}
                        />
                      </td>

                      <td style={tdStyle()}>
                        <select
                          value={d.answer_type}
                          disabled={busy || !!reasonAI}
                          onChange={(e) => setDraftField(d._local_id, "answer_type", e.target.value)}
                          style={inputStyle()}
                        >
                          {ANSWER_TYPES.map((x) => (
                            <option key={x.key} value={x.key}>
                              {x.label}
                            </option>
                          ))}
                        </select>
                      </td>

                      <td style={tdStyle()}>
                        <input
                          inputMode="numeric"
                          value={String(d.weight ?? 1)}
                          disabled={busy || !!reasonAI}
                          onChange={(e) => setDraftField(d._local_id, "weight", e.target.value)}
                          style={inputStyle()}
                        />
                      </td>

                      <td style={tdStyle()}>
                        <select
                          value={d.active ? "1" : "0"}
                          disabled={busy || !!reasonAI}
                          onChange={(e) => setDraftField(d._local_id, "active", e.target.value === "1")}
                          style={inputStyle()}
                        >
                          <option value="1">Active</option>
                          <option value="0">Inactive</option>
                        </select>
                      </td>

                      <td style={tdStyle()}>
                        <textarea
                          value={d.text}
                          disabled={busy || !!reasonAI}
                          onChange={(e) => setDraftField(d._local_id, "text", e.target.value)}
                          style={textareaStyle(90)}
                          spellCheck={false}
                        />
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>

        <div style={{ marginTop: 10, fontSize: 12, color: "#64748B" }}>
          Pro tip: Keep “Select all” on for demos, then deselect anything you don’t want to insert.
        </div>
      </div>
    </Card>
  );
}
