import React, { useCallback, useEffect, useRef, useState } from "react";
import { downloadDocument, orgApi } from "../../../api/orgApi.js";
import { color, font, space } from "../../../theme.js";
import { DroppedItems, LinkButton, Notice, Panel, SectionTitle } from "./shared.jsx";
import { formatDate, useAsync } from "./helpers.js";

function sizeLabel(bytes) {
  if (bytes >= 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  return `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

function StatusBadge({ ui, doc }) {
  const { Badge } = ui;
  if (doc.extraction_status === "done") return <Badge tone="green">Text read</Badge>;
  if (doc.extraction_status === "failed") return <Badge tone="red">Couldn't read text</Badge>;
  return <Badge tone="gray">Waiting</Badge>;
}

function Slot({ ui, org, type, docs, onChanged }) {
  const { Badge, Button } = ui;
  const input = useRef(null);
  const { busy, error, run } = useAsync();
  const inputId = `upload-${type.key}`;

  const upload = (file) =>
    run(async () => {
      await orgApi.upload(org.organisation_id, type.key, file);
      await onChanged();
    });

  const remove = (doc) => {
    if (!window.confirm(`Delete "${doc.filename}"? The stored file is deleted too.`)) return;
    run(async () => {
      await orgApi.deleteDocument(org.organisation_id, doc.document_id);
      await onChanged();
    });
  };

  return (
    <Panel>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: space.sm, flexWrap: "wrap" }}>
        <h3 style={{ margin: 0, fontSize: font.body, fontWeight: font.weight.heavy, color: color.text }}>{type.label}</h3>
        {docs.length === 0 ? <Badge tone="gray">Missing</Badge> : <Badge tone="blue">{docs.length} file{docs.length === 1 ? "" : "s"}</Badge>}
      </div>

      {docs.length ? (
        <ul style={{ listStyle: "none", padding: 0, margin: `${space.sm}px 0 0`, display: "grid", gap: space.sm }}>
          {docs.map((d) => (
            <li key={d.document_id} style={{ borderTop: `1px solid ${color.border}`, paddingTop: space.sm }}>
              <div style={{ fontWeight: font.weight.bold, color: color.text, wordBreak: "break-word" }}>{d.filename}</div>
              <div style={{ display: "flex", gap: space.sm, alignItems: "center", flexWrap: "wrap", marginTop: 4, fontSize: font.small, color: color.textMuted }}>
                <StatusBadge ui={ui} doc={d} />
                <span>
                  {sizeLabel(d.size_bytes)} · {formatDate(d.uploaded_at)}
                </span>
              </div>
              {d.extraction_status === "failed" && d.extraction_error ? (
                <div style={{ marginTop: 4, fontSize: font.small, color: color.danger }}>{d.extraction_error}</div>
              ) : null}
              <div style={{ display: "flex", gap: space.md, marginTop: 6 }}>
                <LinkButton onClick={() => run(() => downloadDocument(org.organisation_id, d.document_id, d.filename))} disabled={busy}>
                  Download
                </LinkButton>
                <LinkButton danger onClick={() => remove(d)} disabled={busy}>
                  Delete
                </LinkButton>
              </div>
            </li>
          ))}
        </ul>
      ) : null}

      {error ? (
        <div style={{ marginTop: space.sm }}>
          <Notice tone="error">{error}</Notice>
        </div>
      ) : null}

      <div style={{ marginTop: space.md }}>
        <label htmlFor={inputId} style={{ position: "absolute", width: 1, height: 1, overflow: "hidden", clip: "rect(0 0 0 0)" }}>
          Upload {type.label}
        </label>
        <input
          id={inputId}
          ref={input}
          type="file"
          accept=".pdf,.docx,.txt,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/plain"
          style={{ display: "none" }}
          onChange={(e) => {
            const file = e.target.files && e.target.files[0];
            e.target.value = "";
            if (file) upload(file);
          }}
        />
        <Button variant="secondary" onClick={() => input.current && input.current.click()} disabled={busy}>
          {busy ? "Working…" : docs.length ? "Upload another" : "Upload"}
        </Button>
      </div>
    </Panel>
  );
}

export default function DocumentsTab({ ui, org, registry, reloadOrg }) {
  const { Button } = ui;
  const [docs, setDocs] = useState(null);
  const { busy, error, run } = useAsync();
  const [summary, setSummary] = useState(null);

  const load = useCallback(() => run(async () => setDocs((await orgApi.documents(org.organisation_id)).items)), [org.organisation_id, run]);
  useEffect(() => {
    load();
  }, [load]);

  const extract = () =>
    run(async () => {
      setSummary(await orgApi.extract(org.organisation_id));
      await reloadOrg();
    });

  const readable = (docs || []).filter((d) => d.extraction_status === "done").length;

  return (
    <div>
      <SectionTitle hint="PDF, Word (.docx) or text files, up to 25 MB each. Text is read on upload so the profile can be checked against it.">
        Documents
      </SectionTitle>

      {registry.ai_extraction_enabled ? (
        <Panel style={{ marginBottom: space.lg }}>
          <div style={{ display: "flex", gap: space.md, alignItems: "center", flexWrap: "wrap" }}>
            <Button onClick={extract} disabled={busy || readable === 0} title={readable === 0 ? "Upload a document with readable text first" : undefined}>
              {busy ? "Extracting…" : "Extract profile"}
            </Button>
            <span style={{ fontSize: 13, color: color.textMuted }}>
              AI proposes facts and committees, each with a quote from the document. Nothing is saved until you confirm it on the Profile tab.
            </span>
          </div>
          {summary ? (
            <div style={{ marginTop: space.md }}>
              <Notice tone="success">
                {`Proposed ${summary.facts_added} new and updated ${summary.facts_updated} fact(s); ${summary.committees_added} new and ${summary.committees_updated} updated committee(s).`}
                {summary.skipped.length ? `\nSkipped: ${summary.skipped.map((s) => `${s.filename}${s.part ? ` (${s.part})` : ""}: ${s.reason}`).join("; ")}` : ""}
              </Notice>
              <DroppedItems items={summary.discarded} />
            </div>
          ) : null}
        </Panel>
      ) : null}

      {error ? (
        <div style={{ marginBottom: space.md }}>
          <Notice tone="error">{error}</Notice>
        </div>
      ) : null}

      {docs === null ? (
        <p style={{ color: color.textMuted }}>Loading…</p>
      ) : (
        <div style={{ display: "grid", gap: space.md, gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))" }}>
          {registry.doc_types.map((t) => (
            <Slot key={t.key} ui={ui} org={org} type={t} docs={docs.filter((d) => d.doc_type === t.key)} onChanged={load} />
          ))}
        </div>
      )}
    </div>
  );
}
