/**
 * Helpers for COMMITTEE_EVAL track config (API JSON shape).
 */

export const COMMITTEE_TRACK_CODE = "COMMITTEE_EVAL";

export function isCommitteeTemplate(t) {
  if (!t) return false;
  const code = String(t.code || "").trim().toUpperCase();
  const mode = String(t.subject_mode || "").trim().toUpperCase();
  return code === COMMITTEE_TRACK_CODE || mode === "COMMITTEE";
}

/** @typedef {{ committees: string[], membershipByCommittee: Record<string, { mode: 'all'|'selected', emails: string[] }> }} CommitteeEditorState */

/**
 * @param {object} config - API config object
 * @returns {CommitteeEditorState}
 */
export function parseCommitteeConfigFromApi(config) {
  const cfg = config && typeof config === "object" ? config : {};
  const committees = Array.isArray(cfg.committees)
    ? cfg.committees.map((c) => String(c || "").trim()).filter(Boolean)
    : [];
  const rawMembers = cfg.committee_members && typeof cfg.committee_members === "object" ? cfg.committee_members : {};
  const membershipByCommittee = {};
  for (const name of committees) {
    const list = rawMembers[name];
    if (Array.isArray(list) && list.length > 0) {
      membershipByCommittee[name] = {
        mode: "selected",
        emails: list.map((e) => String(e || "").trim().toLowerCase()).filter(Boolean),
      };
    } else {
      membershipByCommittee[name] = { mode: "all", emails: [] };
    }
  }
  return { committees, membershipByCommittee };
}

/**
 * @param {CommitteeEditorState} state
 * @returns {object} API config
 */
export function buildCommitteeConfigForApi(state) {
  const committees = (state.committees || []).map((c) => String(c || "").trim()).filter(Boolean);
  const committee_members = {};
  for (const name of committees) {
    const row = state.membershipByCommittee?.[name];
    if (row?.mode === "selected" && Array.isArray(row.emails) && row.emails.length > 0) {
      committee_members[name] = [...new Set(row.emails.map((e) => String(e || "").trim().toLowerCase()).filter(Boolean))];
    }
  }
  const out = { committees };
  if (Object.keys(committee_members).length > 0) {
    out.committee_members = committee_members;
  }
  return out;
}

export function defaultCommitteeEditorState() {
  return { committees: [], membershipByCommittee: {} };
}

/**
 * @param {CommitteeEditorState} state
 * @param {{ participantEmails: Set<string> }} opts
 * @returns {string|null} error message or null
 */
export function validateCommitteeEditorState(state, opts = {}) {
  const committees = (state.committees || []).map((c) => String(c || "").trim()).filter(Boolean);
  if (committees.length === 0) {
    return "Add at least one committee name.";
  }
  const known = opts.participantEmails || new Set();
  for (const name of committees) {
    const row = state.membershipByCommittee?.[name];
    if (row?.mode === "selected") {
      const emails = row.emails || [];
      if (emails.length === 0) {
        return `Select at least one member for committee "${name}", or choose "All invited participants".`;
      }
      for (const e of emails) {
        if (!known.has(String(e).trim().toLowerCase())) {
          return `Email "${e}" is not in the participant list for committee "${name}".`;
        }
      }
    }
  }
  return null;
}
