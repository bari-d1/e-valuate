// ✅ DROP-IN App.jsx (Questionnaire grouping + AI question generation via FILE upload)
// Changes:
// 1) Sidebar tasks grouped: Evaluations / Questionnaire / Participants / Analysis
// 2) Terminology aligned: "Questionnaire" (instead of Instrument)
// 3) New screen: "Generate Questions (AI)" using uploaded file (no copy/paste required)
//    - Upload file -> reads text client-side for .txt/.md
//    - For .pdf/.docx/.doc it uploads to backend (if supported), else shows helpful error
//    - Preview generated drafts -> select -> Add Selected (bulk create)
// 4) Uses evaluation-selected questionnaire (template_code/version) by default
//
// Assumed backend endpoints (adjust only if different):
//   GET    /api/v1/evaluations/{evaluation_id}                      -> returns { ..., questionnaire: { template_code, version } } OR { instrument: {...} }
//   PATCH  /api/v1/evaluations/{evaluation_id}/questionnaire        body: { template_code, version }
//
//   GET    /api/v1/evaluations/{evaluation_id}/questions?template_code=DEFAULT&version=1
//   POST   /api/v1/evaluations/{evaluation_id}/questions            (manual create, unchanged)
//   PATCH  /api/v1/questions/{question_id}                          body: { active: bool }
//
//   POST   /api/v1/evaluations/{evaluation_id}/questionnaire/generate
//          -> generates drafts (does NOT write) from:
//             - JSON: { source_text, n_questions, template_code, version, allowed_answer_types, dimension_hints }
//             - OR multipart file upload (optional): FormData { file, n_questions, template_code, version, ... }
//
//   POST   /api/v1/evaluations/{evaluation_id}/questions/bulk
//          -> bulk insert: { template_code, version, items: [...] }
//
// Notes:
// - If your backend still uses "instrument" instead of "questionnaire", this UI supports both.
// - If you don’t have the /generate or /bulk endpoints yet, you’ll see clear errors,
//   and you can wire endpoints later without changing the UI again.

//import React, { useMemo, useState, useEffect } from "react";
import React, { useMemo, useState, useEffect, useRef } from "react";


const API_BASE = import.meta.env.VITE_API_BASE || "http://127.0.0.1:8000";

/* --------------------------
   Stable constants
-------------------------- */
const PAGES = [{ key: "consultant", label: "Consultant" }];

// ✅ NEW: Grouped sidebar tasks (replaces flat CONSULTANT_TASKS)
const CONSULTANT_TASK_GROUPS = [
  {
    group: "Evaluations",
    items: [
      { key: "list_evaluations", label: "List Evaluations" },
      { key: "create_eval", label: "Create Evaluation" },
    ],
  },
  {
    group: "Questionnaire",
    items: [
      { key: "select_questionnaire", label: "Select Questionnaire" },
      { key: "list_questions", label: "View Questions" },
      { key: "create_questions_manual", label: "Add / Edit Questions" },
      { key: "seed_questions", label: "Seed Default Questionnaire" },
      { key: "generate_questions_ai", label: "Generate Questions (AI)" },
    ],
  },
  {
    group: "Participants",
    items: [
      { key: "invite_participants", label: "Invite Participants" },
      { key: "list_participants", label: "View Participants" },
    ],
  },
  {
    group: "Analysis",
    items: [
      { key: "seed_demo_responses", label: "Seed Demo Responses" },
      { key: "generate_report", label: "Generate Report" },
    ],
  },
];

const ANSWER_TYPES = [
  { key: "rating", label: "Rating (1–5)" },
  { key: "yesno", label: "Yes / No" },
  { key: "comment", label: "Comment" },
];

/* --------------------------
   Utils
-------------------------- */
function pretty(obj) {
  return JSON.stringify(obj, null, 2);
}

function parseCsvLine(line) {
  const parts = line
    .split(",")
    .map((x) => x.trim())
    .filter(Boolean);

  if (!parts.length) return null;

  return {
    email: (parts[0] || "").trim(),
    full_name: parts[1] || null,
    role: parts[2] || null,
  };
}

function parseRegulators(input) {
  return (input || "")
    .split(",")
    .map((x) => x.trim())
    .filter(Boolean);
}

async function safeJsonOrText(res) {
  const ct = res.headers.get("content-type") || "";
  if (ct.includes("application/json")) return await res.json();
  const text = await res.text();
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

function formatDateMaybe(iso) {
  if (!iso) return "—";
  return String(iso).replace("T", " ").replace("Z", "");
}

function clampInt(n, fallback, minV, maxV) {
  const x = Number(n);
  if (!Number.isFinite(x)) return fallback;
  return Math.max(minV, Math.min(maxV, Math.trunc(x)));
}

function normalizeAnswerTypes(keys) {
  const allowed = new Set(ANSWER_TYPES.map((x) => x.key));
  return (keys || []).map(String).filter((k) => allowed.has(k));
}

/* --------------------------
   UI Components
-------------------------- */
function Badge({ children, tone = "blue" }) {
  const tones = {
    blue: { bg: "#E6F0FF", fg: "#1E40AF", bd: "#BFDBFE" },
    green: { bg: "#E8FFF3", fg: "#065F46", bd: "#A7F3D0" },
    amber: { bg: "#FFF7ED", fg: "#92400E", bd: "#FED7AA" },
    gray: { bg: "#F3F4F6", fg: "#374151", bd: "#E5E7EB" },
    red: { bg: "#FEF2F2", fg: "#991B1B", bd: "#FECACA" },
    purple: { bg: "#F3E8FF", fg: "#6B21A8", bd: "#E9D5FF" },
  };
  const t = tones[tone] || tones.gray;

  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 8,
        padding: "4px 10px",
        borderRadius: 999,
        border: `1px solid ${t.bd}`,
        background: t.bg,
        color: t.fg,
        fontSize: 12,
        fontWeight: 600,
      }}
    >
      {children}
    </span>
  );
}

function Card({ title, subtitle, children, right }) {
  return (
    <div
      style={{
        background: "white",
        border: "1px solid #E5E7EB",
        borderRadius: 14,
        padding: 16,
        boxShadow: "0 1px 2px rgba(0,0,0,0.04)",
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "flex-start",
          justifyContent: "space-between",
          gap: 12,
        }}
      >
        <div>
          <div style={{ fontSize: 16, fontWeight: 800, color: "#0F172A" }}>
            {title}
          </div>
          {subtitle ? (
            <div style={{ marginTop: 4, color: "#64748B", fontSize: 13 }}>
              {subtitle}
            </div>
          ) : null}
        </div>
        {right ? <div>{right}</div> : null}
      </div>
      <div style={{ marginTop: 14 }}>{children}</div>
    </div>
  );
}

function Button({ children, onClick, disabled, variant = "primary", title }) {
  const styles =
    variant === "primary"
      ? { bg: "#2563EB", fg: "white", bd: "#1D4ED8" }
      : variant === "soft"
      ? { bg: "#EEF2FF", fg: "#1E40AF", bd: "#C7D2FE" }
      : variant === "danger"
      ? { bg: "#FEF2F2", fg: "#991B1B", bd: "#FECACA" }
      : variant === "highlight"
      ? { bg: "#ECFDF5", fg: "#065F46", bd: "#A7F3D0" }
      : { bg: "#F8FAFC", fg: "#0F172A", bd: "#E2E8F0" };

  return (
    <button
      onClick={onClick}
      disabled={disabled}
      title={title}
      style={{
        padding: "10px 12px",
        borderRadius: 10,
        border: `1px solid ${styles.bd}`,
        background: disabled ? "#E5E7EB" : styles.bg,
        color: disabled ? "#6B7280" : styles.fg,
        fontWeight: 800,
        cursor: disabled ? "not-allowed" : "pointer",
      }}
    >
      {children}
    </button>
  );
}

function Field({ label, children, hint }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      <div style={{ fontSize: 13, color: "#334155", fontWeight: 700 }}>
        {label}
      </div>
      {children}
      {hint ? (
        <div style={{ fontSize: 12, color: "#64748B" }}>{hint}</div>
      ) : null}
    </div>
  );
}

/* --------------------------
   Styles
-------------------------- */
function pageShellStyle() {
  return {
    minHeight: "100vh",
    display: "grid",
    gridTemplateColumns: "260px 1fr",
    background: "#F1F5F9",
  };
}

function sidebarStyle() {
  return {
    background: "linear-gradient(180deg, #0B1220 0%, #111827 100%)",
    borderRight: "1px solid rgba(255,255,255,0.08)",
    display: "flex",
    flexDirection: "column",
  };
}

function navItemStyle(active) {
  return {
    width: "100%",
    textAlign: "left",
    padding: "10px 12px",
    borderRadius: 12,
    border: "1px solid rgba(255,255,255,0.08)",
    background: active ? "rgba(37,99,235,0.22)" : "rgba(255,255,255,0.03)",
    color: "white",
    fontWeight: 900,
    cursor: "pointer",
  };
}

// ✅ grouped task item style (same for all tasks; no random color differences)
function subNavItemStyle(active) {
  return {
    width: "100%",
    textAlign: "left",
    padding: "10px 12px",
    borderRadius: 12,
    border: "1px solid rgba(255,255,255,0.08)",
    background: active ? "rgba(37,99,235,0.22)" : "rgba(255,255,255,0.03)",
    color: active ? "white" : "rgba(255,255,255,0.9)",
    fontWeight: active ? 900 : 700,
    cursor: "pointer",
    marginBottom: 8,
  };
}

function groupHeaderStyle() {
  return {
    margin: "12px 8px 10px",
    fontSize: 12,
    fontWeight: 900,
    color: "rgba(255,255,255,0.75)",
    letterSpacing: 0.2,
    textTransform: "uppercase",
  };
}

function mainStyle() {
  return { padding: 18 };
}

function topbarStyle() {
  return {
    background: "white",
    border: "1px solid #E5E7EB",
    borderRadius: 14,
    padding: "14px 16px",
    boxShadow: "0 1px 2px rgba(0,0,0,0.04)",
  };
}

function inputStyle() {
  return {
    width: "100%",
    padding: "10px 12px",
    borderRadius: 10,
    border: "1px solid #CBD5E1",
    outline: "none",
    fontSize: 14,
    background: "white",
  };
}

function textareaStyle(h = 120) {
  return {
    width: "100%",
    minHeight: h,
    padding: "10px 12px",
    borderRadius: 10,
    border: "1px solid #CBD5E1",
    outline: "none",
    fontSize: 13,
    background: "white",
    fontFamily:
      "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace",
  };
}

function tdStyle() {
  return { padding: "10px 12px", color: "#0F172A", verticalAlign: "top" };
}

function miniPanelStyle() {
  return {
    background: "white",
    border: "1px solid #E5E7EB",
    borderRadius: 12,
    padding: 12,
  };
}

function miniTitleStyle() {
  return {
    fontWeight: 900,
    fontSize: 13,
    color: "#0F172A",
    marginBottom: 8,
  };
}

function tableWrapStyle() {
  return {
    marginTop: 12,
    overflow: "auto",
    border: "1px solid #E5E7EB",
    borderRadius: 12,
    background: "white",
  };
}

function rowHoverStyle() {
  return {
    cursor: "pointer",
    transition: "background 120ms",
  };
}

/* --------------------------
   App
-------------------------- */
export default function App() {
  // Navigation
  const [page, setPage] = useState("consultant");
  const [task, setTask] = useState("list_evaluations");

  // Shared State
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState(null);

  // Evaluation in focus
  const [evalId, setEvalId] = useState("eval-002");

  // ✅ Questionnaire selection (persisted on evaluation)
  const [selectedTemplate, setSelectedTemplate] = useState("DEFAULT");
  const [selectedVersion, setSelectedVersion] = useState("1");
  const [questionnaireLoadedAt, setQuestionnaireLoadedAt] = useState("");

  // List evaluations state
  const [evaluations, setEvaluations] = useState([]);
  const [evalsLoadedAt, setEvalsLoadedAt] = useState("");

  // Create Evaluation form
  const [newEvalId, setNewEvalId] = useState("eval-002");
  const [tenantName, setTenantName] = useState("EMOK Express");
  const [sector, setSector] = useState("insurance");
  const [year, setYear] = useState("2025");
  const [regulatorsText, setRegulatorsText] = useState("NAICOM, FRC");

  // Invite Participants form
  const [inviteText, setInviteText] = useState(
    "board_member_13@demo-client.test,Board Member 13,INED\nboard_member_14@demo-client.test,Board Member 14,ED"
  );

  // Legacy fields kept in sync (so your existing endpoints keep working)
  const [templateCode, setTemplateCode] = useState("DEFAULT");
  const [version, setVersion] = useState("1");

  // Manual questions state
  const [questions, setQuestions] = useState([]);
  const [qsLoadedAt, setQsLoadedAt] = useState("");
  const [qsListLoadedAt, setQsListLoadedAt] = useState("");

  // Create question form (manual)
  const [qDimension, setQDimension] = useState("Board Composition");
  const [qText, setQText] = useState(
    "The board has an appropriate mix of skills, experience, and independence to oversee the organisation effectively."
  );
  const [qAnswerType, setQAnswerType] = useState("rating");
  const [qWeight, setQWeight] = useState("1");
  const [qActive, setQActive] = useState(true);

  const [qCreateStatus, setQCreateStatus] = useState(null); // { created: bool, message: str } | null

  // Demo response seed params
  const [invited, setInvited] = useState("12");
  const [responded, setResponded] = useState("10");
  const [randomSeed, setRandomSeed] = useState("42");

  // ✅ AI generation (file upload)
  const [aiFile, setAiFile] = useState(null);
  const [aiFileName, setAiFileName] = useState("");
  const [aiFileTextPreview, setAiFileTextPreview] = useState(""); // used for .txt/.md
  const [aiNQuestions, setAiNQuestions] = useState("10");
  const [aiDimensionHints, setAiDimensionHints] = useState(
    "Board Composition, Risk Oversight, Strategy & Performance, Controls & Compliance"
  );
  const [aiAllowedTypes, setAiAllowedTypes] = useState(["rating", "comment"]);
  const [aiDrafts, setAiDrafts] = useState([]); // generated drafts
  const [aiSelectedIds, setAiSelectedIds] = useState({}); // {idx: true}
  const [aiGeneratedAt, setAiGeneratedAt] = useState("");
  const [aiAddStatus, setAiAddStatus] = useState(null); // {created, skipped, errors} | null

  const latestSummary = useMemo(() => {
    const summaryJson = result?.data?.summary_json;
    if (!summaryJson) return null;

    const exec = summaryJson?.sections?.executive_summary;
    const recs = summaryJson?.sections?.recommendations?.recommendations || [];
    const analytics = summaryJson?.analytics;
    return { exec, recs, analytics };
  }, [result]);

  function beginAction() {
    setBusy(true);
    setError("");
    setResult(null);
  }

  // ✅ Sync questionnaire fields
  function syncQuestionnaireToUi(template_code, versionVal) {
    const t = String(template_code || "DEFAULT");
    const v = String(versionVal ?? "1");

    setSelectedTemplate(t);
    setSelectedVersion(v);

    // keep legacy fields in sync so your existing code keeps working
    setTemplateCode(t);
    setVersion(v);
  }

  // ✅ Load questionnaire from evaluation (supports backend returning `questionnaire` OR `instrument`)
  async function loadEvaluationQuestionnaire() {
    beginAction();
    try {
      if (!String(evalId || "").trim()) throw new Error("Evaluation ID is required.");

      const res = await fetch(
        `${API_BASE}/api/v1/evaluations/${encodeURIComponent(evalId)}`,
        { headers: { Accept: "application/json" } }
      );

      const data = await safeJsonOrText(res);
      if (!res.ok) throw new Error(typeof data === "string" ? data : pretty(data));

      const qn = data?.questionnaire || data?.instrument || {};
      syncQuestionnaireToUi(qn.template_code || "DEFAULT", qn.version ?? 1);
      setQuestionnaireLoadedAt(new Date().toLocaleString());

      setResult({ action: "load_evaluation_questionnaire", data });
    } catch (e) {
      setError(e?.message || String(e));
    } finally {
      setBusy(false);
    }
  }

  // ✅ Set questionnaire for evaluation (PATCH)
  async function setEvaluationQuestionnaire() {
    beginAction();
    try {
      if (!String(evalId || "").trim()) throw new Error("Evaluation ID is required.");

      const payload = {
        template_code: String(selectedTemplate || "DEFAULT").trim(),
        version: clampInt(selectedVersion, 1, 1, 100),
      };

      // NOTE: This uses /questionnaire. If your backend uses /instrument, switch this URL.
      const res = await fetch(
        `${API_BASE}/api/v1/evaluations/${encodeURIComponent(evalId)}/questionnaire`,
        {
          method: "PATCH",
          headers: { "Content-Type": "application/json", Accept: "application/json" },
          body: JSON.stringify(payload),
        }
      );

      const data = await safeJsonOrText(res);
      if (!res.ok) throw new Error(typeof data === "string" ? data : pretty(data));

      const qn = data?.questionnaire || data?.instrument || payload;
      syncQuestionnaireToUi(qn.template_code || payload.template_code, qn.version ?? payload.version);
      setQuestionnaireLoadedAt(new Date().toLocaleString());

      setResult({ action: "set_evaluation_questionnaire", data });
    } catch (e) {
      setError(e?.message || String(e));
    } finally {
      setBusy(false);
    }
  }

  // ✅ Auto-load questionnaire whenever evalId changes
  useEffect(() => {
    if (String(evalId || "").trim()) {
      loadEvaluationQuestionnaire();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [evalId]);

  async function handlePing() {
    beginAction();
    try {
      const res = await fetch(`${API_BASE}/api/v1/llm/sanity`, {
        headers: { Accept: "application/json" },
      });
      if (!res.ok) throw new Error(await res.text());
      const json = await res.json();
      setResult({ action: "ping", data: json });
    } catch (e) {
      setError(e?.message || String(e));
    } finally {
      setBusy(false);
    }
  }

  async function listEvaluations() {
    beginAction();
    try {
      const res = await fetch(`${API_BASE}/api/v1/evaluations`, {
        headers: { Accept: "application/json" },
      });

      const data = await safeJsonOrText(res);
      if (!res.ok) throw new Error(typeof data === "string" ? data : pretty(data));

      const items = Array.isArray(data?.items) ? data.items : [];
      setEvaluations(items);
      setEvalsLoadedAt(new Date().toLocaleString());

      setResult({ action: "list_evaluations", data });
    } catch (e) {
      setError(e?.message || String(e));
    } finally {
      setBusy(false);
    }
  }

  function setFocusFromEvaluationRow(ev, nextTaskKey) {
    const id = ev?.evaluation_id || ev?.id;
    if (id) setEvalId(String(id));
    if (nextTaskKey) setTask(nextTaskKey);
  }

  async function createEvaluation() {
    beginAction();
    try {
      const payload = {
        evaluation_id: (newEvalId || "").trim() || undefined,
        tenant_name: tenantName,
        sector,
        year: Number(year),
        regulators: parseRegulators(regulatorsText),
      };

      const res = await fetch(`${API_BASE}/api/v1/evaluations`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify(payload),
      });

      const data = await safeJsonOrText(res);
      if (!res.ok) throw new Error(typeof data === "string" ? data : pretty(data));

      setResult({ action: "create_evaluation", data });
      if (data?.evaluation_id) setEvalId(data.evaluation_id);

      try {
        await listEvaluations();
      } catch {
        // ignore
      }
    } catch (e) {
      setError(e?.message || String(e));
    } finally {
      setBusy(false);
    }
  }

  async function inviteParticipants() {
    beginAction();
    try {
      const lines = (inviteText || "")
        .split("\n")
        .map((x) => x.trim())
        .filter(Boolean);

      const participants = lines
        .map(parseCsvLine)
        .filter(Boolean)
        .filter((p) => p.email);

      if (!evalId.trim()) throw new Error("Evaluation ID is required.");
      if (!participants.length) throw new Error("No valid participants found in the input.");

      const res = await fetch(
        `${API_BASE}/api/v1/evaluations/${encodeURIComponent(evalId)}/participants/invite`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json", Accept: "application/json" },
          body: JSON.stringify({ participants }),
        }
      );

      const data = await safeJsonOrText(res);
      if (!res.ok) throw new Error(typeof data === "string" ? data : pretty(data));

      setResult({ action: "invite_participants", data });
    } catch (e) {
      setError(e?.message || String(e));
    } finally {
      setBusy(false);
    }
  }

  async function listParticipants() {
    beginAction();
    try {
      if (!evalId.trim()) throw new Error("Evaluation ID is required.");

      const res = await fetch(
        `${API_BASE}/api/v1/evaluations/${encodeURIComponent(evalId)}/participants`,
        { headers: { Accept: "application/json" } }
      );

      const data = await safeJsonOrText(res);
      if (!res.ok) throw new Error(typeof data === "string" ? data : pretty(data));

      setResult({ action: "list_participants", data });
    } catch (e) {
      setError(e?.message || String(e));
    } finally {
      setBusy(false);
    }
  }

  async function seedQuestions() {
    beginAction();
    try {
      if (!evalId.trim()) throw new Error("Evaluation ID is required.");

      const t = String(selectedTemplate || templateCode || "DEFAULT").trim();
      const v = String(selectedVersion || version || "1");

      const url =
        `${API_BASE}/api/v1/evaluations/${encodeURIComponent(evalId)}/seed/questions` +
        `?template_code=${encodeURIComponent(t)}` +
        `&version=${encodeURIComponent(String(v))}`;

      const res = await fetch(url, {
        method: "POST",
        headers: { Accept: "application/json" },
      });

      const data = await safeJsonOrText(res);
      if (!res.ok) throw new Error(typeof data === "string" ? data : pretty(data));

      setResult({ action: "seed_default_questionnaire", data });
    } catch (e) {
      setError(e?.message || String(e));
    } finally {
      setBusy(false);
    }
  }

  async function seedDemoResponses() {
    beginAction();
    try {
      if (!evalId.trim()) throw new Error("Evaluation ID is required.");
      if (Number(responded) > Number(invited))
        throw new Error("responded cannot be greater than invited");

      const t = String(selectedTemplate || templateCode || "DEFAULT").trim();
      const v = String(selectedVersion || version || "1");

      const url =
        `${API_BASE}/api/v1/evaluations/${encodeURIComponent(evalId)}/seed/demo-responses` +
        `?template_code=${encodeURIComponent(t)}` +
        `&version=${encodeURIComponent(String(v))}` +
        `&invited=${encodeURIComponent(String(invited))}` +
        `&responded=${encodeURIComponent(String(responded))}` +
        `&random_seed=${encodeURIComponent(String(randomSeed))}`;

      const res = await fetch(url, {
        method: "POST",
        headers: { Accept: "application/json" },
      });

      const data = await safeJsonOrText(res);
      if (!res.ok) throw new Error(typeof data === "string" ? data : pretty(data));

      setResult({ action: "seed_demo_responses", data });
    } catch (e) {
      setError(e?.message || String(e));
    } finally {
      setBusy(false);
    }
  }

  async function generateAndLoadLatestReport() {
    beginAction();
    try {
      if (!evalId.trim()) throw new Error("Evaluation ID is required.");

      const genRes = await fetch(
        `${API_BASE}/api/v1/evaluations/${encodeURIComponent(evalId)}/report/generate`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json", Accept: "application/json" },
          body: JSON.stringify({ include_trends: true, include_compliance: true }),
        }
      );

      const genData = await safeJsonOrText(genRes);
      if (!genRes.ok)
        throw new Error(typeof genData === "string" ? genData : pretty(genData));

      const generatedReportId = genData?.report_id;

      const latestRes = await fetch(
        `${API_BASE}/api/v1/evaluations/${encodeURIComponent(evalId)}/report`,
        { headers: { Accept: "application/json" } }
      );

      const latestData = await safeJsonOrText(latestRes);
      if (!latestRes.ok)
        throw new Error(
          typeof latestData === "string" ? latestData : pretty(latestData)
        );

      setResult({
        action: "generate_then_get_latest",
        meta: { generated_report_id: generatedReportId },
        data: latestData,
      });
    } catch (e) {
      setError(e?.message || String(e));
    } finally {
      setBusy(false);
    }
  }

  // List questions helper
  async function listQuestionsGeneric(setLoadedAt) {
    beginAction();
    try {
      if (!evalId.trim()) throw new Error("Evaluation ID is required.");

      const t = String(selectedTemplate || templateCode || "DEFAULT").trim();
      const v = String(selectedVersion || version || "1");

      const url =
        `${API_BASE}/api/v1/evaluations/${encodeURIComponent(evalId)}/questions` +
        `?template_code=${encodeURIComponent(t)}` +
        `&version=${encodeURIComponent(String(v))}`;

      const res = await fetch(url, { headers: { Accept: "application/json" } });
      const data = await safeJsonOrText(res);
      if (!res.ok) throw new Error(typeof data === "string" ? data : pretty(data));

      const items = Array.isArray(data?.items) ? data.items : [];
      setQuestions(items);
      setLoadedAt(new Date().toLocaleString());

      setResult({ action: "view_questions", data });
    } catch (e) {
      setError(e?.message || String(e));
    } finally {
      setBusy(false);
    }
  }

  async function listQuestionsTask() {
    return listQuestionsGeneric(setQsListLoadedAt);
  }

  async function listQuestionsManual() {
    return listQuestionsGeneric(setQsLoadedAt);
  }

  // Create question manual
  async function createQuestionManual() {
    beginAction();
    try {
      setQCreateStatus(null);

      if (!evalId.trim()) throw new Error("Evaluation ID is required.");

      const t = String(selectedTemplate || templateCode || "DEFAULT").trim();
      const v = clampInt(selectedVersion || version, 1, 1, 100);

      if (!String(t || "").trim()) throw new Error("Template Code is required.");
      if (!String(v || "").trim()) throw new Error("Version is required.");
      if (!String(qDimension || "").trim()) throw new Error("Dimension is required.");
      if (!String(qText || "").trim()) throw new Error("Question text is required.");

      const payload = {
        template_code: t,
        version: v,
        dimension: String(qDimension).trim(),
        text: String(qText).trim(),
        answer_type: String(qAnswerType || "rating").trim(),
        weight: clampInt(qWeight, 1, 1, 100),
        active: !!qActive,
      };

      const res = await fetch(
        `${API_BASE}/api/v1/evaluations/${encodeURIComponent(evalId)}/questions`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json", Accept: "application/json" },
          body: JSON.stringify(payload),
        }
      );

      const data = await safeJsonOrText(res);
      if (!res.ok) throw new Error(typeof data === "string" ? data : pretty(data));

      const createdFlag = !!data?.created;
      const msg = String(
        data?.message || (createdFlag ? "Question created." : "Already exists.")
      );
      setQCreateStatus({ created: createdFlag, message: msg });

      setResult({ action: "add_question_manual", data });

      try {
        await listQuestionsManual();
      } catch {
        // ignore
      }
    } catch (e) {
      setError(e?.message || String(e));
    } finally {
      setBusy(false);
    }
  }

  // Toggle question active
  async function toggleQuestionActive(question) {
    beginAction();
    try {
      const qid = question?.question_id || question?.id;
      if (!qid) throw new Error("Question id is missing from the row.");

      const nextActive = !Boolean(question.active);

      const res = await fetch(
        `${API_BASE}/api/v1/questions/${encodeURIComponent(String(qid))}`,
        {
          method: "PATCH",
          headers: { "Content-Type": "application/json", Accept: "application/json" },
          body: JSON.stringify({ active: nextActive }),
        }
      );

      const data = await safeJsonOrText(res);
      if (!res.ok) throw new Error(typeof data === "string" ? data : pretty(data));

      const updated = data?.question;

      setQuestions((prev) =>
        (prev || []).map((q) => {
          const id = q?.question_id || q?.id;
          if (String(id) !== String(qid)) return q;
          const newActive =
            updated && (updated.question_id || updated.id)
              ? Boolean(updated.active)
              : nextActive;
          return { ...q, active: newActive };
        })
      );

      setResult({ action: "toggle_question_active", data });
    } catch (e) {
      setError(e?.message || String(e));
    } finally {
      setBusy(false);
    }
  }

  /* --------------------------
     ✅ AI Generation (file upload)
  -------------------------- */

  // Reads text client-side for simple text files; otherwise leaves to backend (multipart)
  async function handleAiFilePick(file) {
    setAiAddStatus(null);
    setAiDrafts([]);
    setAiSelectedIds({});
    setAiGeneratedAt("");
    setResult(null);
    setError("");

    setAiFile(file || null);
    setAiFileName(file?.name || "");
    setAiFileTextPreview("");

    if (!file) return;

    const name = (file.name || "").toLowerCase();
    const isTextish = name.endsWith(".txt") || name.endsWith(".md") || name.endsWith(".markdown");

    if (isTextish) {
      const text = await file.text();
      setAiFileTextPreview(text.slice(0, 3000)); // preview small portion
    }
  }

  function deriveQuestionnaireTarget() {
    const t = String(selectedTemplate || templateCode || "DEFAULT").trim();
    const v = clampInt(selectedVersion || version, 1, 1, 100);
    return { t, v };
  }

  function parseHintsCsv(hints) {
    return (hints || "")
      .split(",")
      .map((x) => x.trim())
      .filter(Boolean);
  }

  // Generate drafts from file
  async function generateQuestionsFromFile() {
    beginAction();
    try {
      setAiAddStatus(null);
      setAiDrafts([]);
      setAiSelectedIds({});
      setAiGeneratedAt("");

      if (!evalId.trim()) throw new Error("Evaluation ID is required.");
      if (!aiFile) throw new Error("Please upload a file first.");

      const { t, v } = deriveQuestionnaireTarget();
      const n = clampInt(aiNQuestions, 10, 1, 50);
      const allowed_answer_types = normalizeAnswerTypes(aiAllowedTypes);
      const dimension_hints = parseHintsCsv(aiDimensionHints);

      const name = (aiFile.name || "").toLowerCase();
      const isTextish = name.endsWith(".txt") || name.endsWith(".md") || name.endsWith(".markdown");

      let res;
      // Option A: For .txt/.md, send JSON with source_text
      if (isTextish) {
        const source_text = await aiFile.text();

        const payload = {
          source_text,
          n_questions: n,
          template_code: t,
          version: v,
          allowed_answer_types,
          dimension_hints,
        };

        res = await fetch(
          `${API_BASE}/api/v1/evaluations/${encodeURIComponent(evalId)}/questionnaire/generate`,
          {
            method: "POST",
            headers: { "Content-Type": "application/json", Accept: "application/json" },
            body: JSON.stringify(payload),
          }
        );
      } else {
        // Option B: Upload file as multipart (PDF/DOCX etc) IF backend supports it
        const fd = new FormData();
        fd.append("file", aiFile);
        fd.append("n_questions", String(n));
        fd.append("template_code", String(t));
        fd.append("version", String(v));
        fd.append("allowed_answer_types", JSON.stringify(allowed_answer_types));
        fd.append("dimension_hints", JSON.stringify(dimension_hints));

        res = await fetch(
          `${API_BASE}/api/v1/evaluations/${encodeURIComponent(evalId)}/questionnaire/generate`,
          {
            method: "POST",
            headers: { Accept: "application/json" },
            body: fd,
          }
        );
      }

      const data = await safeJsonOrText(res);
      if (!res.ok) {
        // helpful error guidance for unsupported file types
        const msg = typeof data === "string" ? data : pretty(data);
        throw new Error(
          msg +
            "\n\nIf you're uploading PDF/DOCX and this fails, your backend may not support multipart file parsing yet.\n" +
            "Quick workaround: upload .txt for now, or add backend support for PDF/DOCX extraction."
        );
      }

      const items = Array.isArray(data?.items) ? data.items : [];
      // add local ids for selection/editing
      const drafts = items.map((x, idx) => ({
        _local_id: `${Date.now()}_${idx}`,
        dimension: x.dimension || "General",
        text: x.text || "",
        answer_type: x.answer_type || "rating",
        weight: x.weight ?? 1,
        active: x.active ?? true,
      }));

      setAiDrafts(drafts);
      // default select all
      const sel = {};
      drafts.forEach((d) => (sel[d._local_id] = true));
      setAiSelectedIds(sel);

      setAiGeneratedAt(new Date().toLocaleString());
      setResult({ action: "generate_questions_ai", data });
    } catch (e) {
      setError(e?.message || String(e));
    } finally {
      setBusy(false);
    }
  }

  function setDraftField(localId, field, value) {
    setAiDrafts((prev) =>
      (prev || []).map((d) => (d._local_id === localId ? { ...d, [field]: value } : d))
    );
  }

  function toggleDraftSelected(localId) {
    setAiSelectedIds((prev) => ({ ...prev, [localId]: !prev?.[localId] }));
  }

  function selectAllDrafts(flag) {
    const next = {};
    (aiDrafts || []).forEach((d) => (next[d._local_id] = !!flag));
    setAiSelectedIds(next);
  }

  async function addSelectedDraftsToQuestionnaire() {
    beginAction();
    try {
      setAiAddStatus(null);

      if (!evalId.trim()) throw new Error("Evaluation ID is required.");
      const { t, v } = deriveQuestionnaireTarget();

      const selected = (aiDrafts || []).filter((d) => aiSelectedIds?.[d._local_id]);
      if (!selected.length) throw new Error("Select at least one generated question to add.");

      // Basic validation
      const cleaned = selected.map((d) => ({
        dimension: String(d.dimension || "General").trim(),
        text: String(d.text || "").trim(),
        answer_type: String(d.answer_type || "rating").trim(),
        weight: clampInt(d.weight, 1, 1, 100),
        active: !!d.active,
      }));

      if (cleaned.some((x) => !x.text)) throw new Error("One or more selected questions has empty text.");

      const payload = {
        template_code: t,
        version: v,
        items: cleaned,
      };

      const res = await fetch(
        `${API_BASE}/api/v1/evaluations/${encodeURIComponent(evalId)}/questions/bulk`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json", Accept: "application/json" },
          body: JSON.stringify(payload),
        }
      );

      const data = await safeJsonOrText(res);
      if (!res.ok) throw new Error(typeof data === "string" ? data : pretty(data));

      const created = data?.created ?? 0;
      const skipped = data?.skipped_existing ?? 0;
      const errorsArr = Array.isArray(data?.errors) ? data.errors : [];
      setAiAddStatus({ created, skipped, errors: errorsArr });

      setResult({ action: "bulk_add_questions", data });

      // refresh questions list in background
      try {
        await listQuestionsManual();
      } catch {
        // ignore
      }
    } catch (e) {
      setError(e?.message || String(e));
    } finally {
      setBusy(false);
    }
  }

  /* --------------------------
     Focus header used across pages
  -------------------------- */
  function renderFocusHeader() {
    return (
      <div
        style={{
          display: "flex",
          gap: 10,
          alignItems: "center",
          flexWrap: "wrap",
        }}
      >
        <Field label="Evaluation in focus">
          <input
            value={evalId}
            onChange={(e) => setEvalId(e.target.value)}
            placeholder="eval-002"
            style={inputStyle()}
            autoComplete="off"
            spellCheck={false}
          />
        </Field>

        <div style={{ display: "flex", gap: 10, alignItems: "flex-end" }}>
          <Button onClick={handlePing} disabled={busy} variant="soft">
            {busy ? "Working..." : "Ping LLM"}
          </Button>
        </div>

        {/* Questionnaire selector (saved on evaluation) */}
        <div style={{ flex: 1, minWidth: 320 }}>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 120px", gap: 10 }}>
            <Field label="Questionnaire (template)">
              <input
                value={selectedTemplate}
                onChange={(e) => setSelectedTemplate(e.target.value)}
                style={inputStyle()}
                autoComplete="off"
                spellCheck={false}
              />
            </Field>
            <Field label="Version">
              <input
                inputMode="numeric"
                value={selectedVersion}
                onChange={(e) => setSelectedVersion(e.target.value)}
                style={inputStyle()}
              />
            </Field>
          </div>

          <div
            style={{
              marginTop: 10,
              display: "flex",
              gap: 10,
              flexWrap: "wrap",
              alignItems: "center",
            }}
          >
            <Button
              onClick={setEvaluationQuestionnaire}
              disabled={busy || !String(evalId || "").trim()}
              variant="primary"
            >
              {busy ? "Saving..." : "Save Questionnaire"}
            </Button>
            <Button
              onClick={loadEvaluationQuestionnaire}
              disabled={busy || !String(evalId || "").trim()}
              variant="soft"
            >
              Refresh
            </Button>
            <Badge tone="gray">
              Using: {String(selectedTemplate || "DEFAULT")} v{String(selectedVersion || "1")}
            </Badge>
            {questionnaireLoadedAt ? (
              <Badge tone="gray">Loaded: {questionnaireLoadedAt}</Badge>
            ) : null}
          </div>
        </div>
      </div>
    );
  }

  /* --------------------------
     Task render
  -------------------------- */
  function renderConsultantTask() {
    const focus = renderFocusHeader();

    // ✅ NEW screen: Select Questionnaire
    if (task === "select_questionnaire") {
      return (
        <Card
          title="Select Questionnaire"
          subtitle="Set the questionnaire (template + version) for this evaluation. All question actions use it."
          right={<Badge tone="blue">Consultant</Badge>}
        >
          {focus}
          <div style={{ marginTop: 12, color: "#64748B", fontSize: 13 }}>
            Tip: when you change the Evaluation ID, the questionnaire auto-loads from the backend.
          </div>
        </Card>
      );
    }

    // List evaluations
    if (task === "list_evaluations") {
      const count = evaluations?.length || 0;
      const latestId = evaluations?.[0]?.evaluation_id;

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

            <Button onClick={() => setTask("create_eval")} disabled={busy} variant="secondary">
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
                        No evaluations loaded yet. Click <b>Refresh Evaluations</b>.
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
                          onClick={() => setFocusFromEvaluationRow(ev)}
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
                                  setFocusFromEvaluationRow(ev, "invite_participants");
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
                                  setFocusFromEvaluationRow(ev, "list_questions");
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
                                  setFocusFromEvaluationRow(ev, "create_questions_manual");
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
                                  setFocusFromEvaluationRow(ev, "generate_report");
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
                          <td style={tdStyle()}>{formatDateMaybe(ev.created_at)}</td>
                        </tr>
                      );
                    })
                  )}
                </tbody>
              </table>
            </div>

            <div style={{ marginTop: 12, display: "flex", gap: 10, flexWrap: "wrap" }}>
              <Button
                onClick={() => setTask("invite_participants")}
                disabled={busy || !String(evalId || "").trim()}
                variant="primary"
              >
                Continue with Focus →
              </Button>
              <Button onClick={() => setTask("select_questionnaire")} disabled={busy} variant="secondary">
                Select Questionnaire →
              </Button>
              <Button onClick={() => setTask("list_questions")} disabled={busy} variant="secondary">
                View Questions →
              </Button>
              <Button onClick={() => setTask("generate_questions_ai")} disabled={busy} variant="highlight">
                Generate (AI) →
              </Button>
            </div>
          </div>
        </Card>
      );
    }

    // Create evaluation
    if (task === "create_eval") {
      return (
        <Card
          title="Create Evaluation"
          subtitle="Create an evaluation cycle (client + sector + year + regulators)."
          right={<Badge tone="blue">Consultant</Badge>}
        >
          {focus}

          <div style={{ marginTop: 14, display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
            <Field label="Evaluation ID (optional)">
              <input
                value={newEvalId}
                onChange={(e) => setNewEvalId(e.target.value)}
                style={inputStyle()}
                autoComplete="off"
                spellCheck={false}
              />
            </Field>
            <Field label="Year">
              <input
                inputMode="numeric"
                value={year}
                onChange={(e) => setYear(e.target.value)}
                style={inputStyle()}
              />
            </Field>

            <Field label="Tenant Name">
              <input
                value={tenantName}
                onChange={(e) => setTenantName(e.target.value)}
                style={inputStyle()}
                autoComplete="off"
                spellCheck={false}
              />
            </Field>
            <Field label="Sector">
              <input
                value={sector}
                onChange={(e) => setSector(e.target.value)}
                style={inputStyle()}
                autoComplete="off"
                spellCheck={false}
              />
            </Field>

            <div style={{ gridColumn: "1 / -1" }}>
              <Field label="Regulators (comma-separated)" hint='Example: "NAICOM, FRC"'>
                <input
                  value={regulatorsText}
                  onChange={(e) => setRegulatorsText(e.target.value)}
                  style={inputStyle()}
                  autoComplete="off"
                  spellCheck={false}
                />
              </Field>
            </div>
          </div>

          <div style={{ marginTop: 14, display: "flex", gap: 10, flexWrap: "wrap" }}>
            <Button onClick={createEvaluation} disabled={busy || !tenantName.trim() || !sector.trim()}>
              {busy ? "Creating..." : "Create Evaluation"}
            </Button>
            <Button
              onClick={() => {
                setEvalId((newEvalId || "").trim() || evalId);
                setTask("invite_participants");
              }}
              disabled={busy}
              variant="secondary"
            >
              Next: Invite Participants →
            </Button>
            <Button onClick={() => setTask("list_evaluations")} disabled={busy} variant="soft">
              Back to Evaluations →
            </Button>
          </div>
        </Card>
      );
    }

    // Invite participants
    if (task === "invite_participants") {
      return (
        <Card
          title="Invite Participants"
          subtitle="Add board members/directors to an evaluation (idempotent by email)."
          right={<Badge tone="blue">Consultant</Badge>}
        >
          {focus}

          <div style={{ marginTop: 14 }}>
            <Field
              label="Participants (one per line)"
              hint='Formats: "email" OR "email,Full Name" OR "email,Full Name,Role"'
            >
              <textarea
                value={inviteText}
                onChange={(e) => setInviteText(e.target.value)}
                style={textareaStyle(140)}
                spellCheck={false}
              />
            </Field>
          </div>

          <div style={{ marginTop: 14, display: "flex", gap: 10, flexWrap: "wrap" }}>
            <Button onClick={inviteParticipants} disabled={busy || !evalId.trim()}>
              {busy ? "Inviting..." : "Invite Participants"}
            </Button>
            <Button onClick={listParticipants} disabled={busy || !evalId.trim()} variant="secondary">
              View Participants
            </Button>
            <Button onClick={() => setTask("list_questions")} disabled={busy} variant="secondary">
              Next: View Questions →
            </Button>
            <Button onClick={() => setTask("generate_questions_ai")} disabled={busy} variant="highlight">
              Generate Questions (AI) →
            </Button>
            <Button onClick={() => setTask("list_evaluations")} disabled={busy} variant="soft">
              Back to Evaluations →
            </Button>
          </div>
        </Card>
      );
    }

    // View participants
    if (task === "list_participants") {
      return (
        <Card
          title="Participants"
          subtitle="View participants and response status for the evaluation."
          right={<Badge tone="blue">Consultant</Badge>}
        >
          {focus}
          <div style={{ marginTop: 14, display: "flex", gap: 10, flexWrap: "wrap" }}>
            <Button onClick={listParticipants} disabled={busy || !evalId.trim()}>
              {busy ? "Loading..." : "Refresh List"}
            </Button>
            <Button onClick={() => setTask("list_questions")} disabled={busy} variant="secondary">
              Next: View Questions →
            </Button>
            <Button onClick={() => setTask("generate_questions_ai")} disabled={busy} variant="highlight">
              Generate Questions (AI) →
            </Button>
            <Button onClick={() => setTask("list_evaluations")} disabled={busy} variant="soft">
              Back to Evaluations →
            </Button>
          </div>

          {result?.action === "list_participants" ? (
            <div style={{ marginTop: 14 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
                <Badge tone="gray">Total: {result?.data?.count ?? 0}</Badge>
                <Badge tone="green">
                  Responded:{" "}
                  {(result?.data?.items || []).filter(
                    (x) => String(x.status || "").toLowerCase() === "responded"
                  ).length}
                </Badge>
                <Badge tone="amber">
                  Invited:{" "}
                  {(result?.data?.items || []).filter(
                    (x) => String(x.status || "").toLowerCase() === "invited"
                  ).length}
                </Badge>
              </div>

              <div style={tableWrapStyle()}>
                <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
                  <thead style={{ background: "#F8FAFC" }}>
                    <tr>
                      {["Name", "Email", "Role", "Status", "Invited At", "Responded At"].map((h) => (
                        <th
                          key={h}
                          style={{
                            textAlign: "left",
                            padding: "10px 12px",
                            borderBottom: "1px solid #E5E7EB",
                            color: "#0F172A",
                            fontWeight: 800,
                          }}
                        >
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {(result?.data?.items || []).map((p) => (
                      <tr key={p.participant_id} style={{ borderBottom: "1px solid #F1F5F9" }}>
                        <td style={tdStyle()}>{p.full_name || "—"}</td>
                        <td style={tdStyle()}>{p.email}</td>
                        <td style={tdStyle()}>{p.role || "—"}</td>
                        <td style={tdStyle()}>
                          <span
                            style={{
                              padding: "3px 8px",
                              borderRadius: 999,
                              fontWeight: 800,
                              fontSize: 12,
                              border: "1px solid #E5E7EB",
                              background:
                                String(p.status).toLowerCase() === "responded"
                                  ? "#E8FFF3"
                                  : "#FFF7ED",
                              color:
                                String(p.status).toLowerCase() === "responded"
                                  ? "#065F46"
                                  : "#92400E",
                            }}
                          >
                            {p.status}
                          </span>
                        </td>
                        <td style={tdStyle()}>{p.invited_at || "—"}</td>
                        <td style={tdStyle()}>{p.responded_at || "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ) : (
            <div style={{ marginTop: 12, color: "#64748B", fontSize: 13 }}>
              Click <b>Refresh List</b> to load participants.
            </div>
          )}
        </Card>
      );
    }

    // View Questions
    if (task === "list_questions") {
      const qCount = questions?.length || 0;

      return (
        <Card
          title="View Questions"
          subtitle="Lists questions for the questionnaire selected on this evaluation (template/version)."
          right={<Badge tone="blue">Consultant</Badge>}
        >
          {focus}

          <div
            style={{
              marginTop: 14,
              display: "flex",
              gap: 10,
              flexWrap: "wrap",
              alignItems: "center",
            }}
          >
            <Button onClick={listQuestionsTask} disabled={busy || !evalId.trim()} variant="primary">
              {busy ? "Loading..." : "Load Questions"}
            </Button>

            <Button onClick={() => setTask("create_questions_manual")} disabled={busy} variant="secondary">
              Add / Edit Questions →
            </Button>

            <Button onClick={() => setTask("generate_questions_ai")} disabled={busy} variant="highlight">
              Generate Questions (AI) →
            </Button>

            <Badge tone="gray">
              Questionnaire: {String(selectedTemplate || "DEFAULT")} v{String(selectedVersion || "1")}
            </Badge>
            <Badge tone="gray">Count: {qCount}</Badge>
            {qsListLoadedAt ? <Badge tone="gray">Loaded: {qsListLoadedAt}</Badge> : null}

            <Button onClick={() => setTask("list_evaluations")} disabled={busy} variant="soft">
              Back to Evaluations →
            </Button>
          </div>

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
                      No questions loaded yet. Click <b>Load Questions</b>.
                    </td>
                  </tr>
                ) : (
                  questions.map((q) => (
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

    // Seed default questionnaire
    if (task === "seed_questions") {
      return (
        <Card
          title="Seed Default Questionnaire"
          subtitle="Seeds default questions into the evaluation’s selected questionnaire (safe to run multiple times)."
          right={<Badge tone="blue">Consultant</Badge>}
        >
          {focus}

          <div style={{ marginTop: 10, display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
            <Badge tone="gray">
              Target questionnaire: {String(selectedTemplate || "DEFAULT")} v{String(selectedVersion || "1")}
            </Badge>
          </div>

          <div style={{ marginTop: 14, display: "flex", gap: 10, flexWrap: "wrap" }}>
            <Button onClick={seedQuestions} disabled={busy || !evalId.trim()}>
              {busy ? "Seeding..." : "Seed Default Questionnaire"}
            </Button>

            <Button onClick={() => setTask("list_questions")} disabled={busy} variant="secondary">
              View Questions →
            </Button>

            <Button onClick={() => setTask("generate_questions_ai")} disabled={busy} variant="highlight">
              Generate Questions (AI) →
            </Button>

            <Button onClick={() => setTask("seed_demo_responses")} disabled={busy} variant="secondary">
              Next: Seed Demo Responses →
            </Button>

            <Button onClick={() => setTask("list_evaluations")} disabled={busy} variant="soft">
              Back to Evaluations →
            </Button>
          </div>
        </Card>
      );
    }

    // Add/Edit Questions (manual)
    if (task === "create_questions_manual") {
      const qCount = questions?.length || 0;

      return (
        <Card
          title="Add / Edit Questions"
          subtitle="Creates questions in the evaluation’s selected questionnaire. Toggle Active without deleting."
          right={<Badge tone="blue">Consultant</Badge>}
        >
          {focus}

          <div style={{ marginTop: 10, display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
            <Badge tone="gray">
              Target questionnaire: {String(selectedTemplate || "DEFAULT")} v{String(selectedVersion || "1")}
            </Badge>

            <Button onClick={() => setTask("generate_questions_ai")} disabled={busy} variant="highlight">
              Generate Questions (AI) →
            </Button>
          </div>

          <div style={{ marginTop: 14, display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
            <Button onClick={listQuestionsManual} disabled={busy || !evalId.trim()} variant="primary">
              {busy ? "Loading..." : "Load Questions"}
            </Button>
            <Badge tone="gray">Count: {qCount}</Badge>
            {qsLoadedAt ? <Badge tone="gray">Loaded: {qsLoadedAt}</Badge> : null}
            <Button onClick={() => setTask("list_questions")} disabled={busy} variant="secondary">
              View as Table →
            </Button>
            <Button onClick={() => setTask("seed_demo_responses")} disabled={busy} variant="secondary">
              Next: Seed Demo Responses →
            </Button>
            <Button onClick={() => setTask("list_evaluations")} disabled={busy} variant="soft">
              Back to Evaluations →
            </Button>
          </div>

          <div style={{ marginTop: 16, display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
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
                  <input inputMode="numeric" value={qWeight} onChange={(e) => setQWeight(e.target.value)} style={inputStyle()} />
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
                  <textarea value={qText} onChange={(e) => setQText(e.target.value)} style={textareaStyle(140)} spellCheck={false} />
                </Field>
              </div>

              <div style={{ marginTop: 12, display: "flex", gap: 10, flexWrap: "wrap" }}>
                <Button onClick={createQuestionManual} disabled={busy || !evalId.trim()}>
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

              <div style={{ marginTop: 10, fontSize: 12, color: "#64748B" }}>
                Tip: after creating, the list refreshes automatically.
              </div>
            </div>

            <div style={miniPanelStyle()}>
              <div style={miniTitleStyle()}>Questions Loaded</div>

              {qCount === 0 ? (
                <div style={{ fontSize: 13, color: "#64748B" }}>
                  Click <b>Load Questions</b> to view questions for this questionnaire.
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
                      {questions.map((q) => {
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

    // ✅ NEW: Generate Questions (AI) screen — FILE upload + preview + Add Selected
    if (task === "generate_questions_ai") {
      const { t, v } = deriveQuestionnaireTarget();
      const draftCount = aiDrafts?.length || 0;
      const selectedCount = (aiDrafts || []).filter((d) => aiSelectedIds?.[d._local_id]).length;

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
          </div>

          <div style={{ marginTop: 14, display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
            <div style={miniPanelStyle()}>
              <div style={miniTitleStyle()}>1) Upload Source File</div>

              <Field
                label="File"
                hint="Supported now: .txt / .md (client-side). Optional backend support: .pdf / .docx via multipart upload."
              >
                <input
                  type="file"
                  accept=".txt,.md,.markdown,.pdf,.doc,.docx"
                  onChange={(e) => handleAiFilePick(e.target.files?.[0] || null)}
                  style={inputStyle()}
                />
              </Field>

              {aiFileName ? (
                <div style={{ marginTop: 10, display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
                  <Badge tone="green">Selected: {aiFileName}</Badge>
                  <Button
                    variant="soft"
                    disabled={busy}
                    onClick={() => handleAiFilePick(null)}
                    title="Clear selected file"
                  >
                    Clear
                  </Button>
                </div>
              ) : (
                <div style={{ marginTop: 10, fontSize: 13, color: "#64748B" }}>
                  Upload a policy/framework document to generate questions.
                </div>
              )}

              {aiFileTextPreview ? (
                <div style={{ marginTop: 12 }}>
                  <Field label="Preview (first ~3000 chars)">
                    <textarea value={aiFileTextPreview} readOnly style={textareaStyle(160)} />
                  </Field>
                </div>
              ) : null}
            </div>

            <div style={miniPanelStyle()}>
              <div style={miniTitleStyle()}>2) Generate Settings</div>

              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                <Field label="Number of questions">
                  <input
                    inputMode="numeric"
                    value={aiNQuestions}
                    onChange={(e) => setAiNQuestions(e.target.value)}
                    style={inputStyle()}
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
                  />
                </Field>
              </div>

              <div style={{ marginTop: 12, display: "flex", gap: 10, flexWrap: "wrap" }}>
                <Button onClick={generateQuestionsFromFile} disabled={busy || !evalId.trim() || !aiFile}>
                  {busy ? "Generating..." : "Generate Drafts"}
                </Button>
                <Button
                  variant="secondary"
                  disabled={busy}
                  onClick={() => {
                    // quick demo: set defaults good for a wow demo
                    setAiNQuestions("10");
                    setAiAllowedTypes(["rating", "comment"]);
                    setAiDimensionHints("Board Composition, Risk Oversight, Strategy & Performance, Controls & Compliance");
                  }}
                >
                  Use Demo Defaults →
                </Button>
              </div>

              <div style={{ marginTop: 10, fontSize: 12, color: "#64748B" }}>
                Tip: Generate drafts first; then edit/select; then add to questionnaire.
              </div>
            </div>
          </div>

          <div style={{ marginTop: 14 }}>
            <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
              <Badge tone="gray">Drafts: {draftCount}</Badge>
              <Badge tone="gray">Selected: {selectedCount}</Badge>

              <Button variant="soft" disabled={busy || draftCount === 0} onClick={() => selectAllDrafts(true)}>
                Select all
              </Button>
              <Button variant="soft" disabled={busy || draftCount === 0} onClick={() => selectAllDrafts(false)}>
                Select none
              </Button>

              <Button
                variant="primary"
                disabled={busy || selectedCount === 0}
                onClick={addSelectedDraftsToQuestionnaire}
                title="Bulk insert selected questions into the questionnaire"
              >
                {busy ? "Adding..." : "Add Selected to Questionnaire"}
              </Button>

              <Button variant="secondary" disabled={busy} onClick={() => setTask("list_questions")}>
                View Questions →
              </Button>
            </div>

            {aiAddStatus ? (
              <div style={{ marginTop: 10, display: "flex", gap: 10, flexWrap: "wrap" }}>
                <Badge tone="green">Created: {aiAddStatus.created}</Badge>
                <Badge tone="amber">Skipped existing: {aiAddStatus.skipped}</Badge>
                {aiAddStatus.errors?.length ? (
                  <Badge tone="red">Errors: {aiAddStatus.errors.length}</Badge>
                ) : (
                  <Badge tone="gray">Errors: 0</Badge>
                )}
              </div>
            ) : null}

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
                        No drafts yet. Upload a file and click <b>Generate Drafts</b>.
                      </td>
                    </tr>
                  ) : (
                    aiDrafts.map((d) => {
                      const sel = !!aiSelectedIds?.[d._local_id];
                      return (
                        <tr key={d._local_id} style={{ borderBottom: "1px solid #F1F5F9" }}>
                          <td style={tdStyle()}>
                            <input type="checkbox" checked={sel} onChange={() => toggleDraftSelected(d._local_id)} />
                          </td>

                          <td style={tdStyle()}>
                            <input
                              value={d.dimension}
                              onChange={(e) => setDraftField(d._local_id, "dimension", e.target.value)}
                              style={inputStyle()}
                            />
                          </td>

                          <td style={tdStyle()}>
                            <select
                              value={d.answer_type}
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
                              onChange={(e) => setDraftField(d._local_id, "weight", e.target.value)}
                              style={inputStyle()}
                            />
                          </td>

                          <td style={tdStyle()}>
                            <select
                              value={d.active ? "1" : "0"}
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

    // Seed demo responses
    if (task === "seed_demo_responses") {
      return (
        <Card
          title="Seed Demo Responses"
          subtitle="Creates demo participants + responses so analytics and reports are based on real DB rows."
          right={<Badge tone="blue">Consultant</Badge>}
        >
          {focus}

          <div style={{ marginTop: 14, display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 12 }}>
            <Field label="Invited">
              <input inputMode="numeric" value={invited} onChange={(e) => setInvited(e.target.value)} style={inputStyle()} />
            </Field>
            <Field label="Responded">
              <input inputMode="numeric" value={responded} onChange={(e) => setResponded(e.target.value)} style={inputStyle()} />
            </Field>
            <Field label="Random Seed">
              <input inputMode="numeric" value={randomSeed} onChange={(e) => setRandomSeed(e.target.value)} style={inputStyle()} />
            </Field>
          </div>

          <div style={{ marginTop: 10 }}>
            <Badge tone="gray">
              Target questionnaire: {String(selectedTemplate || "DEFAULT")} v{String(selectedVersion || "1")}
            </Badge>
          </div>

          <div style={{ marginTop: 14, display: "flex", gap: 10, flexWrap: "wrap" }}>
            <Button onClick={seedDemoResponses} disabled={busy || !evalId.trim()}>
              {busy ? "Seeding..." : "Seed Demo Responses"}
            </Button>
            <Button onClick={() => setTask("generate_report")} disabled={busy} variant="secondary">
              Next: Generate Report →
            </Button>
            <Button onClick={() => setTask("list_evaluations")} disabled={busy} variant="soft">
              Back to Evaluations →
            </Button>
          </div>
        </Card>
      );
    }

    // Generate report
    return (
      <Card
        title="Generate Report"
        subtitle="One click: generate a new report, then fetch the latest report for the evaluation."
        right={<Badge tone="blue">Consultant</Badge>}
      >
        {focus}

        <div style={{ marginTop: 14, display: "flex", gap: 10, flexWrap: "wrap" }}>
          <Button onClick={generateAndLoadLatestReport} disabled={busy || !evalId.trim()} variant="primary">
            {busy ? "Working..." : "Generate + Load Latest"}
          </Button>
          <Button onClick={() => setTask("list_participants")} disabled={busy} variant="secondary">
            View Participants
          </Button>
          <Button onClick={() => setTask("list_questions")} disabled={busy} variant="secondary">
            View Questions
          </Button>
          <Button onClick={() => setTask("list_evaluations")} disabled={busy} variant="soft">
            Back to Evaluations →
          </Button>
        </div>

        {latestSummary?.exec ? (
          <div style={{ marginTop: 16 }}>
            <div style={{ padding: 14, borderRadius: 14, border: "1px solid #E5E7EB", background: "#F8FAFC" }}>
              <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
                <Badge tone="green">Latest Report</Badge>
                <Badge tone="gray">Report ID: {result?.data?.report_id}</Badge>
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

  // Task label (for top bar)
  const taskLabel = useMemo(() => {
    for (const g of CONSULTANT_TASK_GROUPS) {
      const found = g.items.find((x) => x.key === task);
      if (found) return found.label;
    }
    return "Task";
  }, [task]);

  return (
    <div style={pageShellStyle()}>
      {/* Sidebar */}
      <aside style={sidebarStyle()}>
        <div style={{ padding: "18px 16px" }}>
          <div style={{ fontSize: 14, fontWeight: 900, color: "white", letterSpacing: 0.2 }}>
            C&amp;W Board Eval
          </div>
          <div style={{ marginTop: 4, fontSize: 12, color: "rgba(255,255,255,0.75)" }}>
            React UI • Phase 1 (Consultant)
          </div>
        </div>

        <div style={{ padding: "0 10px 14px" }}>
          {PAGES.map((p) => (
            <button
              key={p.key}
              onClick={() => {
                setPage(p.key);
                setTask("list_evaluations");
              }}
              style={navItemStyle(page === p.key)}
            >
              {p.label}
            </button>
          ))}
        </div>

        {/* ✅ Grouped Consultant tasks */}
        <div style={{ padding: "0 10px 16px" }}>
          <div style={{ margin: "8px 8px 10px", fontSize: 12, fontWeight: 900, color: "rgba(255,255,255,0.75)" }}>
            Consultant tasks
          </div>

          {CONSULTANT_TASK_GROUPS.map((grp) => (
            <div key={grp.group} style={{ marginBottom: 10 }}>
              <div style={groupHeaderStyle()}>{grp.group}</div>
              {grp.items.map((t) => (
                <button
                  key={t.key}
                  onClick={() => setTask(t.key)}
                  style={subNavItemStyle(task === t.key)}
                >
                  {t.label}
                </button>
              ))}
            </div>
          ))}
        </div>

        <div style={{ marginTop: "auto", padding: 14 }}>
          <div style={{ fontSize: 12, color: "rgba(255,255,255,0.75)" }}>API</div>
          <div style={{ fontSize: 12, color: "white", fontWeight: 800, wordBreak: "break-all" }}>
            {API_BASE}
          </div>
        </div>
      </aside>

      {/* Main */}
      <main style={mainStyle()}>
        <div style={topbarStyle()}>
          <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
            <div style={{ fontSize: 18, fontWeight: 900, color: "#0F172A" }}>
              Consultant Workspace
            </div>
            <Badge tone="gray">Evaluation in focus: {evalId || "—"}</Badge>
            <Badge tone="gray">
              Questionnaire: {String(selectedTemplate || "DEFAULT")} v{String(selectedVersion || "1")}
            </Badge>
            <Badge tone="blue">{taskLabel}</Badge>
          </div>
        </div>

        {error ? (
          <div
            style={{
              marginTop: 14,
              padding: 14,
              borderRadius: 14,
              border: "1px solid #FCA5A5",
              background: "#FEF2F2",
              color: "#7F1D1D",
              fontWeight: 700,
              whiteSpace: "pre-wrap",
            }}
          >
            {error}
          </div>
        ) : null}

        <div style={{ marginTop: 14 }}>{renderConsultantTask()}</div>

        {result ? (
          <div style={{ marginTop: 14 }}>
            <Card
              title="Raw Response"
              subtitle="Useful during demos and troubleshooting."
              right={<Badge tone="gray">{result?.action}</Badge>}
            >
              <pre
                style={{
                  background: "#0B1220",
                  color: "#E5E7EB",
                  padding: 14,
                  borderRadius: 12,
                  overflow: "auto",
                  fontSize: 12,
                  lineHeight: 1.5,
                }}
              >
                {pretty(result)}
              </pre>
            </Card>
          </div>
        ) : null}
      </main>
    </div>
  );
}
