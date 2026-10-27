/**
 * Question bank (the firm's methodology as data) and the per-participant question preview.
 */
import { request } from "./orgApi.js";

const QB = "/question-bank";
const item = (id) => `${QB}/items/${encodeURIComponent(id)}`;

function query(params) {
  const q = new URLSearchParams();
  Object.entries(params || {}).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== "" && v !== false) q.set(k, String(v));
  });
  const s = q.toString();
  return s ? `?${s}` : "";
}

export const questionBankApi = {
  meta: () => request(`${QB}/meta`),
  list: (filters) => request(`${QB}/items${query(filters)}`),
  get: (id) => request(item(id)),
  create: (body) => request(`${QB}/items`, { method: "POST", body }),
  update: (id, body) => request(item(id), { method: "PATCH", body }),
  approve: (id) => request(`${item(id)}/approve`, { method: "POST" }),
  retire: (id) => request(`${item(id)}/retire`, { method: "POST" }),
  validateRule: (rule) => request(`${QB}/rules/validate`, { method: "POST", body: { rule } }),
  addClause: (id, code, reference) => request(`${item(id)}/clauses`, { method: "POST", body: { code, reference } }),
  confirmClause: (id, clauseId) => request(`${item(id)}/clauses/${clauseId}/confirm`, { method: "POST" }),
  removeClause: (id, clauseId) => request(`${item(id)}/clauses/${clauseId}`, { method: "DELETE" }),
  options: (evalId) => request(`/evaluations/${encodeURIComponent(evalId)}/options`),
  setOptions: (evalId, options) =>
    request(`/evaluations/${encodeURIComponent(evalId)}/options`, { method: "PUT", body: { options } }),
  assemble: (evalId, body) =>
    request(`/evaluations/${encodeURIComponent(evalId)}/assembly`, { method: "POST", body: body || {} }),
  runs: (evalId) => request(`/evaluations/${encodeURIComponent(evalId)}/assembly-runs`),
  questionSet: (evalId, participantId) =>
    request(`/evaluations/${encodeURIComponent(evalId)}/participants/${encodeURIComponent(participantId)}/question-set`),
  preview: (evalId, { participantId, includeDrafts } = {}) =>
    request(
      `/evaluations/${encodeURIComponent(evalId)}/question-preview${query({
        participant_id: participantId,
        include_drafts: includeDrafts,
      })}`
    ),
};
