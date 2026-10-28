/** Labels for the Findings pages: plain words, never codes. */

export const KIND_LABELS = {
  strength: "Strength",
  concern: "Concern",
  observation: "Observation",
  compliance_gap: "Compliance gap",
  self_perception_gap: "Self-perception gap",
};
export const KIND_TONES = {
  strength: "green",
  concern: "red",
  observation: "blue",
  compliance_gap: "amber",
  self_perception_gap: "purple",
};
export const SUPPORT_LABELS = {
  strong: "Strong support",
  moderate: "Moderate support",
  limited: "Limited support",
  conflicting: "Conflicting views",
};
export const ORIGIN_LABELS = { computed: "Drafted from the numbers", ai: "Drafted by AI", consultant: "Added by a consultant" };
export const STATUS_LABELS = { draft: "Draft", accepted: "Accepted", edited: "Accepted (edited)", rejected: "Rejected" };
export const KIND_ORDER = ["compliance_gap", "concern", "self_perception_gap", "observation", "strength"];

export const SUBJECT_KIND_LABELS = {
  board: "The board",
  committee: "Committee",
  person: "Director",
  secretariat: "Company secretariat",
};
export const ROLE_LABELS = {
  BOARD: "Board",
  COMMITTEE: "Committee",
  CHAIR: "Chair",
  MD_CEO: "MD/CEO",
  ED: "Executive director",
  NED: "Non-executive director",
  INED: "Independent non-executive director",
  COMPANY_SECRETARY: "Company secretariat",
};

export const isAccepted = (f) => f.status === "accepted" || f.status === "edited";

export function fmt(x) {
  return x === null || x === undefined ? "—" : Number(x).toFixed(1);
}

export function plural(n, one, many) {
  return `${n} ${n === 1 ? one : many || `${one}s`}`;
}
