/** Display formatting shared by the consultant app and the member portal. */

/** "2026-10-27T09:48:11.25+00:00" -> "27 Oct 2026, 09:48" (local time). */
export function formatDateTime(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return String(iso);
  return d.toLocaleString(undefined, { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

/** "BOARD_AS_WHOLE" / "likert_5" -> "Board as whole" / "Likert 5". */
export function humanise(code) {
  if (!code) return "";
  const s = String(code).replace(/[_-]+/g, " ").trim().toLowerCase();
  return s.charAt(0).toUpperCase() + s.slice(1);
}
