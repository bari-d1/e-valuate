/**
 * Parse portal API errors and handle hub vs assignment token confusion.
 */

/**
 * @param {unknown} err
 * @returns {{ code: string, hubUrl?: string, hubPath?: string, message: string } | null}
 */
export function getHubTokenMisroute(err) {
  if (!err || typeof err !== "object") return null;
  if (err.code === "hub_token_not_assignment") {
    return {
      code: err.code,
      hubUrl: err.hubUrl || err.hub_url,
      hubPath: err.hubPath || err.hub_path,
      message: err.message || "This link opens your task hub, not a single questionnaire.",
    };
  }
  return null;
}

/**
 * @param {string} raw — response body text or JSON string
 */
export function parsePortalApiDetail(raw) {
  const text = String(raw || "").trim();
  if (!text) return null;
  try {
    const j = JSON.parse(text);
    const d = j.detail;
    if (typeof d === "object" && d?.code === "hub_token_not_assignment") {
      return d;
    }
    if (typeof d === "string") {
      try {
        const inner = JSON.parse(d);
        if (inner?.code === "hub_token_not_assignment") return inner;
      } catch {
        /* not nested json */
      }
    }
  } catch {
    /* not json */
  }
  return null;
}

/**
 * @param {import('react-router-dom').NavigateFunction} nav
 * @param {string} token — raw token from route (hub token)
 * @param {{ hubUrl?: string, hubPath?: string }} misroute
 * @returns {boolean} true if redirect was triggered
 */
export function redirectToHubFromMisroute(nav, token, misroute) {
  const path = (misroute?.hubPath || "").trim();
  if (path) {
    nav(path, { replace: true });
    return true;
  }
  const url = (misroute?.hubUrl || "").trim();
  if (url) {
    try {
      const u = new URL(url);
      nav(`${u.pathname}${u.search}${u.hash}`, { replace: true });
      return true;
    } catch {
      /* fall through */
    }
  }
  const t = String(token || "").trim();
  if (t) {
    nav(`/member/hub/${encodeURIComponent(t)}`, { replace: true });
    return true;
  }
  return false;
}

/**
 * Wrap a fetch error into an Error with hub misroute metadata when applicable.
 * @param {Response} r
 */
export async function throwPortalLoadError(r) {
  const text = await r.text();
  const detail = parsePortalApiDetail(text);
  if (detail?.code === "hub_token_not_assignment") {
    const err = new Error(
      detail.message ||
        "This is your personal hub link. Open it to see all your questionnaire tasks."
    );
    err.code = "hub_token_not_assignment";
    err.hubUrl = detail.hub_url;
    err.hubPath = detail.hub_path;
    throw err;
  }
  let msg = text;
  try {
    const j = JSON.parse(text);
    msg = typeof j.detail === "string" ? j.detail : text;
  } catch {
    /* keep text */
  }
  throw new Error(msg);
}
