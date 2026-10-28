/** Labels and small helpers for the Responses (tracking) page. */

export const STATUS_TONES = {
  not_ready: "gray",
  ready: "blue",
  sent: "blue",
  opened: "purple",
  in_progress: "amber",
  submitted: "green",
  email_failed: "red",
};

// Order used when sorting by status: those needing attention first
export const STATUS_ORDER = ["email_failed", "sent", "opened", "in_progress", "ready", "not_ready", "submitted"];
export const OUTSTANDING = new Set(["sent", "email_failed", "opened", "in_progress"]);

/** "First reminder Mon 3 Nov" style dates from an ISO date. */
export function shortDate(iso) {
  if (!iso) return "";
  const d = new Date(`${iso.slice(0, 10)}T00:00:00`);
  return d.toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short" });
}

export function longDate(iso) {
  if (!iso) return "";
  const d = new Date(`${iso.slice(0, 10)}T00:00:00`);
  return d.toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" });
}

/** "just now", "3 hours ago", "2 days ago", or the date for anything older than a fortnight. */
export function ago(iso, now = Date.now()) {
  if (!iso) return "—";
  const min = Math.round((now - new Date(iso).getTime()) / 60000);
  if (min < 2) return "just now";
  if (min < 60) return `${min} minutes ago`;
  const h = Math.round(min / 60);
  if (h < 24) return `${h} hour${h === 1 ? "" : "s"} ago`;
  const d = Math.round(h / 24);
  if (d < 14) return `${d} day${d === 1 ? "" : "s"} ago`;
  return shortDate(iso);
}

export function daysLeftText(days) {
  if (days === null || days === undefined) return "No deadline set";
  if (days < 0) return `Deadline passed ${-days} day${days === -1 ? "" : "s"} ago`;
  if (days === 0) return "Deadline is today";
  return `${days} day${days === 1 ? "" : "s"} to the deadline`;
}

/** "First reminder Mon 3 Nov, then Fri 7 Nov, final reminder Tue 11 Nov." */
export function scheduleSentence(slots) {
  if (!slots || !slots.length) return "No reminders fit before the deadline with these settings.";
  const regular = slots.filter((s) => !s.final).map((s) => shortDate(s.on));
  const final = slots.find((s) => s.final);
  const parts = [];
  if (regular.length) parts.push(`First reminder ${regular[0]}`);
  if (regular.length > 1) parts.push(`then ${regular.slice(1).join(", then ")}`);
  if (final) parts.push(`${regular.length ? "final reminder" : "Final reminder"} ${shortDate(final.on)}`);
  return `${parts.join(", ")}.`;
}
