/**
 * Organisations (companies), their documents, profile and governance codes.
 * Uses the same API base and consultant key headers as the rest of the consultant app.
 */
import { getConsultantHeaders } from "./consultantAuth.js";

export const API_BASE = import.meta.env.VITE_API_BASE || "http://127.0.0.1:8000";
const V1 = `${API_BASE}/api/v1`;

export const NETWORK_ERROR = "Couldn't reach the server. Check it's running and try again.";

const FIELD_LABELS = { full_name: "Name", email: "Email", display_code: "Display code", name: "Name" };

// FastAPI validation errors ([{loc, msg}]) as "Name: String should have at most 255 characters"
export function validationMessage(detail) {
  return detail
    .map((d) => {
      const field = Array.isArray(d?.loc) ? d.loc[d.loc.length - 1] : "";
      const label = FIELD_LABELS[field] || (typeof field === "string" ? field.replace(/_/g, " ") : "");
      return label ? `${label}: ${d?.msg || "invalid"}` : d?.msg || "";
    })
    .filter(Boolean)
    .join("; ");
}

export async function request(path, { method = "GET", body, form, headers: extra } = {}) {
  const headers = getConsultantHeaders({ Accept: "application/json", ...(extra || {}) });
  let payload;
  if (form) {
    payload = form; // the browser sets the multipart boundary
  } else if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }
  let res;
  try {
    res = await fetch(`${V1}${path}`, { method, headers, body: payload });
  } catch {
    throw new Error(NETWORK_ERROR);
  }
  const text = await res.text();
  let data = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = text;
  }
  if (!res.ok) {
    const detail = data && typeof data === "object" ? data.detail : data;
    const message =
      typeof detail === "string"
        ? detail
        : Array.isArray(detail)
          ? validationMessage(detail)
          : detail?.message || (detail ? JSON.stringify(detail) : `Request failed (${res.status})`);
    const err = new Error(message);
    err.status = res.status;
    // Validation errors listed one by one (e.g. the question bank)
    if (Array.isArray(detail?.errors)) err.errors = detail.errors;
    throw err;
  }
  return data;
}

const org = (id) => `/organisations/${encodeURIComponent(id)}`;

export const orgApi = {
  registry: () => request("/org-profile/registry"),
  list: () => request("/organisations"),
  create: (body) => request("/organisations", { method: "POST", body }),
  get: (id) => request(org(id)),
  update: (id, body) => request(org(id), { method: "PATCH", body }),

  documents: (id) => request(`${org(id)}/documents`),
  upload: (id, docType, file) => {
    const form = new FormData();
    form.append("doc_type", docType);
    form.append("file", file);
    return request(`${org(id)}/documents`, { method: "POST", form });
  },
  deleteDocument: (id, docId) => request(`${org(id)}/documents/${docId}`, { method: "DELETE" }),
  downloadUrl: (id, docId) => `${V1}${org(id)}/documents/${docId}/download`,
  extract: (id) => request(`${org(id)}/extraction`, { method: "POST" }),

  facts: (id) => request(`${org(id)}/facts`),
  addFact: (id, body) => request(`${org(id)}/facts`, { method: "POST", body }),
  updateFact: (id, factId, body) => request(`${org(id)}/facts/${factId}`, { method: "PATCH", body }),
  confirmFact: (id, factId, body) => request(`${org(id)}/facts/${factId}/confirm`, { method: "POST", body: body || {} }),
  rejectFact: (id, factId) => request(`${org(id)}/facts/${factId}/reject`, { method: "POST" }),
  deleteFact: (id, factId) => request(`${org(id)}/facts/${factId}`, { method: "DELETE" }),

  committees: (id) => request(`${org(id)}/committees`),
  addCommittee: (id, body) => request(`${org(id)}/committees`, { method: "POST", body }),
  updateCommittee: (id, cId, body) => request(`${org(id)}/committees/${cId}`, { method: "PATCH", body }),
  confirmCommittee: (id, cId, body) => request(`${org(id)}/committees/${cId}/confirm`, { method: "POST", body: body || {} }),
  rejectCommittee: (id, cId) => request(`${org(id)}/committees/${cId}/reject`, { method: "POST" }),
  deleteCommittee: (id, cId) => request(`${org(id)}/committees/${cId}`, { method: "DELETE" }),

  markReviewed: (id) => request(`${org(id)}/mark-reviewed`, { method: "POST" }),

  codes: (id) => request(`${org(id)}/governance-codes`),
  setCodes: (id, codes) => request(`${org(id)}/governance-codes`, { method: "PUT", body: { codes } }),
  allCodes: () => request("/governance-codes"),

  evaluations: () => request("/evaluations"),
  taxonomy: () => request("/taxonomy"),
};

const member = (id, mId) => `${org(id)}/board-members/${encodeURIComponent(mId)}`;

export const boardApi = {
  registry: () => request("/board-member-profile/registry"),
  list: (id) => request(`${org(id)}/board-members`),
  create: (id, body) => request(`${org(id)}/board-members`, { method: "POST", body }),
  get: (id, mId) => request(member(id, mId)),
  update: (id, mId, body) => request(member(id, mId), { method: "PATCH", body }),
  deactivate: (id, mId) => request(`${member(id, mId)}/deactivate`, { method: "POST" }),

  documents: (id, mId) => request(`${member(id, mId)}/documents`),
  upload: (id, mId, file) => {
    const form = new FormData();
    form.append("file", file);
    return request(`${member(id, mId)}/documents`, { method: "POST", form });
  },
  deleteDocument: (id, mId, docId) => request(`${member(id, mId)}/documents/${docId}`, { method: "DELETE" }),
  extract: (id, mId) => request(`${member(id, mId)}/extraction`, { method: "POST" }),

  facts: (id, mId) => request(`${member(id, mId)}/facts`),
  addFact: (id, mId, body) => request(`${member(id, mId)}/facts`, { method: "POST", body }),
  updateFact: (id, mId, factId, body) => request(`${member(id, mId)}/facts/${factId}`, { method: "PATCH", body }),
  confirmFact: (id, mId, factId, body) => request(`${member(id, mId)}/facts/${factId}/confirm`, { method: "POST", body: body || {} }),
  rejectFact: (id, mId, factId) => request(`${member(id, mId)}/facts/${factId}/reject`, { method: "POST" }),
  deleteFact: (id, mId, factId) => request(`${member(id, mId)}/facts/${factId}`, { method: "DELETE" }),
  markReviewed: (id, mId) => request(`${member(id, mId)}/mark-reviewed`, { method: "POST" }),

  memberships: (id) => request(`${org(id)}/committee-memberships`),
  match: (id) => request(`${org(id)}/committee-memberships/match`, { method: "POST" }),
  addMembership: (id, body) => request(`${org(id)}/committee-memberships`, { method: "POST", body }),
  confirmMembership: (id, msId, body) => request(`${org(id)}/committee-memberships/${msId}/confirm`, { method: "POST", body: body || {} }),
  rejectMembership: (id, msId) => request(`${org(id)}/committee-memberships/${msId}/reject`, { method: "POST" }),
  deleteMembership: (id, msId) => request(`${org(id)}/committee-memberships/${msId}`, { method: "DELETE" }),
};

const ev = (evalId) => `/evaluations/${encodeURIComponent(evalId)}`;

export const evaluationApi = {
  get: (evalId) => request(ev(evalId)),
  update: (evalId, body) => request(ev(evalId), { method: "PATCH", body }),
};

export const readinessApi = {
  readiness: (evalId) => request(`${ev(evalId)}/readiness`),
  fromBoardMembers: (evalId, boardMemberIds) =>
    request(`${ev(evalId)}/participants/from-board-members`, {
      method: "POST",
      body: boardMemberIds ? { board_member_ids: boardMemberIds } : {},
    }),
};

/** Download a stored document with the consultant headers (a plain link can't send them). */
export async function downloadDocument(id, docId, filename) {
  const res = await fetch(orgApi.downloadUrl(id, docId), { headers: getConsultantHeaders() });
  if (!res.ok) throw new Error("Download failed.");
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename || "document";
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export const SECTOR_OPTIONS = [
  { value: "insurance", label: "Insurance" },
  { value: "banking", label: "Banking (commercial, merchant, non-interest, payment service)" },
  { value: "banking/microfinance", label: "Banking — microfinance" },
  { value: "pension", label: "Pension" },
  { value: "telecommunications", label: "Telecommunications" },
  { value: "sme", label: "SME" },
  { value: "finance", label: "Finance (other)" },
];

export function sectorLabel(key, subType) {
  if (!key) return "Not set";
  const v = subType ? `${key}/${subType}` : key;
  return SECTOR_OPTIONS.find((o) => o.value === v)?.label.split(" (")[0] || key;
}

export function sectorFromOption(value) {
  if (!value) return { sector_key: null, sector_sub_type: null };
  const [key, sub] = value.split("/");
  return { sector_key: key, sector_sub_type: sub || null };
}

export const SOURCE_LABELS = { public: "Public", client: "Client", consultant: "Consultant" };
