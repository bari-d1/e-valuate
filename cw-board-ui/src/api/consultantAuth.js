/**

 * Consultant API key for protected backend routes.

 * Must match backend CONSULTANT_API_KEY when auth is enabled.

 */



import { readHttpErrorMessage, revokeBlobObjectUrl, saveBlobAsFile } from "./blobDownload.js";



const CONSULTANT_API_KEY = (import.meta.env.VITE_CONSULTANT_API_KEY || "").trim();



export function consultantAuthEnabled() {

  return !!CONSULTANT_API_KEY;

}



/** Headers to attach to consultant API calls (JSON and file downloads). */

export function getConsultantHeaders(extra = {}) {

  const headers = { ...extra };

  if (CONSULTANT_API_KEY) {

    headers["X-Consultant-Key"] = CONSULTANT_API_KEY;

  }

  return headers;

}



function parseFilenameFromContentDisposition(cd) {

  const match = /filename\*?=(?:UTF-8''|")?([^";]+)"?/i.exec(cd || "");

  if (!match) return null;

  try {

    return decodeURIComponent(match[1]);

  } catch {

    return match[1];

  }

}



/**

 * Download responses export (CSV or XLSX) with consultant API key when configured.

 *

 * @returns {Promise<{ filename: string, needsManualLink: boolean, objectUrl: string|null, bytes: number }>}

 */

export async function downloadResponsesExport(apiBase, evalId, format, filterParams = {}) {

  const q = new URLSearchParams({ format });

  for (const [k, v] of Object.entries(filterParams)) {

    if (v != null && String(v).trim() !== "") q.set(k, String(v).trim());

  }

  const base = (apiBase || "").replace(/\/$/, "");

  const url = `${base}/api/v1/evaluations/${encodeURIComponent(evalId)}/responses/export?${q}`;



  const res = await fetch(url, { headers: getConsultantHeaders() });

  if (!res.ok) {

    throw new Error(await readHttpErrorMessage(res));

  }



  const blob = await res.blob();

  if (!blob || blob.size === 0) {

    throw new Error("Export returned an empty file. Check filters or confirm responses exist for this evaluation.");

  }



  const cd = res.headers.get("content-disposition") || "";

  const ext = format === "xlsx" ? "xlsx" : "csv";

  const filename = parseFilenameFromContentDisposition(cd) || `${evalId}_responses.${ext}`;



  const save = await saveBlobAsFile(blob, filename);

  if (save.aborted) {

    throw new Error("Download cancelled.");

  }



  return {

    filename: save.filename,

    needsManualLink: save.needsManualLink,

    objectUrl: save.objectUrl,

    bytes: blob.size,

  };

}



/** Release a manual download link created by downloadResponsesExport. */

export function releaseResponsesExportUrl(objectUrl) {

  revokeBlobObjectUrl(objectUrl);

}


