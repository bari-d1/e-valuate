/** Labels for the Findings pages: plain words, never codes. */

export const KIND_LABELS = {
  strength: "Strength",
  concern: "Concern",
  observation: "Observation",
  practice_gap: "Practice differs from expectation (unverified)",
  self_perception_gap: "Self-perception gap",
};
export const KIND_TONES = {
  strength: "green",
  concern: "red",
  observation: "blue",
  practice_gap: "amber",
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
export const KIND_ORDER = ["practice_gap", "concern", "self_perception_gap", "observation", "strength"];

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

/**
 * Computed strengths, concerns and self/peer gaps come from the run's thresholds, which are the
 * client's to approve. Until they are, those findings are draft signals.
 */
export const DRAFT_SIGNAL_KINDS = ["strength", "concern", "self_perception_gap"];
export const THRESHOLD_LABELS = {
  theme_strength_mean: "Theme strength: average at least",
  item_strength_mean: "Clause-linked item strength: average at least",
  concern_mean: "Concern: average at most",
  self_peer_gap: "Self/peer gap: at least",
};
export const thresholdsApproved = (settings) => settings?.thresholds_status === "approved";
export const isDraftSignal = (f, settings) =>
  f.origin === "computed" && DRAFT_SIGNAL_KINDS.includes(f.kind) && !thresholdsApproved(settings);

/** Colour for an average, from the run's own thresholds (none recorded: no colour). */
export function scoreTone(mean, thresholds) {
  if (!thresholds || mean === null || mean === undefined) return "neutral";
  if (mean <= thresholds.concern_mean) return "low";
  if (mean >= thresholds.theme_strength_mean) return "high";
  return "neutral";
}

export function fmt(x) {
  return x === null || x === undefined ? "—" : Number(x).toFixed(1);
}

export function plural(n, one, many) {
  return `${n} ${n === 1 ? one : many || `${one}s`}`;
}
