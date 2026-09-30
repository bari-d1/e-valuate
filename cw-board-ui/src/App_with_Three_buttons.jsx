// src/App.jsx
import { useMemo, useState } from "react";

const API_BASE = "http://127.0.0.1:8000/api/v1";

export default function App() {
  const [evaluationId, setEvaluationId] = useState("eval-001");
  const [loading, setLoading] = useState(false);

  const [latestReportId, setLatestReportId] = useState("");
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");

  const canDownload = useMemo(() => {
    const rid = (latestReportId || "").trim();
    return rid.length > 0;
  }, [latestReportId]);

  async function handleGenerateReport() {
    setError("");
    setResult(null);
    setLoading(true);

    try {
      const url = `${API_BASE}/evaluations/${encodeURIComponent(
        evaluationId.trim()
      )}/report/generate`;

      const resp = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json", accept: "application/json" },
        body: JSON.stringify({
          include_trends: true,
          include_compliance: true,
        }),
      });

      const data = await safeJson(resp);

      if (!resp.ok) {
        throw new Error(data?.detail || `HTTP ${resp.status}`);
      }

      // Your API returns { report_id, status }
      setLatestReportId(data.report_id || "");
      setResult({ action: "generate_report", data });
    } catch (e) {
      setError(String(e?.message || e));
    } finally {
      setLoading(false);
    }
  }

  async function handleGetLatestReport() {
    setError("");
    setResult(null);
    setLoading(true);

    try {
      const url = `${API_BASE}/evaluations/${encodeURIComponent(
        evaluationId.trim()
      )}/report`;

      const resp = await fetch(url, { headers: { accept: "application/json" } });
      const data = await safeJson(resp);

      if (!resp.ok) {
        throw new Error(data?.detail || `HTTP ${resp.status}`);
      }

      // Your endpoint returns a payload with report_id + summary_json etc.
      setLatestReportId(data.report_id || "");
      setResult({ action: "get_latest_report", data });
    } catch (e) {
      setError(String(e?.message || e));
    } finally {
      setLoading(false);
    }
  }

  async function handleDownloadDocx() {
    setError("");
    setResult(null);

    const rid = (latestReportId || "").trim();
    if (!rid) {
      setError("No report_id available. Generate a report or fetch latest first.");
      return;
    }

    setLoading(true);
    try {
      const url = `${API_BASE}/reports/${encodeURIComponent(rid)}/docx`;

      const resp = await fetch(url, {
        method: "GET",
        headers: { accept: "application/vnd.openxmlformats-officedocument.wordprocessingml.document" },
      });

      if (!resp.ok) {
        const maybe = await safeJson(resp);
        throw new Error(maybe?.detail || `HTTP ${resp.status}`);
      }

      const blob = await resp.blob();

      // Try to read filename from Content-Disposition; otherwise fallback
      const cd = resp.headers.get("content-disposition") || "";
      const filename = parseFilenameFromContentDisposition(cd) || `report_${rid}.docx`;

      triggerBrowserDownload(blob, filename);

      setResult({
        action: "download_docx",
        data: { report_id: rid, downloaded_as: filename, content_type: blob.type || "application/octet-stream" },
      });
    } catch (e) {
      setError(String(e?.message || e));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{ maxWidth: 980, margin: "32px auto", padding: "0 16px", fontFamily: "system-ui, -apple-system, Segoe UI, Roboto, Arial" }}>
      <h1 style={{ marginBottom: 8 }}>C&amp;W Board Evaluation — UI (Phase 1)</h1>
      <p style={{ marginTop: 0, color: "#444" }}>
        Minimal React UI to call your FastAPI endpoints: <b>Generate Report</b>, <b>Get Latest</b>, <b>Download DOCX</b>.
      </p>

      <div style={{ display: "flex", gap: 12, alignItems: "flex-end", flexWrap: "wrap", padding: 16, border: "1px solid #ddd", borderRadius: 12 }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          <label style={{ fontSize: 12, color: "#555" }}>Evaluation ID</label>
          <input
            value={evaluationId}
            onChange={(e) => setEvaluationId(e.target.value)}
            placeholder="eval-001"
            style={{ padding: "10px 12px", borderRadius: 10, border: "1px solid #ccc", minWidth: 240 }}
          />
        </div>

        <div style={{ display: "flex", flexWrap: "wrap", gap: 10 }}>
          <button
            onClick={handleGenerateReport}
            disabled={loading || !evaluationId.trim()}
            style={btnStyle}
            title="POST /evaluations/{evaluation_id}/report/generate"
          >
            {loading ? "Working..." : "Generate Report"}
          </button>

          <button
            onClick={handleGetLatestReport}
            disabled={loading || !evaluationId.trim()}
            style={btnStyle}
            title="GET /evaluations/{evaluation_id}/report"
          >
            {loading ? "Working..." : "Get Latest Report"}
          </button>

          <button
            onClick={handleDownloadDocx}
            disabled={loading || !canDownload}
            style={{ ...btnStyle, opacity: loading || !canDownload ? 0.6 : 1 }}
            title="GET /reports/{report_id}/docx"
          >
            {loading ? "Working..." : "Download DOCX"}
          </button>
        </div>
      </div>

      <div style={{ marginTop: 14, padding: 12, borderRadius: 12, background: "#fafafa", border: "1px solid #eee" }}>
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
          <span style={{ fontSize: 12, color: "#666" }}>
            API Base: <code>{API_BASE}</code>
          </span>
          <span style={{ fontSize: 12, color: "#666" }}>
            Current report_id: <code>{latestReportId || "(none yet)"}</code>
          </span>
        </div>
      </div>

      {error ? (
        <div style={{ marginTop: 16, padding: 12, borderRadius: 12, border: "1px solid #f3b5b5", background: "#fff5f5" }}>
          <b style={{ color: "#a40000" }}>Error</b>
          <div style={{ marginTop: 8, whiteSpace: "pre-wrap" }}>{error}</div>
        </div>
      ) : null}

      <div style={{ marginTop: 16 }}>
        <h2 style={{ marginBottom: 8 }}>Result</h2>
        <pre
          style={{
            padding: 14,
            borderRadius: 12,
            border: "1px solid #ddd",
            background: "white",
            overflowX: "auto",
            minHeight: 120,
          }}
        >
          {result ? JSON.stringify(result, null, 2) : "No result yet. Click a button above."}
        </pre>
      </div>

      <div style={{ marginTop: 20, color: "#666", fontSize: 13 }}>
        <p style={{ marginTop: 0 }}>
          Tip: If you ever see a <code>NetworkError</code>, confirm FastAPI is running on <code>127.0.0.1:8000</code>.
        </p>
      </div>
    </div>
  );
}

const btnStyle = {
  padding: "10px 14px",
  borderRadius: 10,
  border: "1px solid #333",
  background: "#111",
  color: "white",
  cursor: "pointer",
};

async function safeJson(resp) {
  // Some responses might not be JSON (e.g., DOCX download).
  try {
    return await resp.json();
  } catch {
    return null;
  }
}

function parseFilenameFromContentDisposition(cd) {
  // Supports: attachment; filename="foo.docx"
  const match = /filename\*?=(?:UTF-8''|")?([^";]+)"?/i.exec(cd || "");
  if (!match) return null;
  try {
    return decodeURIComponent(match[1]);
  } catch {
    return match[1];
  }
}

function triggerBrowserDownload(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
