/** Display formatting shared by the consultant app and the member portal. */

// Fixed three-letter months: browser locales differ ("Sept" vs "Sep")
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** "2025-09-01" -> "1 Sep 2025". A plain date is shown as written, with no time zone shift. */
export function formatDate(iso) {
  if (!iso) return "—";
  const plain = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(iso));
  if (plain) return `${Number(plain[3])} ${MONTHS[Number(plain[2]) - 1]} ${plain[1]}`;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return String(iso);
  return `${d.getDate()} ${MONTHS[d.getMonth()]} ${d.getFullYear()}`;
}

/** "2026-10-27T09:48:11.25+00:00" -> "27 Oct 2026, 09:48" (local time). */
export function formatDateTime(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return String(iso);
  const time = `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
  return `${d.getDate()} ${MONTHS[d.getMonth()]} ${d.getFullYear()}, ${time}`;
}

/** "BOARD_AS_WHOLE" / "likert_5" -> "Board as whole" / "Likert 5". */
export function humanise(code) {
  if (!code) return "";
  const s = String(code).replace(/[_-]+/g, " ").trim().toLowerCase();
  return s.charAt(0).toUpperCase() + s.slice(1);
}
