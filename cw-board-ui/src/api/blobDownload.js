/**
 * Save a Blob as a local file. Browsers often block <a download> clicks that run
 * after an async fetch; prefer the File System Access API when available.
 */

function extensionFromFilename(filename) {
  const m = /\.([a-z0-9]+)$/i.exec(String(filename || ""));
  return (m?.[1] || "bin").toLowerCase();
}

function mimeForExtension(ext) {
  if (ext === "xlsx") {
    return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";
  }
  if (ext === "csv") {
    return "text/csv";
  }
  return "application/octet-stream";
}

function pickerTypesForFilename(filename) {
  const ext = extensionFromFilename(filename);
  const mime = mimeForExtension(ext);
  const label = ext === "xlsx" ? "Excel workbook" : ext === "csv" ? "CSV file" : "File";
  return [{ description: label, accept: { [mime]: [`.${ext}`] } }];
}

/**
 * @returns {Promise<{ method: 'picker'|'anchor', filename: string, objectUrl: string|null, needsManualLink: boolean, aborted?: boolean }>}
 */
export async function saveBlobAsFile(blob, filename) {
  const safeName = String(filename || "download").trim() || "download";

  if (typeof window.showSaveFilePicker === "function") {
    try {
      const handle = await window.showSaveFilePicker({
        suggestedName: safeName,
        types: pickerTypesForFilename(safeName),
      });
      const writable = await handle.createWritable();
      await writable.write(blob);
      await writable.close();
      return { method: "picker", filename: safeName, objectUrl: null, needsManualLink: false };
    } catch (e) {
      if (e?.name === "AbortError") {
        return { method: "picker", filename: safeName, objectUrl: null, needsManualLink: false, aborted: true };
      }
      // Fall through to anchor when picker fails for other reasons (e.g. policy).
    }
  }

  const objectUrl = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = objectUrl;
  a.download = safeName;
  a.rel = "noopener";
  document.body.appendChild(a);
  a.click();
  a.remove();

  return {
    method: "anchor",
    filename: safeName,
    objectUrl,
    needsManualLink: true,
  };
}

export function revokeBlobObjectUrl(objectUrl) {
  if (objectUrl) {
    URL.revokeObjectURL(objectUrl);
  }
}

export async function readHttpErrorMessage(res) {
  const text = await res.text();
  if (!text) return `Request failed (${res.status})`;
  try {
    const data = JSON.parse(text);
    if (typeof data?.detail === "string") return data.detail;
    if (data?.detail != null) return JSON.stringify(data.detail);
  } catch {
    /* plain text */
  }
  return text;
}
