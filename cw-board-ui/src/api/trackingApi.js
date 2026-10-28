/**
 * Tracking and reminders for evaluations that use assembled question sets.
 * Consultant actions send X-Consultant-Name so the timeline shows who did what.
 */
import { request } from "./orgApi.js";
import { who } from "./questionBankApi.js";

const tr = (evalId) => `/evaluations/${encodeURIComponent(evalId)}/tracking`;
const person = (evalId, pid) => `${tr(evalId)}/participants/${encodeURIComponent(pid)}`;

export const trackingApi = {
  summary: (evalId) => request(tr(evalId)),
  timeline: (evalId, pid) => request(`${person(evalId, pid)}/events`),
  // participantIds: null for everyone outstanding; dryRun: who would be emailed and who skipped
  remind: (evalId, participantIds, { override = false, dryRun = false } = {}) =>
    request(`${tr(evalId)}/remind`, {
      method: "POST",
      body: { participant_ids: participantIds, override, dry_run: dryRun },
      headers: who(),
    }),
  resendLink: (evalId, pid) => request(`${person(evalId, pid)}/resend-link`, { method: "POST", headers: who() }),
  regenerateLink: (evalId, pid) => request(`${person(evalId, pid)}/regenerate-link`, { method: "POST", headers: who() }),
  reopenForm: (evalId, pid, reason) =>
    request(`${person(evalId, pid)}/reopen`, { method: "POST", body: { reason }, headers: who() }),
  setDeadline: (evalId, deadline, notify) =>
    request(`${tr(evalId)}/deadline`, { method: "PUT", body: { deadline, notify }, headers: who() }),
  close: (evalId) => request(`${tr(evalId)}/close`, { method: "POST", headers: who() }),
  reopen: (evalId) => request(`${tr(evalId)}/reopen`, { method: "POST", headers: who() }),
  settings: (evalId) => request(`${tr(evalId)}/reminder-settings`),
  saveSettings: (evalId, body) =>
    request(`${tr(evalId)}/reminder-settings`, { method: "PUT", body, headers: who() }),
};
