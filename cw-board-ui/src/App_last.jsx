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

async function fetchWithFallback(urls, options) {
  let lastErr = null;

  for (const url of urls) {
    try {
      const res = await fetch(url, options);

      // If route not found, try next candidate
      if (res.status === 404) {
        lastErr = new Error(`404 Not Found: ${url}`);
        continue;
      }

      const data = await safeJsonOrText(res);
      if (!res.ok) {
        throw new Error(typeof data === "string" ? data : pretty(data));
      }

      return { url, data };
    } catch (e) {
      lastErr = e;
      // For network errors etc, stop early (optional); but we can continue as well:
      // continue;
    }
  }

  throw lastErr || new Error("All fallback URLs failed.");
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


function groupTone(group) {
  const g = String(group || "").toLowerCase();

  // Slightly stronger separation + consistent alpha ramps
  if (g.includes("evaluation")) {
    return {
      bg: "rgba(59,130,246,0.18)",
      fg: "rgba(219,234,254,1)",
      bd: "rgba(59,130,246,0.30)",
      accent: "rgba(59,130,246,0.85)",
    }; // blue
  }
  if (g.includes("questionnaire")) {
    return {
      bg: "rgba(168,85,247,0.18)",
      fg: "rgba(243,232,255,1)",
      bd: "rgba(168,85,247,0.30)",
      accent: "rgba(168,85,247,0.85)",
    }; // purple
  }
  if (g.includes("participant")) {
    return {
      bg: "rgba(34,197,94,0.16)",
      fg: "rgba(220,252,231,1)",
      bd: "rgba(34,197,94,0.28)",
      accent: "rgba(34,197,94,0.85)",
    }; // green
  }
  if (g.includes("analysis")) {
    return {
      bg: "rgba(245,158,11,0.16)",
      fg: "rgba(255,237,213,1)",
      bd: "rgba(245,158,11,0.28)",
      accent: "rgba(245,158,11,0.85)",
    }; // amber
  }

  return {
    bg: "rgba(255,255,255,0.06)",
    fg: "rgba(255,255,255,0.80)",
    bd: "rgba(255,255,255,0.14)",
    accent: "rgba(255,255,255,0.55)",
  };
}

function groupHeaderStyleTone(group) {
  const t = groupTone(group);

  return {
    margin: "12px 8px 10px",
    padding: "8px 10px 8px 12px",
    borderRadius: 10,
    fontSize: 12,
    fontWeight: 900,
    letterSpacing: 0.6,
    textTransform: "uppercase",

    // main styling
    background: t.bg,
    color: t.fg,
    border: `1px solid ${t.bd}`,

    // ✅ new: left accent bar (fast cognitive grouping)
    borderLeft: `6px solid ${t.accent}`,

    // ✅ new: subtle depth (doesn't fight the buttons)
    boxShadow: "0 1px 0 rgba(0,0,0,0.25)",
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

  const [openGroups, setOpenGroups] = useState(() => ({
  Evaluations: true,
  Questionnaire: true,
  Participants: false,
  Analysis: false,
  }));

  const [showDebug, setShowDebug] = useState(false);
  const [focusOpen, setFocusOpen] = useState(false);
  const [questionnaireSavedAt, setQuestionnaireSavedAt] = useState("");
  const [questionnaireSavedForEvalId, setQuestionnaireSavedForEvalId] = useState("");


  const [wfParticipantsCount, setWfParticipantsCount] = useState(0);
  const [wfQuestionsCount, setWfQuestionsCount] = useState(0);
  const [wfReportReady, setWfReportReady] = useState(false);
  const [wfReportAt, setWfReportAt] = useState("");

  const [lastCreatedEvalId, setLastCreatedEvalId] = useState("");





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


function lockReason(actionKey) {
  const hasEval = !!String(evalId || "").trim();

  const hasQuestionnaireSelected =
    !!String(selectedTemplate || "").trim() && !!String(selectedVersion || "").trim();

  const hasQuestionnaireSaved =
    String(questionnaireSavedForEvalId || "").trim() === String(evalId || "").trim();

  const hasQuestions = Array.isArray(questions) && questions.length > 0;

  const participantsCount =
    typeof wfParticipantsCount !== "undefined" && typeof wfParticipantsCount === "number"
      ? wfParticipantsCount
      : 0;

  const hasParticipants = participantsCount > 0;

  if (actionKey !== "evaluation" && !hasEval) return "Select an evaluation first.";

  if (["questionnaire", "list_questions", "manual_questions", "ai_questions"].includes(actionKey)) {
    if (!hasQuestionnaireSelected) return "Select a questionnaire (template/version) first.";
    return "";
  }

  if (actionKey === "seed") {
    if (!hasParticipants) return "Invite participants first.";
    if (!hasQuestions) return "Add questions first.";
    return "";
  }

  if (actionKey === "report") {
    if (!hasQuestionnaireSelected) return "Select a questionnaire (template/version) first.";
    if (!hasQuestionnaireSaved) return "Save the questionnaire for this evaluation first.";
    if (!hasQuestions) return "Add questions first.";
    return "";
  }
  if (actionKey === "participants") {
  if (!hasEval) return "Select an evaluation first.";
  return "";
}


  return "";
}



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

    // ✅ evaluations.py returns `instrument`
    const inst = data?.instrument || {};
    syncQuestionnaireToUi(inst.template_code || "DEFAULT", inst.version ?? 1);

    setQuestionnaireLoadedAt(new Date().toLocaleString());
    setResult({ action: "load_evaluation_instrument", data });
  } catch (e) {
    setError(e?.message || String(e));
  } finally {
    setBusy(false);
  }
}




  // ✅ Set questionnaire for evaluation (PATCH)...Questionaire is same as Instrument
  async function setEvaluationQuestionnaire() {
  beginAction();
  try {
    if (!String(evalId || "").trim()) throw new Error("Evaluation ID is required.");

    const payload = {
      template_code: String(selectedTemplate || "DEFAULT").trim(),
      version: clampInt(selectedVersion, 1, 1, 10_000),
    };

    // ✅ evaluations.py defines /instrument
    const res = await fetch(
      `${API_BASE}/api/v1/evaluations/${encodeURIComponent(evalId)}/instrument`,
      {
        method: "PATCH",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify(payload),
      }
    );

    const data = await safeJsonOrText(res);
    if (!res.ok) throw new Error(typeof data === "string" ? data : pretty(data));

    // ✅ success: mark questionnaire saved for this evaluation


    const inst = data?.instrument || payload;
    syncQuestionnaireToUi(inst.template_code || payload.template_code, inst.version ?? payload.version);

    setQuestionnaireSavedForEvalId(String(evalId || "").trim());
    setQuestionnaireSavedAt(new Date().toLocaleString());



    setQuestionnaireLoadedAt(new Date().toLocaleString());
    setResult({ action: "set_evaluation_instrument", data });


  } catch (e) {
    setError(e?.message || String(e));
  } finally {
    setBusy(false);
  }
}

   /* --------------------------
   ✅ Workflow Progress Bar
-------------------------- */

function taskToStepIndex(t) {
  const key = String(t || "");

  // 0) Evaluation
  if (key === "list_evaluations" || key === "create_eval") return 0;

  // 1) Questionnaire
  if (key === "select_questionnaire") return 1;

  // 2) Participants
  if (key === "invite_participants" || key === "list_participants") return 2;

  // 3) Questions
  if (
    key === "seed_questions" ||
    key === "list_questions" ||
    key === "create_questions_manual" ||
    key === "generate_questions_ai"
  )
    return 3;

  // 4) Analysis / Report
  if (key === "seed_demo_responses" || key === "generate_report") return 4;

  // fallback
  return 0;
}

function flowTone(stepKey) {
  // subtle but distinct (works on white background)
  if (stepKey === "evaluation") return { bg: "#EFF6FF", fg: "#1D4ED8", bd: "#BFDBFE" }; // blue
  if (stepKey === "questionnaire") return { bg: "#F5F3FF", fg: "#6D28D9", bd: "#DDD6FE" }; // purple
  if (stepKey === "participants") return { bg: "#ECFDF5", fg: "#047857", bd: "#A7F3D0" }; // green
  if (stepKey === "questions") return { bg: "#FFFBEB", fg: "#B45309", bd: "#FDE68A" }; // amber
  if (stepKey === "report") return { bg: "#F1F5F9", fg: "#0F172A", bd: "#E2E8F0" }; // slate
  return { bg: "#F1F5F9", fg: "#0F172A", bd: "#E2E8F0" };
}

function stepStatus(stepIndex, currentIndex, done) {
  if (done) return "done";
  if (stepIndex === currentIndex) return "current";
  if (stepIndex < currentIndex) return "done"; // task moved ahead even if not strictly "done"
  return "todo";
}


function computeNextActionKey() {
  const hasEval = !!String(evalId || "").trim();

  const hasQuestionnaire =
    !!String(selectedTemplate || "").trim() && !!String(selectedVersion || "").trim();

  //const participantsCount =
    //(typeof wfParticipantsCount === "number" ? wfParticipantsCount : 0) ||
    //(result?.action === "list_participants" ? Number(result?.data?.count || 0) : 0) ||
    //(result?.action === "invite_participants" ? 1 : 0);

  const participantsCount =
  (typeof wfParticipantsCount === "number" ? wfParticipantsCount : 0) ||
  (result?.action === "list_participants" ? Number(result?.data?.count || 0) : 0);


  const hasParticipants = participantsCount > 0;

  const questionsCount =
    (typeof wfQuestionsCount === "number" ? wfQuestionsCount : 0) ||
    (Array.isArray(questions) ? questions.length : 0);

  const hasQuestions = questionsCount > 0;

  const hasReport =
    (typeof wfReportReady === "boolean" ? wfReportReady : false) ||
    result?.action === "generate_then_get_latest" ||
    result?.action === "get_latest_report" ||
    result?.action === "generate_report" ||
    !!latestSummary?.exec;

  if (!hasEval) return "list_evaluations";
  if (!hasQuestionnaire) return "select_questionnaire";
  if (!hasParticipants) return "invite_participants";
  if (!hasQuestions) return "list_questions";
  if (!hasReport) return "generate_report";
  return "generate_report"; // end state
}

function nextActionMeta() {
  const key = computeNextActionKey();
  const map = {
    list_evaluations: { label: "Next: Choose Evaluation →", toTask: "list_evaluations", tone: "primary" },
    select_questionnaire: { label: "Next: Select Questionnaire →", toTask: "select_questionnaire", tone: "primary" },
    invite_participants: { label: "Next: Invite Participants →", toTask: "invite_participants", tone: "primary" },
    list_questions: { label: "Next: Add / View Questions →", toTask: "list_questions", tone: "primary" },
    generate_report: { label: "Next: Generate Report →", toTask: "generate_report", tone: "primary" },
  };
  return map[key] || map.list_evaluations;
}
function renderNextActionBar(opts = {}) {
  const meta = nextActionMeta();

  // Next button label + destination
  const label = opts.nextLabel || opts.label || meta.label;
  const toTask = opts.toTask || meta.toTask;

  // Optional lock reasons (empty string means “no lock”)
  const nextReason = opts.nextReason || "";
  const refreshReason = opts.refreshReason || "";
  const backReason = opts.backReason || "";

  const hasEval = !!String(evalId || "").trim();

  // Keep your existing rule, but allow lockReason to add extra gating
  const nextDisabled =
    busy ||
    !!nextReason ||
    (toTask !== "list_evaluations" && !hasEval) ||
    !!opts.nextDisabled; // optional manual override

  const refreshDisabled = busy || !!refreshReason || !!opts.refreshDisabled;
  const backDisabled = busy || !!backReason || !!opts.backDisabled;

  // Support custom Next behavior
  const handleNext = () => {
    if (typeof opts.onNext === "function") return opts.onNext();
    return setTask(toTask);
  };

  return (
    <div style={{ marginTop: 14, display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
      <Button
        onClick={handleNext}
        disabled={nextDisabled}
        title={nextReason || label}
        variant="primary"
      >
        {label}
      </Button>

      {opts.onRefresh ? (
        <Button
          onClick={opts.onRefresh}
          disabled={refreshDisabled}
          title={refreshReason || "Refresh"}
          variant="soft"
        >
          Refresh
        </Button>
      ) : null}

      {opts.backTo ? (
        <Button
          onClick={() => setTask(opts.backTo)}
          disabled={backDisabled}
          title={backReason || "Back"}
          variant="secondary"
        >
          Back
        </Button>
      ) : null}

      {opts.extra ? opts.extra : null}
    </div>
  );
}



  // ✅ Auto-load questionnaire whenever evalId changes
  useEffect(() => {
    if (String(evalId || "").trim()) {
      loadEvaluationQuestionnaire();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [evalId]);

  useEffect(() => {
  if (!result?.action) return;

  const a = String(result.action || "");
  const d = result.data;

  // --- Participants ---
  // list_participants returns { count, items: [...] }
  if (a === "list_participants") {
    const c = Number(d?.count || 0);
    if (Number.isFinite(c)) setWfParticipantsCount(c);
  }

  // invite_participants often returns created/updated list or summary
  if (a === "invite_participants") {
    // Try common shapes safely
    const invitedItems = Array.isArray(d?.items) ? d.items.length : 0;
    const invitedCount = Number(d?.count || d?.invited_count || invitedItems || 0);

     const delta =
    Number(d?.invited_count || d?.count || 0) ||
    (Array.isArray(d?.items) ? d.items.length : 0);

    // We don't want to accidentally set 0; only bump upward
    if (Number.isFinite(invitedCount) && invitedCount > 0) {
      setWfParticipantsCount((prev) => Math.max(prev, invitedCount));
    } else {
      // If backend doesn't return counts, we still know "at least 1 invite happened"
      setWfParticipantsCount((prev) => Math.max(prev, 1));
    }
    // ✅ then always re-fetch the real total (handles idempotency, duplicates, etc.)
    listParticipants(); // make sure this updates result.action to "list_participants"

  }

  // --- Questions ---
  // list_questions returns { count, items: [...] } (or sometimes just items)
  if (a === "list_questions") {
    const itemsLen = Array.isArray(d?.items) ? d.items.length : 0;
    const c = Number(d?.count || itemsLen || 0);
    if (Number.isFinite(c)) setWfQuestionsCount(c);
  }

  // create_question / add_question_manual etc.
  if (a === "add_question_manual" || a === "create_question") {
    const created = !!d?.created;
    if (created) setWfQuestionsCount((prev) => Math.max(prev + 1, 1));
    // if "already exists" we don't change count
  }

  // bulk create / seed / AI generate — assume questions exist even if we don't have count
  if (
    a === "bulk_create_questions" ||
    a === "seed_questions" ||
    a === "generate_questions_ai" ||
    a === "questionnaire_generate"
  ) {
    // Try to infer a count if present
    const c = Number(d?.created_count || d?.count || d?.added || 0);
    if (Number.isFinite(c) && c > 0) setWfQuestionsCount((prev) => Math.max(prev, c));
    else setWfQuestionsCount((prev) => Math.max(prev, 1));
  }

  // toggle active doesn't change count
  // update_question doesn't change count

  // --- Report ---
  if (
    a === "generate_report" ||
    a === "generate_then_get_latest" ||
    a === "get_latest_report" ||
    a === "get_report_by_id"
  ) {
    // Mark ready if we got a report id or any summary content
    const reportId = d?.report_id || d?.id || d?.latest?.report_id;
    const hasExec = !!d?.exec || !!latestSummary?.exec;

    if (reportId || hasExec) {
      setWfReportReady(true);
      const now = new Date().toLocaleString();
      setWfReportAt(now);
    }
  }
}, [result]); // eslint-disable-line react-hooks/exhaustive-deps


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

    // ✅ store result (optional, but keep)
    setResult({ action: "create_evaluation", data });

    // ✅ single source of truth (stable even if listEvaluations overwrites `result`)
    if (data?.evaluation_id) {
      const id = String(data.evaluation_id).trim();
      setEvalId(id);
      setLastCreatedEvalId(id);
    }

    try {
      await listEvaluations(); // may overwrite result; no longer a problem
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

      //setResult({ action: "seed_default_questionnaire", data });
      setResult({ action: "seed_questions", data });

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

    //setResult({ action: "view_questions", data });
    setResult({ action: "list_questions", data });

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

    if (!String(evalId || "").trim()) throw new Error("Evaluation ID is required.");

    const t = String(selectedTemplate || templateCode || "DEFAULT").trim();
    const v = clampInt(selectedVersion || version, 1, 1, 10_000);

    if (!t) throw new Error("Template Code is required.");
    if (!v) throw new Error("Version is required.");
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

    // refresh questions list
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

    const updatedActive =
      typeof data?.active === "boolean" ? data.active : nextActive;

    setQuestions((prev) =>
      (prev || []).map((q) => {
        const id = q?.question_id || q?.id;
        if (String(id) !== String(qid)) return q;
        return { ...q, active: updatedActive };
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

const aiFileInputRef = useRef(null);

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
  const isTextish =
    name.endsWith(".txt") || name.endsWith(".md") || name.endsWith(".markdown");

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

    // ✅ Always multipart
    const fd = new FormData();
    fd.append("file", aiFile);
    fd.append("n_questions", String(n));
    fd.append("template_code", String(t));
    fd.append("version", String(v));
    fd.append("allowed_answer_types", JSON.stringify(allowed_answer_types));
    fd.append("dimension_hints", JSON.stringify(dimension_hints));

    const urls = [
      // optional new endpoint (if you add it later)
      `${API_BASE}/api/v1/questions/generate`,
      // current evaluation-scoped endpoint (your questions.py)
      `${API_BASE}/api/v1/evaluations/${encodeURIComponent(evalId)}/questionnaire/generate`,
    ];

    const { data } = await fetchWithFallback(urls, {
      method: "POST",
      headers: { Accept: "application/json" }, // ✅ don't set Content-Type for FormData
      body: fd,
    });

    const items = Array.isArray(data?.items) ? data.items : [];
    const drafts = items.map((x, idx) => ({
      _local_id: `${Date.now()}_${idx}`,
      dimension: x.dimension || "General",
      text: x.text || "",
      answer_type: x.answer_type || "rating",
      weight: x.weight ?? 1,
      active: x.active ?? true,
    }));

    setAiDrafts(drafts);

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

    const cleaned = selected.map((d) => ({
      dimension: String(d.dimension || "General").trim(),
      text: String(d.text || "").trim(),
      answer_type: String(d.answer_type || "rating").trim(),
      weight: clampInt(d.weight, 1, 1, 100),
      active: !!d.active,
    }));

    if (cleaned.some((x) => !x.text)) {
      throw new Error("One or more selected questions has empty text.");
    }

    const payload = { template_code: t, version: v, items: cleaned };

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

    setAiAddStatus({
      created: data?.created ?? 0,
      skipped: data?.skipped_existing ?? 0,
      errors: Array.isArray(data?.errors) ? data.errors : [],
    });

    //setResult({ action: "bulk_add_questions", data });
    setResult({ action: "bulk_create_questions", data });


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
function renderFlowBar(opts) {
  const left = opts?.left ?? null;   // can be array OR JSX
  const right = opts?.right ?? null; // can be array OR JSX
  const meta = opts?.meta ?? null;
  const marginTop = typeof opts?.marginTop === "number" ? opts.marginTop : 14;

  const renderButtons = (arr) =>
    (arr || []).map((b) => (
      <Button
        key={b.key}
        onClick={b.onClick}
        disabled={!!b.disabled}
        variant={b.variant || "secondary"}
        title={b.title}
      >
        {b.label}
      </Button>
    ));

  return (
    <div
      style={{
        marginTop,
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        gap: 12,
        flexWrap: "wrap",
      }}
    >
      <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
        {Array.isArray(left) ? renderButtons(left) : left}
        {meta ? (
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
            {meta}
          </div>
        ) : null}
      </div>

      <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
        {Array.isArray(right) ? renderButtons(right) : right}
      </div>
    </div>
  );
}


  /* --------------------------
     Focus header used across pages
  -------------------------- */
  // ✅ DROP-IN: Collapsible renderFocusHeader()


function renderFocusHeader() {
  return (
    <details
      style={{
        border: "1px solid #E5E7EB",
        background: "white",
        borderRadius: 14,
        padding: 12,
        boxShadow: "0 1px 2px rgba(0,0,0,0.04)",
      }}
    >
      {/* ✅ Collapsed header line (always visible) */}
      <summary
        style={{
          cursor: "pointer",
          listStyle: "none",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 10,
          flexWrap: "wrap",
          userSelect: "none",
        }}
      >
        <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
          <div style={{ fontWeight: 900, color: "#0F172A" }}>Focus</div>

          <Badge tone="gray">Eval: {evalId || "—"}</Badge>

          <Badge tone="gray">
            Q: {String(selectedTemplate || "DEFAULT")} v{String(selectedVersion || "1")}
          </Badge>

          {questionnaireLoadedAt ? (
            <Badge tone="gray">Loaded: {questionnaireLoadedAt}</Badge>
          ) : null}
        </div>

        <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
          <Button onClick={handlePing} disabled={busy} variant="soft">
            {busy ? "Working..." : "Ping LLM"}
          </Button>

        </div>
      </summary>


    </details>
  );
}


function renderWorkflowBar() {
      const currentIndex = taskToStepIndex(task);

      // ---- Core prerequisites
      const hasEval = !!String(evalId || "").trim();

      const hasQuestionnaire =
        !!String(selectedTemplate || "").trim() && !!String(selectedVersion || "").trim();

      // ---- Smarter progress (prefer cached workflow state, fallback to current result/arrays)

      // Participants
      const fallbackParticipantsCount =
        (result?.action === "list_participants" ? Number(result?.data?.count || 0) : 0) ||
        (result?.action === "invite_participants" ? 1 : 0);

      const participantsCount =
        typeof wfParticipantsCount === "number" && wfParticipantsCount > 0
          ? wfParticipantsCount
          : fallbackParticipantsCount;

      const hasParticipants = participantsCount > 0;

      // Questions
      const questionsCountFromState = Array.isArray(questions) ? questions.length : 0;

      const fallbackQuestionsCount =
        (result?.action === "list_questions"
          ? Number(
              result?.data?.count ||
                (Array.isArray(result?.data?.items) ? result.data.items.length : 0) ||
                0
            )
          : 0) || 0;

      const questionsCount =
        typeof wfQuestionsCount === "number" && wfQuestionsCount > 0
          ? wfQuestionsCount
          : Math.max(questionsCountFromState, fallbackQuestionsCount);

      const hasQuestions = questionsCount > 0;

      // Report
      const fallbackHasReport =
        !!latestSummary?.exec ||
        result?.action === "generate_then_get_latest" ||
        result?.action === "get_latest_report" ||
        result?.action === "generate_report";

      const hasReport =
        (typeof wfReportReady === "boolean" ? wfReportReady : false) || fallbackHasReport;

      const reportHint = hasReport ? (wfReportAt ? `Generated: ${wfReportAt}` : "Generated") : "Generate report";

      // ---- Steps
      const STEPS = [
        {
          key: "evaluation",
          label: "Evaluation",
          hint: hasEval ? `Focused: ${evalId}` : "Pick/create an evaluation",
          toTask: "list_evaluations",
          done: hasEval,
          lock: false,
        },
        {
          key: "questionnaire",
          label: "Questionnaire",
          hint: hasQuestionnaire
            ? `Using: ${String(selectedTemplate)} v${String(selectedVersion)}`
            : "Select template & version",
          toTask: "select_questionnaire",
          done: hasQuestionnaire,
          lock: !hasEval,
        },
        {
          key: "participants",
          label: "Participants",
          hint: hasParticipants ? `Count: ${participantsCount}` : "Invite / view participants",
          toTask: "invite_participants",
          done: hasParticipants,
          lock: !hasEval,
        },
        {
          key: "questions",
          label: "Questions",
          hint: hasQuestions ? `Count: ${questionsCount}` : "Seed / add / generate questions",
          toTask: "list_questions",
          done: hasQuestions,
          lock: !hasEval,
        },
        {
          key: "report",
          label: "Report",
          hint: reportHint,
          toTask: "generate_report",
          done: hasReport,
          lock: !hasEval,
        },
      ];

      // ---- Auto-suggest next step (and add a "Go →" CTA)
      const nextKey =
        !hasEval
          ? "evaluation"
          : !hasQuestionnaire
          ? "questionnaire"
          : !hasParticipants
          ? "participants"
          : !hasQuestions
          ? "questions"
          : "report";

      const nextStepObj = STEPS.find((x) => x.key === nextKey) || STEPS[0];

      const nextDisabled = !!busy || !!nextStepObj.lock;
      const nextDisabledTitle =
        nextStepObj.lock ? "Select an evaluation first." : nextStepObj.hint;

      return (
        <div
          style={{
            marginTop: 12,
            background: "white",
            border: "1px solid #E5E7EB",
            borderRadius: 14,
            padding: 12,
            boxShadow: "0 1px 2px rgba(0,0,0,0.04)",
          }}
        >
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              gap: 10,
              flexWrap: "wrap",
            }}
          >
            <div style={{ fontWeight: 900, color: "#0F172A" }}>Workflow</div>

            {/* ✅ "Next" + a single CTA button */}
            <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
              <Badge tone="gray">Next: {String(nextStepObj?.label || "—")}</Badge>

              <Button
                variant="primary"
                disabled={nextDisabled}
                onClick={() => setTask(nextStepObj.toTask)}
                title={nextDisabled ? nextDisabledTitle : `Go to ${nextStepObj.label}`}
              >
                Go →
              </Button>

              <div style={{ fontSize: 12, color: "#64748B" }}>
                Click any step to jump • Current step is highlighted
              </div>
            </div>
          </div>

          <div
            style={{
              marginTop: 10,
              display: "flex",
              alignItems: "stretch",
              gap: 10,
              flexWrap: "wrap",
            }}
          >
            {STEPS.map((s, idx) => {
              const tone = flowTone(s.key);
              const status = stepStatus(idx, currentIndex, s.done);

              const isCurrent = status === "current";
              const isDone = status === "done";

              const disabled = !!busy || !!s.lock;

              return (
                <div key={s.key} style={{ display: "flex", alignItems: "center", gap: 10 }}>
                  <button
                    onClick={() => setTask(s.toTask)}
                    disabled={disabled}
                    title={disabled && s.lock ? "Select an evaluation first." : s.hint}
                    style={{
                      borderRadius: 12,
                      border: `1px solid ${tone.bd}`,
                      background: isCurrent ? tone.bg : "white",
                      color: tone.fg,
                      padding: "10px 12px",
                      minWidth: 160,
                      textAlign: "left",
                      cursor: disabled ? "not-allowed" : "pointer",
                      opacity: disabled ? 0.6 : 1,
                      boxShadow: isCurrent ? "0 0 0 2px rgba(37,99,235,0.15)" : "none",
                    }}
                  >
                    <div
                      style={{
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "space-between",
                        gap: 10,
                      }}
                    >
                      <div style={{ fontWeight: 900, fontSize: 13 }}>
                        {isDone ? "✓ " : isCurrent ? "• " : "○ "}
                        {s.label}
                      </div>

                      <span
                        style={{
                          fontSize: 11,
                          fontWeight: 900,
                          padding: "3px 8px",
                          borderRadius: 999,
                          border: "1px solid #E5E7EB",
                          background: isDone ? "#ECFDF5" : isCurrent ? "#EEF2FF" : "#F8FAFC",
                          color: isDone ? "#065F46" : isCurrent ? "#1D4ED8" : "#64748B",
                          whiteSpace: "nowrap",
                        }}
                      >
                        {isDone ? "Done" : isCurrent ? "Current" : "Next"}
                      </span>
                    </div>

                    <div style={{ marginTop: 6, fontSize: 12, color: "#64748B", fontWeight: 700 }}>
                      {s.hint}
                    </div>
                  </button>

                  {idx < STEPS.length - 1 ? (
                    <div
                      aria-hidden
                      style={{
                        width: 18,
                        height: 2,
                        background: idx < currentIndex ? "#94A3B8" : "#E2E8F0",
                        borderRadius: 999,
                      }}
                    />
                  ) : null}
                </div>
              );
            })}
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
  // Locks
  const reasonEval = lockReason("evaluation");              // needs eval
  const reasonQuestionnaire = lockReason("questionnaire");  // needs eval + template/version

  const disabledEvalOnly = busy || !!reasonEval;

  const canInvite = !busy && !reasonEval;                      // invite needs only eval
  const canProceedToQuestions = !busy && !reasonQuestionnaire; // questions need questionnaire

  // ✅ NEW: Saved cue (persisted questionnaire/instrument)
    const savedForThisEval = String(questionnaireSavedForEvalId || "").trim() === String(evalId || "").trim();

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

      {/* Current selection */}
      <div style={{ marginTop: 10, display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
        <Badge tone="gray">Evaluation: {String(evalId || "—")}</Badge>

        <Badge tone="gray">
          Selected: {String(selectedTemplate || "—")} v{String(selectedVersion || "—")}
        </Badge>

        {/* ✅ NEW: persisted confirmation */}
        {savedForThisEval ? (
          <Badge tone="green">
            ✓ Questionnaire saved for this evaluation{questionnaireSavedAt ? ` • ${questionnaireSavedAt}` : ""}
          </Badge>
        ) : null}

        {reasonEval ? <Badge tone="amber">{reasonEval}</Badge> : null}
        {!reasonEval && reasonQuestionnaire ? <Badge tone="amber">{reasonQuestionnaire}</Badge> : null}
      </div>

      {/* Inputs */}
      <div style={{ marginTop: 14, display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
        <Field label="Template">
          <input
            value={selectedTemplate || ""}
            onChange={(e) => setSelectedTemplate(e.target.value)}
            style={inputStyle()}
            disabled={disabledEvalOnly}
            placeholder="e.g., DEFAULT"
          />
        </Field>

        <Field label="Version">
          <input
            value={selectedVersion || ""}
            onChange={(e) => setSelectedVersion(e.target.value)}
            style={inputStyle()}
            disabled={disabledEvalOnly}
            placeholder="e.g., 1"
          />
        </Field>
      </div>

      {/* Flow / navigation */}
      {renderFlowBar({
        left: [
          {
            key: "invite",
            label: "Invite Participants →",
            onClick: () => setTask("invite_participants"),
            disabled: !canInvite,
            variant: "secondary",
            title: reasonEval || "Invite board members/directors",
          },
          {
            key: "edit_questions",
            label: "Continue: Add / Edit Questions →",
            onClick: () => setTask("create_questions_manual"),
            disabled: !canProceedToQuestions,
            variant: "primary",
            title: reasonQuestionnaire || "Proceed to question authoring",
          },
        ],
        meta: (
          <span style={{ fontSize: 13, color: "#64748B" }}>
            {reasonEval ? (
              <>
                <b style={{ color: "#92400E" }}>Locked:</b> {reasonEval}
              </>
            ) : reasonQuestionnaire ? (
              <>
                <b style={{ color: "#92400E" }}>Next step locked:</b> {reasonQuestionnaire}
              </>
            ) : (
              <>Next: Add/Edit questions → (Optional) Seed demo → Generate report</>
            )}
          </span>
        ),
        right: [
          {
            key: "view_questions",
            label: "View Questions →",
            onClick: () => setTask("list_questions"),
            disabled: busy || !!lockReason("list_questions"),
            variant: "soft",
            title: lockReason("list_questions") || "View questions for this questionnaire",
          },
          {
            key: "back",
            label: "Back to Evaluations →",
            onClick: () => setTask("list_evaluations"),
            disabled: busy,
            variant: "soft",
          },
        ],
        marginTop: 14,
      })}
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

            {/* ✅ REPLACED CLUSTER WITH renderFlowBar (safe) */}
                        {/* ✅ REPLACED CLUSTER WITH renderFlowBar (safe) */}
            {renderFlowBar({
              left: (
                <>
                  <Button
                    onClick={() => setTask("invite_participants")}
                    disabled={busy || !!lockReason("participants")}
                    title={lockReason("participants") || "Invite participants"}
                    variant="primary"
                  >
                    Continue with Focus →
                  </Button>

                  <Button
                    onClick={() => setTask("select_questionnaire")}
                    disabled={busy || !!lockReason("questionnaire")}
                    title={lockReason("questionnaire") || "Select questionnaire"}
                    variant="secondary"
                  >
                    Questionnaire →
                  </Button>

                  <Button
                    onClick={() => setTask("list_questions")}
                    disabled={busy || !!lockReason("list_questions")}
                    title={lockReason("list_questions") || "View questions"}
                    variant="secondary"
                  >
                    Questions →
                  </Button>

                  <Button
                    onClick={() => setTask("generate_questions_ai")}
                    disabled={busy || !!lockReason("ai_questions")}
                    title={lockReason("ai_questions") || "Generate questions with AI"}
                    variant="highlight"
                  >
                    Generate (AI) →
                  </Button>
                </>
              ),
              right: (
                <span style={{ fontSize: 13, color: "#64748B", fontWeight: 700 }}>
                  Next: Confirm questionnaire → Invite participants → Prepare questions → Generate report
                </span>
              ),
              tone: "gray",
            })}

          </div>
        </Card>
      );
    }


    // Create evaluation
    // Create evaluation
// Create evaluation (DROP-IN with ✓ Questionnaire saved cue in Step 2)
if (task === "create_eval") {
  const canCreate = !!tenantName.trim() && !!sector.trim() && !!String(year || "").trim();

  // ✅ stable ID source (do not rely on `result.action`)
  const effectiveEvalId = String(evalId || lastCreatedEvalId || "").trim();

  // Step locks
  const reasonCreate = !canCreate ? "Tenant, Sector, and Year are required." : "";
  const reasonNeedsEval = !effectiveEvalId ? "Create an evaluation first (so an Evaluation ID exists)." : "";

  // Questionnaire inputs are only usable after eval exists
  const disableQuestionnaireSection = busy || !effectiveEvalId;

  // ✅ NEW: success cue for questionnaire save (Step 2)
  const savedForThisEval =
    String(questionnaireSavedForEvalId || "").trim() === String(effectiveEvalId || "").trim();

  return (
    <Card
      title="Create Evaluation"
      subtitle="Create an evaluation cycle (client + sector + year + regulators)."
      right={<Badge tone="blue">Consultant</Badge>}
    >
      {focus}

      {/* ---------------- Step 1: Create Evaluation ---------------- */}
      <div style={{ marginTop: 14, fontWeight: 900, color: "#0F172A" }}>Step 1 — Evaluation Details</div>

      <div style={{ marginTop: 10, display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
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
          <input inputMode="numeric" value={year} onChange={(e) => setYear(e.target.value)} style={inputStyle()} />
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

      {/* Status */}
      <div style={{ marginTop: 10, display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
        <Badge tone="gray">Evaluation in focus: {effectiveEvalId || "—"}</Badge>
        {lastCreatedEvalId ? <Badge tone="green">Created: {lastCreatedEvalId}</Badge> : null}
      </div>

      {/* Step 1 buttons */}
      <div style={{ marginTop: 14, display: "flex", gap: 10, flexWrap: "wrap" }}>
        <Button
          onClick={createEvaluation}
          disabled={busy || !canCreate}
          variant="primary"
          title={reasonCreate || "Create evaluation"}
        >
          {busy ? "Creating..." : "Create Evaluation"}
        </Button>

        <Button onClick={() => setTask("list_evaluations")} disabled={busy} variant="soft">
          Back to Evaluations →
        </Button>

        {!canCreate ? <Badge tone="amber">Locked: {reasonCreate}</Badge> : null}
      </div>

      {/* ---------------- Step 2: Questionnaire (Instrument) ---------------- */}
      <div style={{ marginTop: 18, paddingTop: 14, borderTop: "1px solid #E5E7EB" }}>
        <div style={{ fontWeight: 900, color: "#0F172A", marginBottom: 6 }}>
          Step 2 — Questionnaire (Template + Version)
        </div>

        <div style={{ marginTop: 6, color: "#64748B", fontSize: 13 }}>
          This saves the questionnaire selection to the backend for this evaluation.
        </div>

        {/* ✅ NEW: visual cue (only when saved for this evaluation) */}
        {savedForThisEval ? (
          <div style={{ marginTop: 10 }}>
            <Badge tone="green">
              ✓ Questionnaire saved for this evaluation{questionnaireSavedAt ? ` • ${questionnaireSavedAt}` : ""}
            </Badge>
          </div>
        ) : null}

        <div style={{ marginTop: 12, display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
          <Field label="Template">
            <input
              value={selectedTemplate || ""}
              onChange={(e) => {
                setSelectedTemplate(e.target.value);
                // ✅ optional: clear saved cue until saved again
                setQuestionnaireSavedForEvalId("");
                setQuestionnaireSavedAt("");
              }}
              style={inputStyle()}
              disabled={disableQuestionnaireSection}
              placeholder="e.g., DEFAULT"
            />
          </Field>

          <Field label="Version">
            <input
              value={selectedVersion || ""}
              onChange={(e) => {
                setSelectedVersion(e.target.value);
                // ✅ optional: clear saved cue until saved again
                setQuestionnaireSavedForEvalId("");
                setQuestionnaireSavedAt("");
              }}
              style={inputStyle()}
              disabled={disableQuestionnaireSection}
              placeholder="e.g., 1"
            />
          </Field>
        </div>

        <div style={{ marginTop: 12, display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
          <Button
            onClick={setEvaluationQuestionnaire}
            disabled={busy || !effectiveEvalId}
            variant="secondary"
            title={reasonNeedsEval || "Save questionnaire to backend"}
          >
            Save Questionnaire
          </Button>

          <Button
            onClick={() => setTask("invite_participants")}
            disabled={busy || !effectiveEvalId}
            variant="primary"
            title={reasonNeedsEval || "Continue to invite participants"}
          >
            Next: Invite Participants →
          </Button>

          {!effectiveEvalId ? <Badge tone="amber">Locked: {reasonNeedsEval}</Badge> : null}
        </div>
      </div>
    </Card>
  );
}



    // Invite participants
    if (task === "invite_participants") {
  const reasonEval = lockReason("evaluation"); // "" or "Select an evaluation first."
  const disabled = busy || !!reasonEval;

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

      {/* Action bar */}
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
        {/* Left: primary actions */}
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
              listParticipants();
              setTask("list_participants");
            }}
            disabled={disabled}
            title={reasonEval || "View participants"}
            variant="soft"
          >
            View Participants
          </Button>

          {/* Optional: show the reason as a hint */}
          {reasonEval ? <Badge tone="amber">{reasonEval}</Badge> : null}
        </div>

        {/* Right: navigation */}
        {renderNextActionBar({
          onRefresh: () => {
            if (disabled) return;
            listParticipants();
            setTask("list_participants");
          },
          backTo: "list_evaluations",
        })}
      </div>
    </Card>
  );
}



    // View participants
    if (task === "list_participants") {
  const total = result?.action === "list_participants" ? (result?.data?.count ?? 0) : 0;

  const respondedCount =
    result?.action === "list_participants"
      ? (result?.data?.items || []).filter((x) => String(x.status || "").toLowerCase() === "responded").length
      : 0;

  const invitedCount =
    result?.action === "list_participants"
      ? (result?.data?.items || []).filter((x) => String(x.status || "").toLowerCase() === "invited").length
      : 0;

  // ✅ Locks
  const reasonParticipants = lockReason("participants");     // needs eval
  const reasonListQuestions = lockReason("list_questions");  // needs eval + questionnaire
  const reasonAiQuestions = lockReason("ai_questions");      // needs eval + questionnaire

  return (
    <Card
      title="Participants"
      subtitle="View participants and response status for the evaluation."
      right={<Badge tone="blue">Consultant</Badge>}
    >
      {focus}

      {/* ✅ Flow bar replaces the old button cluster */}
      {renderFlowBar({
        left: [
          {
            key: "refresh",
            label: busy ? "Loading..." : "Refresh List",
            onClick: listParticipants,
            disabled: busy || !!reasonParticipants,
            title: reasonParticipants || "Load latest participants",
            variant: "primary",
          },
        ],
        meta:
          result?.action === "list_participants" ? (
            <>
              <Badge tone="gray">Total: {total}</Badge>
              <Badge tone="green">Responded: {respondedCount}</Badge>
              <Badge tone="amber">Invited: {invitedCount}</Badge>
            </>
          ) : (
            <Badge tone="gray">
              {reasonParticipants ? reasonParticipants : "Click Refresh List to load participants"}
            </Badge>
          ),
        right: [
          {
            key: "qs",
            label: "Next: View Questions →",
            onClick: () => setTask("list_questions"),
            disabled: busy || !!reasonListQuestions,
            title: reasonListQuestions || "View questions for this questionnaire",
            variant: "secondary",
          },
          {
            key: "ai",
            label: "Generate Questions (AI) →",
            onClick: () => setTask("generate_questions_ai"),
            disabled: busy || !!reasonAiQuestions,
            title: reasonAiQuestions || "Generate draft questions from a source file",
            variant: "highlight",
          },
          {
            key: "back",
            label: "Back to Evaluations →",
            onClick: () => setTask("list_evaluations"),
            disabled: busy,
            title: "Back to evaluations list",
            variant: "soft",
          },
        ],
      })}

      {result?.action === "list_participants" ? (
        <div style={{ marginTop: 14 }}>
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
                            String(p.status).toLowerCase() === "responded" ? "#E8FFF3" : "#FFF7ED",
                          color:
                            String(p.status).toLowerCase() === "responded" ? "#065F46" : "#92400E",
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
          {reasonParticipants ? (
            <>
              <b>Locked:</b> {reasonParticipants}
            </>
          ) : (
            <>
              Click <b>Refresh List</b> to load participants.
            </>
          )}
        </div>
      )}
    </Card>
  );
}


    // View Questions
    // View questions
    if (task === "list_questions") {
  const qCount = questions?.length || 0;

  const reasonLoad = lockReason("list_questions");        // requires eval + questionnaire
  const reasonManual = lockReason("manual_questions");    // requires eval + questionnaire
  const reasonAI = lockReason("ai_questions");            // requires eval + questionnaire

  return (
    <Card
      title="View Questions"
      subtitle="Lists questions for the questionnaire selected on this evaluation (template/version)."
      right={<Badge tone="blue">Consultant</Badge>}
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
            <Badge tone="gray">
              Questionnaire: {String(selectedTemplate || "DEFAULT")} v{String(selectedVersion || "1")}
            </Badge>
            <Badge tone="gray">Count: {qCount}</Badge>
            {qsListLoadedAt ? <Badge tone="gray">Loaded: {qsListLoadedAt}</Badge> : null}
            {reasonLoad ? <Badge tone="amber">{reasonLoad}</Badge> : null}
          </>
        ),
        right: [
          {
            key: "edit_questions",
            label: "Add / Edit Questions →",
            onClick: () => setTask("create_questions_manual"),
            disabled: busy || !!reasonManual,
            variant: "secondary",
            title: reasonManual || "Add/edit questions manually",
          },
          {
            key: "gen_ai",
            label: "Generate Questions (AI) →",
            onClick: () => setTask("generate_questions_ai"),
            disabled: busy || !!reasonAI,
            variant: "highlight",
            title: reasonAI || "Generate draft questions from a source file",
          },
          {
            key: "back",
            label: "Back to Evaluations →",
            onClick: () => setTask("list_evaluations"),
            disabled: busy,
            variant: "soft",
          },
        ],
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


    // Add / Edit Questions (manual)
    if (task === "create_questions_manual") {
  const qCount = questions?.length || 0;

  const reasonManual = lockReason("manual_questions");
  const reasonAI = lockReason("ai_questions");
  const reasonSeed = lockReason("seed");

  return (
    <Card
      title="Add / Edit Questions"
      subtitle="Creates questions in the evaluation’s selected questionnaire. Toggle Active without deleting."
      right={<Badge tone="blue">Consultant</Badge>}
    >
      {focus}

      {/* ✅ Top bar: one clean place for navigation + key actions */}
      {renderFlowBar({
        left: [
          {
            key: "load_questions",
            label: busy ? "Loading..." : "Load Questions",
            onClick: listQuestionsManual,
            disabled: busy || !!reasonManual,
            variant: "primary",
            title: reasonManual || "Load questions for the focused evaluation/questionnaire",
          },
          {
            key: "view_table",
            label: "View as Table →",
            onClick: () => setTask("list_questions"),
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
            {reasonManual ? <Badge tone="amber">{reasonManual}</Badge> : null}
          </>
        ),
        right: [
          {
            key: "gen_ai",
            label: "Generate (AI) →",
            onClick: () => setTask("generate_questions_ai"),
            disabled: busy || !!reasonAI,
            variant: "highlight",
            title: reasonAI || "Use AI helper to draft questions",
          },
          {
            key: "next_seed",
            label: "Next: Seed Demo Responses →",
            onClick: () => setTask("seed_demo_responses"),
            disabled: busy || !!reasonSeed,
            variant: "secondary",
            title: reasonSeed || "Seed demo participants + responses (for report testing)",
          },
          {
            key: "back",
            label: "Back →",
            onClick: () => setTask("list_evaluations"),
            disabled: busy,
            variant: "soft",
          },
        ],
        marginTop: 10,
      })}

      {/* ✅ Main content: two panels */}
      <div style={{ marginTop: 16, display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
        {/* Left: New question form */}
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
              <select
                value={qActive ? "1" : "0"}
                onChange={(e) => setQActive(e.target.value === "1")}
                style={inputStyle()}
              >
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

          {/* ✅ Form actions */}
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

          {reasonManual ? (
            <div style={{ marginTop: 10, fontSize: 12, color: "#92400E", fontWeight: 700 }}>
              Locked: {reasonManual}
            </div>
          ) : (
            <div style={{ marginTop: 10, fontSize: 12, color: "#64748B" }}>
              Tip: after creating, the list refreshes automatically.
            </div>
          )}
        </div>

        {/* Right: Loaded questions list */}
        <div style={miniPanelStyle()}>
          <div style={miniTitleStyle()}>Questions Loaded</div>

          {qCount === 0 ? (
            <div style={{ fontSize: 13, color: "#64748B" }}>
              {reasonManual ? (
                <>
                  <b>Locked:</b> {reasonManual}
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

      {/* ✅ Bottom bar: next step + back */}
      {renderFlowBar({
        left: [
          {
            key: "next_seed_bottom",
            label: "Next: Seed Demo Responses →",
            onClick: () => setTask("seed_demo_responses"),
            disabled: busy || !!reasonSeed,
            variant: "primary",
            title: reasonSeed || "Move to seeding demo responses (for report testing).",
          },
        ],
        meta: (
          <span style={{ fontSize: 13, color: "#64748B" }}>
            {reasonSeed ? (
              <>
                <b style={{ color: "#92400E" }}>Locked:</b> {reasonSeed}
              </>
            ) : (
              <>
                Next step is usually <b>Seed Demo Responses</b> (for report testing) or go back to <b>View Questions</b>.
              </>
            )}
          </span>
        ),
        right: [
          {
            key: "view_table_bottom",
            label: "View Questions →",
            onClick: () => setTask("list_questions"),
            disabled: busy,
            variant: "secondary",
          },
          {
            key: "back_bottom",
            label: "Back →",
            onClick: () => setTask("list_evaluations"),
            disabled: busy,
            variant: "soft",
          },
        ],
        marginTop: 12,
      })}
    </Card>
  );
}



    // ✅ NEW: Generate Questions (AI) screen — FILE upload + preview + Add Selected
   if (task === "generate_questions_ai") {
  const { t, v } = deriveQuestionnaireTarget();
  const draftCount = aiDrafts?.length || 0;
  const selectedCount = (aiDrafts || []).filter((d) => aiSelectedIds?.[d._local_id]).length;

  // ✅ Locks
  const reasonAI = lockReason("ai_questions");        // requires eval + questionnaire
  const reasonListQs = lockReason("list_questions");  // requires eval + questionnaire

  // Extra: file requirement (only for generation)
  const reasonFile = !reasonAI && !aiFile ? "Choose a file first." : "";


  // Convenience flags
  const disabledAI = busy || !!reasonAI;
  const disabledGenerate = busy || !!reasonAI || !!reasonFile;
  const disabledAdd = busy || !!reasonAI || draftCount === 0 || selectedCount === 0;

  const disabledViewQs = busy || !!reasonListQs;

  return (
    <Card
      title="Generate Questions (AI)"
      subtitle="Upload a file and generate draft questions. Review, edit, select, then add to the questionnaire."
      right={<Badge tone="purple">AI</Badge>}
    >
      {focus}

      {/* ✅ Compact target line */}
      <div style={{ marginTop: 10, display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
        <Badge tone="gray">
          Target questionnaire: {String(t)} v{String(v)}
        </Badge>
        {aiGeneratedAt ? <Badge tone="gray">Generated: {aiGeneratedAt}</Badge> : null}
        {reasonAI ? <Badge tone="amber">{reasonAI}</Badge> : null}
      </div>

      {/* ✅ 2-panel layout stays (upload + settings) */}
      <div style={{ marginTop: 14, display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
        {/* ---------- Panel 1: File upload ---------- */}
        <div style={miniPanelStyle()}>
          <div style={miniTitleStyle()}>1) Upload Source File</div>

          <Field
            label="File"
            hint="Supported now: .txt / .md (client-side). Optional backend: .pdf / .docx via multipart upload."
          >
            <input
              ref={aiFileInputRef}
              type="file"
              accept=".txt,.md,.markdown,.pdf,.doc,.docx"
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

        {/* ---------- Panel 2: Settings ---------- */}
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
            <Field
              label="Dimension hints (comma-separated)"
              hint="Optional: helps AI map questions into your preferred dimensions"
            >
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

          {/* ✅ Generate actions */}
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

      {/* ✅ Single clean action strip for drafts */}
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
                <Badge tone={aiAddStatus.errors?.length ? "red" : "gray"}>
                  Errors: {aiAddStatus.errors?.length || 0}
                </Badge>
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
          {
            key: "view_questions",
            label: "View Questions →",
            onClick: () => setTask("list_questions"),
            disabled: disabledViewQs,
            title: reasonListQs || "View saved questions",
            variant: "secondary",
          },
        ],
        marginTop: 14,
      })}

      {/* Drafts table */}
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



    // Seed demo responses
    if (task === "seed_demo_responses") {
  const reasonSeed = lockReason("seed");        // needs eval + participants + questions
  const reasonEval = lockReason("evaluation");  // eval only

  // Optional: manual_questions lock for "Back: Questions"
  const reasonManual = lockReason("manual_questions");

  return (
    <Card
      title="Seed Demo Responses"
      subtitle="Creates demo participants + responses so analytics and reports are based on real DB rows."
      right={<Badge tone="blue">Consultant</Badge>}
    >
      {/* Focus header */}
      <div style={{ marginTop: 6 }}>{focus}</div>

      {/* Inputs */}
      <div style={{ marginTop: 14, display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 12 }}>
        <Field label="Invited">
          <input
            inputMode="numeric"
            value={invited}
            onChange={(e) => setInvited(e.target.value)}
            style={inputStyle()}
          />
        </Field>

        <Field label="Responded">
          <input
            inputMode="numeric"
            value={responded}
            onChange={(e) => setResponded(e.target.value)}
            style={inputStyle()}
          />
        </Field>

        <Field label="Random Seed">
          <input
            inputMode="numeric"
            value={randomSeed}
            onChange={(e) => setRandomSeed(e.target.value)}
            style={inputStyle()}
          />
        </Field>
      </div>

      {/* Context */}
      <div style={{ marginTop: 10, display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
        <Badge tone="gray">
          Target questionnaire: {String(selectedTemplate || "DEFAULT")} v{String(selectedVersion || "1")}
        </Badge>
        <Badge tone="gray">Tip: Seed once, then generate the report.</Badge>
        {reasonSeed ? <Badge tone="amber">{reasonSeed}</Badge> : null}
      </div>

      {/* Primary action */}
      <div style={{ marginTop: 14, display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
        <Button
          onClick={seedDemoResponses}
          disabled={busy || !!reasonSeed}
          variant="primary"
          title={reasonSeed || "Seed demo participants + responses"}
        >
          {busy ? "Seeding..." : "Seed Demo Responses"}
        </Button>

        <Button
          onClick={() => setTask("list_participants")}
          disabled={busy || !!reasonEval}
          variant="soft"
          title={reasonEval || "Verify the demo participants were created"}
        >
          View Participants
        </Button>

        <Button
          onClick={() => setTask("create_questions_manual")}
          disabled={busy || !!reasonManual}
          variant="secondary"
          title={reasonManual || "Back to questions"}
        >
          Back: Questions →
        </Button>
      </div>

      {/* Navigation: Next / Back */}
      <div style={{ marginTop: 12 }}>
        {renderNextActionBar({
          label: "Next: Generate Report →",
          toTask: "generate_report",
          nextReason: reasonSeed,           // disables Next with reason if locked
          onRefresh: () => {
            listParticipants?.();
            setTask("list_participants");
          },
          backTo: "list_evaluations",
        })}

      </div>
    </Card>
  );
}

    // Generate report
if (task === "generate_report") {
  const reasonReport = lockReason("report");        // requires eval + questions (per your lockReason)
  const reasonEval = lockReason("evaluation");      // requires eval
  const hasLatest = !!latestSummary?.exec;

  // Optional download button (safe)
  const canDownload = !!result?.data?.report_id && typeof window !== "undefined" && typeof window.downloadReportDocx === "function";

  //const canDownload = typeof downloadReportDocx === "function" && !!result?.data?.report_id;

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
          <Button
            onClick={() => downloadReportDocx(result?.data?.report_id)}
            disabled={busy}
            variant="soft"
            title="Download the latest report as DOCX"
          >
            Download DOCX
          </Button>
        ) : null}

        {reasonReport ? <Badge tone="amber">{reasonReport}</Badge> : null}
      </div>

      {/* ✅ Next/Back bar */}
      <div style={{ marginTop: 12 }}>
        {typeof renderNextActionBar === "function"
          ? renderNextActionBar({
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
          : null}
      </div>

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

}

  //End of renderConsultantTask function

  // Task label (for top bar)
  const taskLabel = useMemo(() => {
    for (const g of CONSULTANT_TASK_GROUPS) {
      const found = g.items.find((x) => x.key === task);
      if (found) return found.label;
    }
    return "Task";
  }, [task]);

  //Here is where we actually build the page with sidebar and the main bar(page)

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



        {/* ✅ Grouped Consultant tasks (color-coded + collapsible) */}
        <div style={{ padding: "0 10px 16px" }}>
          <div
            style={{
              margin: "8px 8px 10px",
              fontSize: 12,
              fontWeight: 900,
              color: "rgba(255,255,255,0.75)",
            }}
          >
            Consultant tasks
          </div>

          {CONSULTANT_TASK_GROUPS.map((grp) => {
            const isOpen = !!openGroups?.[grp.group];
            const count = grp.items?.length || 0;

            return (
              <div key={grp.group} style={{ marginBottom: 10 }}>
                {/* Header acts like an accordion toggle */}
                <button
                  type="button"
                  onClick={() =>
                    setOpenGroups((prev) => ({
                      ...(prev || {}),
                      [grp.group]: !prev?.[grp.group],
                    }))
                  }
                  style={{
                    ...groupHeaderStyleTone(grp.group),
                    width: "100%",
                    textAlign: "left",
                    cursor: "pointer",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    gap: 10,
                  }}
                  title="Click to expand/collapse"
                >
                  <span style={{ display: "flex", alignItems: "center", gap: 10 }}>
                    <span style={{ fontWeight: 900 }}>{grp.group}</span>
                    <span
                      style={{
                        fontSize: 11,
                        padding: "2px 8px",
                        borderRadius: 999,
                        border: "1px solid rgba(255,255,255,0.16)",
                        color: "rgba(255,255,255,0.85)",
                        background: "rgba(0,0,0,0.18)",
                      }}
                    >
                      {count}
                    </span>
                  </span>

                  <span style={{ fontSize: 12, color: "rgba(255,255,255,0.85)" }}>
                    {isOpen ? "▾" : "▸"}
                  </span>
                </button>

                {isOpen ? (
                  <div style={{ marginTop: 8 }}>
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
                ) : null}
              </div>
            );
          })}
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
        {renderWorkflowBar()}


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

        {/* Debug toggle + Raw Response (collapsed by default) */}
        <div style={{ marginTop: 14 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
            <Button
              variant="soft"
              disabled={!result}
              onClick={() => setShowDebug((s) => !s)}
              title="Toggle debug output"
            >
              {showDebug ? "Hide Debug" : "Show Debug"}
            </Button>

            {result?.action ? <Badge tone="gray">Last action: {result.action}</Badge> : null}
          </div>

          {result && showDebug ? (
            <div style={{ marginTop: 10 }}>
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
        </div>

      </main>
    </div>
  );
}
