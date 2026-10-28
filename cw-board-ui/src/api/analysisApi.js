/**
 * Analysis of assembled evaluations: runs, results per subject, evidence, findings and conclusions.
 * Consultant decisions send X-Consultant-Name so findings show who accepted or edited them.
 */
import { request } from "./orgApi.js";
import { who } from "./questionBankApi.js";

const base = (evalId) => `/evaluations/${encodeURIComponent(evalId)}/analysis`;
const run = (evalId, runId) => `${base(evalId)}/runs/${encodeURIComponent(runId)}`;

export const analysisApi = {
  runs: (evalId) => request(`${base(evalId)}/runs`),
  start: (evalId, body) => request(`${base(evalId)}/runs`, { method: "POST", body, headers: who() }),
  run: (evalId, runId) => request(run(evalId, runId)),
  evidence: (evalId, runId, subjectId) => request(`${run(evalId, runId)}/subjects/${encodeURIComponent(subjectId)}/evidence`),
  findings: (evalId, runId, subjectId) =>
    request(`${run(evalId, runId)}/findings${subjectId ? `?subject_id=${encodeURIComponent(subjectId)}` : ""}`),
  addFinding: (evalId, runId, body) => request(`${run(evalId, runId)}/findings`, { method: "POST", body, headers: who() }),
  updateFinding: (evalId, runId, findingId, body) =>
    request(`${run(evalId, runId)}/findings/${encodeURIComponent(findingId)}`, { method: "PATCH", body, headers: who() }),
  conclusions: (evalId, runId) => request(`${run(evalId, runId)}/conclusions`),
  setConclusion: (evalId, runId, body) => request(`${run(evalId, runId)}/conclusions`, { method: "PUT", body, headers: who() }),
  complete: (evalId, runId) => request(`${run(evalId, runId)}/complete`, { method: "POST", headers: who() }),
  compare: (evalId, oldId, newId) =>
    request(`${base(evalId)}/compare?old=${encodeURIComponent(oldId)}&new=${encodeURIComponent(newId)}`),
};
