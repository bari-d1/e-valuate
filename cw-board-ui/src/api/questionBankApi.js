/**
 * Question bank (the firm's methodology as data) and the per-participant question preview.
 */
import { request } from "./orgApi.js";

const QB = "/question-bank";
const ev = (id) => `/evaluations/${encodeURIComponent(id)}`;
const aq = (evalId, qid) => `${ev(evalId)}/assembled-questions/${encodeURIComponent(qid)}`;

// Who made a change, for the audit trail (the shared key carries no identity)
export const CONSULTANT_NAME_KEY = "consultant.name";
export function who() {
  try {
    const name = (localStorage.getItem(CONSULTANT_NAME_KEY) || "").trim();
    return name ? { "X-Consultant-Name": name } : {};
  } catch {
    return {};
  }
}
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
    request(`/evaluations/${encodeURIComponent(evalId)}/assembly`, { method: "POST", body: body || {}, headers: who() }),
  runs: (evalId) => request(`/evaluations/${encodeURIComponent(evalId)}/assembly-runs`),
  questionSet: (evalId, participantId) =>
    request(`/evaluations/${encodeURIComponent(evalId)}/participants/${encodeURIComponent(participantId)}/question-set`),
  // Consultant review of assembled sets. Every change returns the question with fresh "metrics".
  review: (evalId) => request(`${ev(evalId)}/review`),
  reviewSet: (evalId, pid) => request(`${ev(evalId)}/participants/${encodeURIComponent(pid)}/question-set/review`),
  wording: (evalId, qid, body) => request(aq(evalId, qid), { method: "PATCH", body, headers: who() }),
  regenerate: (evalId, qid, note) => request(`${aq(evalId, qid)}/regenerate`, { method: "POST", body: { note }, headers: who() }),
  acceptNew: (evalId, qid) => request(`${aq(evalId, qid)}/accept`, { method: "POST", body: {}, headers: who() }),
  rejectNew: (evalId, qid) => request(`${aq(evalId, qid)}/reject`, { method: "POST", body: {}, headers: who() }),
  tags: (evalId, qid, body) => request(`${aq(evalId, qid)}/tags`, { method: "PATCH", body, headers: who() }),
  remove: (evalId, qid, reason) => request(`${aq(evalId, qid)}/remove`, { method: "POST", body: { reason }, headers: who() }),
  restore: (evalId, qid) => request(`${aq(evalId, qid)}/restore`, { method: "POST", headers: who() }),
  move: (evalId, qid, direction) => request(`${aq(evalId, qid)}/move`, { method: "POST", body: { direction }, headers: who() }),
  searchBank: (evalId, text, subjectType) =>
    request(`${ev(evalId)}/review/bank-items${query({ text, subject_type: subjectType })}`),
  addQuestion: (evalId, pid, body) =>
    request(`${ev(evalId)}/participants/${encodeURIComponent(pid)}/question-set/questions`, { method: "POST", body, headers: who() }),
  approveSet: (evalId, pid, overrideReason) =>
    request(`${ev(evalId)}/participants/${encodeURIComponent(pid)}/question-set/approve`, {
      method: "POST",
      body: { override_reason: overrideReason || null },
      headers: who(),
    }),
  reopenSet: (evalId, pid, reason) =>
    request(`${ev(evalId)}/participants/${encodeURIComponent(pid)}/question-set/reopen`, { method: "POST", body: { reason }, headers: who() }),
  bulkApprove: (evalId, participantIds, overrideReason) =>
    request(`${ev(evalId)}/question-sets/approve`, {
      method: "POST",
      body: { participant_ids: participantIds, override_reason: overrideReason || null },
      headers: who(),
    }),
  reviewSubjects: (evalId) => request(`${ev(evalId)}/review/subjects`),
  reviewSubject: (evalId, sid) => request(`${ev(evalId)}/review/subjects/${encodeURIComponent(sid)}`),
  preview: (evalId, { participantId, includeDrafts } = {}) =>
    request(
      `/evaluations/${encodeURIComponent(evalId)}/question-preview${query({
        participant_id: participantId,
        include_drafts: includeDrafts,
      })}`
    ),
};
