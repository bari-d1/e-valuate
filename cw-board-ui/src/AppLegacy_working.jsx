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
import { NavLink, Navigate, Route, Routes, useLocation, useNavigate } from "react-router-dom";

import InviteParticipantsPage from "./pages/consultant/InviteParticipants";
import ListParticipantsPage from "./pages/consultant/ListParticipants";
import CreateEvaluationPage from "./pages/consultant/CreateEvaluation";
import ListEvaluationsPage from "./pages/consultant/ListEvaluations";
import SelectQuestionnairePage from "./pages/consultant/SelectQuestionnaire";
import CreateQuestionsManualPage from "./pages/consultant/CreateQuestionsManual";
import GenerateQuestionsAIPage from "./pages/consultant/GenerateQuestionsAI";
import GenerateReportPage from "./pages/consultant/GenerateReport";
import ListQuestionsPage from "./pages/consultant/ListQuestions";
import SeedDemoResponsesPage from "./pages/consultant/SeedDemoResponses";
import SeedDefaultQuestionsPage from "./pages/consultant/SeedDefaultQuestions";





const API_BASE = import.meta.env.VITE_API_BASE || "http://127.0.0.1:8000";


/* --------------------------
   Stable constants
-------------------------- */
const PAGES = [{ key: "consultant", label: "Consultant" }];

const TASK_TO_PATH = {
  list_evaluations: "/consultant/evaluations",
  create_eval: "/consultant/evaluations/create",
  select_questionnaire: "/consultant/questionnaire/select",
  invite_participants: "/consultant/participants/invite",
  list_participants: "/consultant/participants",
  list_questions: "/consultant/questions",
  create_questions_manual: "/consultant/questions/edit",
  seed_questions: "/consultant/questions/seed",
  generate_questions_ai: "/consultant/questions/ai",
  seed_demo_responses: "/consultant/analysis/seed-demo",
  generate_report: "/consultant/analysis/report",
};

function stepIndexFromPath(pathname) {
  const p = String(pathname || "");

  if (p.includes("/consultant/evaluations")) return 0;
  if (p.includes("/consultant/questionnaire")) return 1;
  if (p.includes("/consultant/participants")) return 2;
  if (p.includes("/consultant/questions")) return 3;
  if (p.includes("/consultant/analysis")) return 4;

  return 0;
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

//console.log("renderFlowBar type:", typeof renderFlowBar);

const ui = {
  Card,
  Badge,
  Button,
  Field,
  // ✅ ADD THIS
  renderFlowBar,
  tdStyle,
  tableWrapStyle,
  miniPanelStyle,
  miniTitleStyle,
  inputStyle,
  textareaStyle,
};






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

function parseInviteText(text) {
  const lines = String(text || "")
    .split(/\r?\n/)
    .map((l) => l.trim())
    .filter(Boolean);

  const out = [];
  for (const line of lines) {
    const row = parseCsvLine(line);
    if (!row) continue;

    // minimal email sanity check (keeps idempotency behavior by email)
    const email = String(row.email || "").trim();
    if (!email || !email.includes("@")) continue;

    out.push({
      email,
      full_name: row.full_name || null,
      role: row.role || null,
    });
  }
  return out;
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

// ---------------- API helpers (centralized fetch) ----------------


function joinUrl(base, path) {
  const b = (base || "").replace(/\/+$/, "");
  const p = String(path || "").replace(/^\/+/, "");
  return `${b}/${p}`;
}

async function apiRequest(method, path, payload, opts = {}) {
  const baseUrl = opts.baseUrl || API_BASE; // ✅ default to API_BASE (CRITICAL)
  const url = path.startsWith("http") ? path : joinUrl(baseUrl, path);

  const headers = {
    ...(payload ? { "Content-Type": "application/json" } : {}),
    ...(opts.headers || {}),
  };

  const res = await fetch(url, {
    method,
    headers,
    body: payload ? JSON.stringify(payload) : undefined,
    credentials: opts.credentials || "same-origin",
  });

  const data = await safeJsonOrText(res);

  if (!res.ok) {
    const err = new Error(
      (typeof data === "string" && data) ||
        (data && data.message) ||
        `Request failed (${res.status})`
    );
    err.status = res.status;
    err.data = data;
    err.url = url;
    err.method = method;
    throw err;
  }

  return data;
}


function apiGet(path, opts) {
  return apiRequest("GET", path, undefined, opts);
}
function apiPost(path, payload, opts) {
  return apiRequest("POST", path, payload, opts);
}
function apiPatch(path, payload, opts) {
  return apiRequest("PATCH", path, payload, opts);
}


/* --------------------------
   App
-------------------------- */
export default function AppLegacy() {

  const navigate = useNavigate();
  const location = useLocation();

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






    // (keep page if you want, but it’s not used anymore)
    const [page, setPage] = useState("consultant");


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
    return navigate(TASK_TO_PATH[toTask] || "/consultant/evaluations");

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
          onClick={() => navigate(TASK_TO_PATH[opts.backTo] || "/consultant/evaluations")}

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
    if (!String(evalId || "").trim()) throw new Error("Evaluation ID is required.");

    const payload = { participants: parseInviteText(inviteText) };
    const data = await apiPost(`/api/v1/evaluations/${evalId}/participants/invite`, payload);
    setResult({ action: "invite_participants", data });
  } catch (e) {
    setError(e?.message || String(e));
    setResult({ action: "error", data: { message: e.message, status: e.status, raw: e.data } });
  } finally {
    setBusy(false);
  }
}

async function listParticipants() {
  beginAction();
  try {
    if (!String(evalId || "").trim()) throw new Error("Evaluation ID is required.");

    const data = await apiGet(`/api/v1/evaluations/${evalId}/participants`);
    setResult({ action: "list_participants", data });
  } catch (e) {
    setError(e?.message || String(e));
    setResult({ action: "error", data: { message: e.message, status: e.status, raw: e.data } });
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
      const currentIndex = stepIndexFromPath(location.pathname);


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
                onClick={() => navigate(TASK_TO_PATH[nextStepObj.toTask] || "/consultant/evaluations")}

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
                    onClick={() => navigate(TASK_TO_PATH[s.toTask] || "/consultant/evaluations")}

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

    // -----------------------------------------
  // ✅ Sidebar navigation list (no setTask)
  // -----------------------------------------
  const CONSULTANT_NAV_GROUPS = [
    {
      group: "Evaluations",
      items: [
        { to: "/consultant/evaluations", label: "List Evaluations" },
        { to: "/consultant/evaluations/create", label: "Create Evaluation" },
      ],
    },
    {
      group: "Questionnaire",
      items: [
        { to: "/consultant/questionnaire/select", label: "Select Questionnaire" },
        { to: "/consultant/questions", label: "View Questions" },
        { to: "/consultant/questions/edit", label: "Add / Edit Questions" },
        { to: "/consultant/questions/seed", label: "Seed Default Questionnaire" },
        { to: "/consultant/questions/ai", label: "Generate Questions (AI)" },
      ],
    },
    {
      group: "Participants",
      items: [
        { to: "/consultant/participants/invite", label: "Invite Participants" },
        { to: "/consultant/participants", label: "View Participants" },
      ],
    },
    {
      group: "Analysis",
      items: [
        { to: "/consultant/analysis/seed-demo", label: "Seed Demo Responses" },
        { to: "/consultant/analysis/report", label: "Generate Report" },
      ],
    },
  ];

  //End of renderConsultantTask function

  // ✅ derive a label from pathname (replaces taskLabel)
  const routeLabel = useMemo(() => {
    const p = location.pathname;
    for (const g of CONSULTANT_NAV_GROUPS) {
      const found = g.items.find((x) => p.startsWith(x.to));
      if (found) return found.label;
    }
    // fallback for base
    if (p === "/consultant" || p === "/consultant/") return "List Evaluations";
    return "Consultant";
  }, [location.pathname]);



  const focus = renderFocusHeader();

  //Here is where we actually build the page with sidebar and the main bar(page)





  return (
    <div style={pageShellStyle()}>
      {/* Sidebar */}
      <aside style={sidebarStyle()}>
        <div style={{ padding: "18px 16px" }}>
          <div style={{ fontSize: 14, fontWeight: 900, color: "white" }}>C&amp;W Board Eval</div>
          <div style={{ marginTop: 4, fontSize: 12, color: "rgba(255,255,255,0.75)" }}>
            React UI • Phase 1 (Consultant)
          </div>
        </div>

        <div style={{ padding: "0 10px 16px" }}>
          <div style={{ margin: "8px 8px 10px", fontSize: 12, fontWeight: 900, color: "rgba(255,255,255,0.75)" }}>
            Consultant tasks
          </div>

          {CONSULTANT_NAV_GROUPS.map((grp) => (
            <div key={grp.group} style={{ marginBottom: 10 }}>
              <div style={groupHeaderStyleTone(grp.group)}>{grp.group}</div>

              <div style={{ marginTop: 8 }}>
                {grp.items.map((it) => (
                  <NavLink
                    key={it.to}
                    to={it.to}
                    style={({ isActive }) => ({
                      ...subNavItemStyle(isActive),
                      display: "block",
                      textDecoration: "none",
                    })}
                  >
                    {it.label}
                  </NavLink>
                ))}
              </div>
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
            <div style={{ fontSize: 18, fontWeight: 900, color: "#0F172A" }}>Consultant Workspace</div>
            <Badge tone="gray">Evaluation in focus: {evalId || "—"}</Badge>
            <Badge tone="gray">Questionnaire: {String(selectedTemplate || "DEFAULT")} v{String(selectedVersion || "1")}</Badge>
            <Badge tone="blue">{routeLabel}</Badge>
          </div>
        </div>

        {renderWorkflowBar()}

        {error ? (
          <div style={{ marginTop: 14, padding: 14, borderRadius: 14, border: "1px solid #FCA5A5", background: "#FEF2F2", color: "#7F1D1D", fontWeight: 700, whiteSpace: "pre-wrap" }}>
            {error}
          </div>
        ) : null}

        <div style={{ marginTop: 14 }}>
          <Routes>
            {/* default inside consultant */}
            <Route path="/" element={<Navigate to="evaluations" replace />} />

            {/* Evaluations */}
            <Route
              path="evaluations"
              element={
                <ListEvaluationsPage
                  ui={ui}
                  evaluations={evaluations}
                  evalsLoadedAt={evalsLoadedAt}
                  evalId={evalId}
                  selectedTemplate={selectedTemplate}
                  selectedVersion={selectedVersion}
                  busy={busy}
                  listEvaluations={listEvaluations}
                  // ✅ replace setTask usage with navigate inside the page OR pass navigate helper:
                  go={(to) => navigate(to)}
                  setFocusFromEvaluationRow={(ev) => {
                    const id = ev?.evaluation_id || ev?.id;
                    if (id) setEvalId(String(id));
                    // example: after choosing eval, go to questionnaire select
                    // navigate("/consultant/questionnaire/select");
                  }}
                  lockReason={lockReason}
                  formatDateMaybe={formatDateMaybe}
                  tableWrapStyle={tableWrapStyle}
                  tdStyle={tdStyle}
                  rowHoverStyle={rowHoverStyle}
                  renderFlowBar={renderFlowBar}
                />
              }
            />
            <Route
              path="evaluations/create"
              element={
                <CreateEvaluationPage
                  ui={ui}
                  tenantName={tenantName}
                  setTenantName={setTenantName}
                  sector={sector}
                  setSector={setSector}
                  year={year}
                  setYear={setYear}
                  newEvalId={newEvalId}
                  setNewEvalId={setNewEvalId}
                  regulatorsText={regulatorsText}
                  setRegulatorsText={setRegulatorsText}
                  evalId={evalId}
                  lastCreatedEvalId={lastCreatedEvalId}
                  questionnaireSavedAt={questionnaireSavedAt}
                  questionnaireSavedForEvalId={questionnaireSavedForEvalId}
                  setQuestionnaireSavedAt={setQuestionnaireSavedAt}
                  setQuestionnaireSavedForEvalId={setQuestionnaireSavedForEvalId}
                  selectedTemplate={selectedTemplate}
                  setSelectedTemplate={setSelectedTemplate}
                  selectedVersion={selectedVersion}
                  setSelectedVersion={setSelectedVersion}
                  busy={busy}
                  focus={focus}
                  createEvaluation={createEvaluation}
                  setEvaluationQuestionnaire={setEvaluationQuestionnaire}
                  go={(to) => navigate(to)}
                  inputStyle={inputStyle}
                />
              }
            />

            {/* Questionnaire */}
            <Route
              path="questionnaire/select"
              element={
                <SelectQuestionnairePage
                  ui={ui}
                  busy={busy}
                  focus={focus}
                  evalId={evalId}
                  selectedTemplate={selectedTemplate}
                  selectedVersion={selectedVersion}
                  questionnaireSavedForEvalId={questionnaireSavedForEvalId}
                  questionnaireSavedAt={questionnaireSavedAt}
                  setSelectedTemplate={setSelectedTemplate}
                  setSelectedVersion={setSelectedVersion}
                  go={(to) => navigate(to)}
                  lockReason={lockReason}
                  inputStyle={inputStyle}
                  renderFlowBar={renderFlowBar}
                />
              }
            />

            {/* Participants */}
            <Route
              path="participants/invite"
              element={
                <InviteParticipantsPage
                  ui={ui}
                  busy={busy}
                  focus={focus}
                  inviteText={inviteText}
                  setInviteText={setInviteText}
                  inviteParticipants={inviteParticipants}
                  listParticipants={listParticipants}
                  lockReason={lockReason}
                  go={(to) => navigate(to)}
                  renderNextActionBar={renderNextActionBar}
                  textareaStyle={textareaStyle}
                />
              }
            />
            <Route
              path="participants"
              element={
                <ListParticipantsPage
                  ui={ui}
                  busy={busy}
                  focus={focus}
                  result={result}
                  lockReason={lockReason}
                  listParticipants={listParticipants}
                  go={(to) => navigate(to)}
                  renderFlowBar={renderFlowBar}
                  tableWrapStyle={tableWrapStyle}
                  tdStyle={tdStyle}
                />
              }
            />

            {/* Questions */}
            <Route
              path="questions"
              element={
                <ListQuestionsPage
                  ui={ui}
                  busy={busy}
                  focus={focus}
                  questions={questions}
                  selectedTemplate={selectedTemplate}
                  selectedVersion={selectedVersion}
                  qsListLoadedAt={qsListLoadedAt}
                  listQuestionsTask={listQuestionsTask}
                  lockReason={lockReason}
                  go={(to) => navigate(to)}
                  formatDateMaybe={formatDateMaybe}
                  renderFlowBar={renderFlowBar}
                />
              }
            />
            <Route
              path="questions/edit"
              element={
                <CreateQuestionsManualPage
                  ui={ui}
                  busy={busy}
                  focus={focus}
                  questions={questions}
                  qsLoadedAt={qsLoadedAt}
                  selectedTemplate={selectedTemplate}
                  selectedVersion={selectedVersion}
                  lockReason={lockReason}
                  listQuestionsManual={listQuestionsManual}
                  createQuestionManual={createQuestionManual}
                  toggleQuestionActive={toggleQuestionActive}
                  go={(to) => navigate(to)}
                  qCreateStatus={qCreateStatus}
                  qDimension={qDimension}
                  setQDimension={setQDimension}
                  qAnswerType={qAnswerType}
                  setQAnswerType={setQAnswerType}
                  qWeight={qWeight}
                  setQWeight={setQWeight}
                  qActive={qActive}
                  setQActive={setQActive}
                  qText={qText}
                  setQText={setQText}
                  ANSWER_TYPES={ANSWER_TYPES}
                  renderFlowBar={renderFlowBar}
                  miniPanelStyle={miniPanelStyle}
                  miniTitleStyle={miniTitleStyle}
                  inputStyle={inputStyle}
                  textareaStyle={textareaStyle}
                  tdStyle={tdStyle}
                />
              }
            />
            <Route
              path="questions/ai"
              element={
                <GenerateQuestionsAIPage
                  ui={ui}
                  busy={busy}
                  focus={focus}
                  aiDrafts={aiDrafts}
                  aiSelectedIds={aiSelectedIds}
                  aiGeneratedAt={aiGeneratedAt}
                  aiAddStatus={aiAddStatus}
                  aiFile={aiFile}
                  aiFileName={aiFileName}
                  aiFileTextPreview={aiFileTextPreview}
                  aiFileInputRef={aiFileInputRef}
                  aiNQuestions={aiNQuestions}
                  setAiNQuestions={setAiNQuestions}
                  aiAllowedTypes={aiAllowedTypes}
                  setAiAllowedTypes={setAiAllowedTypes}
                  aiDimensionHints={aiDimensionHints}
                  setAiDimensionHints={setAiDimensionHints}
                  ANSWER_TYPES={ANSWER_TYPES}
                  deriveQuestionnaireTarget={deriveQuestionnaireTarget}
                  lockReason={lockReason}
                  handleAiFilePick={handleAiFilePick}
                  generateQuestionsFromFile={generateQuestionsFromFile}
                  selectAllDrafts={selectAllDrafts}
                  toggleDraftSelected={toggleDraftSelected}
                  setDraftField={setDraftField}
                  addSelectedDraftsToQuestionnaire={addSelectedDraftsToQuestionnaire}
                  go={(to) => navigate(to)}
                />
              }
            />

            <Route
              path="questions/seed"
              element={
                <SeedDefaultQuestionsPage
                  ui={ui}
                  busy={busy}
                  focus={focus}
                  evalId={evalId}
                  selectedTemplate={selectedTemplate}
                  selectedVersion={selectedVersion}
                  lockReason={lockReason}
                  seedQuestions={seedQuestions}
                  listQuestionsTask={listQuestionsTask}   // optional: refresh after seeding
                  go={(to) => navigate(to)}
                  renderNextActionBar={renderNextActionBar}
                />
              }
            />


            {/* Analysis */}
            <Route
              path="analysis/seed-demo"
              element={
                <SeedDemoResponsesPage
                  ui={ui}
                  busy={busy}
                  focus={focus}
                  invited={invited}
                  setInvited={setInvited}
                  responded={responded}
                  setResponded={setResponded}
                  randomSeed={randomSeed}
                  setRandomSeed={setRandomSeed}
                  selectedTemplate={selectedTemplate}
                  selectedVersion={selectedVersion}
                  lockReason={lockReason}
                  seedDemoResponses={seedDemoResponses}
                  listParticipants={listParticipants}
                  go={(to) => navigate(to)}
                  renderNextActionBar={renderNextActionBar}
                />
              }
            />
            <Route
              path="analysis/report"
              element={
                <GenerateReportPage
                  ui={ui}
                  busy={busy}
                  focus={focus}
                  result={result}
                  latestSummary={latestSummary}
                  selectedTemplate={selectedTemplate}
                  selectedVersion={selectedVersion}
                  lockReason={lockReason}
                  go={(to) => navigate(to)}
                  generateAndLoadLatestReport={generateAndLoadLatestReport}
                  renderNextActionBar={renderNextActionBar}
                />
              }
            />

            {/* Consultant unknown paths */}
            <Route path="*" element={<Navigate to="evaluations" replace />} />
          </Routes>
        </div>
      </main>
    </div>
  );

 // ✅ Fallback: never allow "blank screen" if a task key doesn't match


}




