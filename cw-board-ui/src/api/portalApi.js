/**
 * src/api/portalApi.js
 * --------------------
 * Token-based Board Member portal API client.
 *
 * Notes:
 * - The frontend (Vite) runs on http://localhost:5173
 * - The backend (FastAPI) runs on http://localhost:8000
 * - Ensure FastAPI CORS allows the frontend origin(s).
 *
 * Endpoints used:
 * - GET  /api/v1/portal/hub/{hubToken}
 * - GET  /api/v1/portal/{token}
 * - GET  /api/v1/portal/{token}/responses
 * - POST /api/v1/portal/{token}/responses?finalize=true|false
 */

import { throwPortalLoadError } from "./memberPortalErrors.js";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "";

async function _readErrorMessage(r) {
  let msg = await r.text();
  try {
    const j = JSON.parse(msg);
    msg = j.detail || msg;
  } catch {
    /* keep text */
  }
  return msg;
}

/**
 * @param {string} hubToken
 * @param {{ allowNotFound?: boolean }} [opts] — if true, returns null on 404 (for token disambiguation)
 */
export async function portalHubLoad(hubToken, opts = {}) {
  const t = encodeURIComponent(String(hubToken || "").trim());
  const r = await fetch(`${API_BASE}/api/v1/portal/hub/${t}`);
  if (r.status === 404 && opts.allowNotFound) {
    return null;
  }
  if (!r.ok) {
    throw new Error(await _readErrorMessage(r));
  }
  return r.json();
}

export async function portalLoad(token) {
  const r = await fetch(`${API_BASE}/api/v1/portal/${encodeURIComponent(String(token || "").trim())}`);
  if (!r.ok) await throwPortalLoadError(r);
  return r.json();
}

export async function portalGetResponses(token) {
  const r = await fetch(`${API_BASE}/api/v1/portal/${token}/responses`);
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

export async function portalSubmitResponses(token, answers, finalize = true) {
  const url = `${API_BASE}/api/v1/portal/${token}/responses?finalize=${finalize ? "true" : "false"}`;
  const r = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ answers }),
  });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}
