/**
 * Participant form API (evaluations that use assembled question sets).
 *
 * - GET  /api/v1/portal/a/{token}           load the form (the first open locks the set)
 * - PUT  /api/v1/portal/a/{token}/answers   save answers: [{question_id, value}], null clears
 * - POST /api/v1/portal/a/{token}/submit    submit; 422 lists what's still missing
 *
 * Errors carry `status`, `code` and a `message` that is safe to show the participant.
 */

import { API_BASE } from "./orgApi.js";

const NETWORK_MESSAGE = "We couldn't reach the server. Check your connection and try again.";

async function call(token, path = "", { method = "GET", body } = {}) {
  const url = `${API_BASE}/api/v1/portal/a/${encodeURIComponent(String(token || "").trim())}${path}`;
  let res;
  try {
    res = await fetch(url, {
      method,
      headers: body === undefined ? { Accept: "application/json" } : { Accept: "application/json", "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    const err = new Error(NETWORK_MESSAGE);
    err.status = 0;
    err.code = "network";
    throw err;
  }
  let data = null;
  try {
    data = await res.json();
  } catch {
    data = null;
  }
  if (!res.ok) {
    const detail = data?.detail;
    const err = new Error(
      (detail && typeof detail === "object" && detail.message) || "Something went wrong. Please try again in a moment."
    );
    err.status = res.status;
    err.code = (detail && detail.code) || "error";
    err.errors = detail?.errors || [];
    err.missing = detail?.missing || [];
    throw err;
  }
  return data;
}

export const formApi = {
  load: (token) => call(token),
  save: (token, answers) => call(token, "/answers", { method: "PUT", body: { answers } }),
  submit: (token) => call(token, "/submit", { method: "POST" }),
};
