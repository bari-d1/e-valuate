/** Labels and small helpers shared by the question review pages. */

export const SET_STATUS = {
  not_assembled: { label: "Not assembled", tone: "gray" },
  draft: { label: "Draft", tone: "amber" },
  approved: { label: "Approved", tone: "green" },
  locked: { label: "Locked", tone: "gray" },
};

export const SOURCE_LABELS = {
  bank: "Bank wording",
  ai_tailored: "AI wording chosen",
  consultant_edited: "Edited by consultant",
  consultant_written: "Written by consultant",
  ai_new: "Proposed by AI",
};

export const SECTION_HINTS = {
  board: "Questions about the board as a whole and the secretariat.",
  committees: "Once for each committee they sit on.",
  colleagues: "About their fellow directors.",
  yourself: "Their self-assessment.",
  confirm: "Facts we already hold, for them to confirm.",
  additional: "Questions the AI proposed or a consultant added at the end.",
};

// Core peer grid items: one short statement rated for every colleague, shown as one block
export const GRID_PREFIX = "PEER-CORE-";
export const isGrid = (q) => (q.bank_item_code || "").startsWith(GRID_PREFIX);

/** "P001 · Board Member 001" -> "Board Member 001" for compact labels. */
export const shortName = (label) => String(label || "").split(" · ").pop();

export function plural(n, one, many) {
  return `${n} ${n === 1 ? one : many || `${one}s`}`;
}

/** Where a question came from, in plain words. */
export function origin(q) {
  if (q.text_source === "ai_new") return "Proposed by AI";
  if (q.text_source === "consultant_written") return `Written by ${q.added_by || "a consultant"}`;
  const code = q.bank_item_code ? `${q.bank_item_code} v${q.bank_item_version}` : "Bank";
  return q.added_by ? `${code} · added by ${q.added_by}` : code;
}

/** Questions the participant will actually get (not removed; AI proposals only once accepted). */
export function isActive(q) {
  return q.status !== "removed" && !(q.text_source === "ai_new" && q.suggestion_status !== "accepted");
}

/** A wording suggestion still waiting for a decision. */
export const hasOpenWording = (q) => !!q.ai_text && q.text_source === "bank" && !q.suggestion_status && q.status !== "removed";
export const isPendingNew = (q) => q.text_source === "ai_new" && q.suggestion_status === "pending";

const EVENT_LABELS = {
  use_bank: "kept the bank wording",
  use_ai: "used the AI wording",
  edit: "edited the wording",
  accept_new: "accepted an AI-proposed question",
  reject_new: "rejected an AI-proposed question",
  regenerate: "asked for a new suggestion",
  edit_tags: "changed the tags",
  remove: "removed a question",
  restore: "restored a question",
  add_from_bank: "added a question from the bank",
  add_written: "wrote a question",
  move: "moved a question",
  approve: "approved the set",
  reopen: "reopened the set",
  lock: "locked the set",
};
export const eventLabel = (e) => EVENT_LABELS[e.action] || e.action;
