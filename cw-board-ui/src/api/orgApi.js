/**
 * Organisations (companies), their documents, profile and governance codes.
 * Uses the same API base and consultant key headers as the rest of the consultant app.
 */
import { getConsultantHeaders } from "./consultantAuth.js";

export const API_BASE = import.meta.env.VITE_API_BASE || "http://127.0.0.1:8000";
const V1 = `${API_BASE}/api/v1`;

async function request(path, { method = "GET", body, form } = {}) {
  const headers = getConsultantHeaders({ Accept: "application/json" });
  let payload;
  if (form) {
    payload = form; // the browser sets the multipart boundary
  } else if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }
  const res = await fetch(`${V1}${path}`, { method, headers, body: payload });
  const text = await res.text();
  let data = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = text;
  }
  if (!res.ok) {
    const detail = data && typeof data === "object" ? data.detail : data;
    const message = typeof detail === "string" ? detail : detail ? JSON.stringify(detail) : `Request failed (${res.status})`;
    const err = new Error(message);
    err.status = res.status;
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
