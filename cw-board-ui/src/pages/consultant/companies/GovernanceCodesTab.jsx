import React, { useCallback, useEffect, useState } from "react";
import { orgApi } from "../../../api/orgApi.js";
import { color, font, space } from "../../../theme.js";
import { LinkButton, Notice, Panel, SectionTitle } from "./shared.jsx";
import { inputCss, useAsync } from "./helpers.js";

export default function GovernanceCodesTab({ ui, org }) {
  const { Badge, Button } = ui;
  const [linked, setLinked] = useState(null);
  const [all, setAll] = useState([]);
  const [toAdd, setToAdd] = useState("");
  const { busy, error, run } = useAsync();
  const id = org.organisation_id;

  const load = useCallback(
    () =>
      run(async () => {
        const [l, a] = await Promise.all([orgApi.codes(id), orgApi.allCodes()]);
        setLinked(l.items);
        setAll(a.items);
      }),
    [id, run]
  );
  useEffect(() => {
    load();
  }, [load]);

  const save = (codes) =>
    run(async () => {
      setLinked((await orgApi.setCodes(id, codes)).items);
      setToAdd("");
    });

  const linkedCodes = (linked || []).map((c) => c.code);
  const available = all.filter((c) => !linkedCodes.includes(c.code));

  return (
    <div>
      <SectionTitle hint="The codes this company is assessed against. Sector defaults are added automatically; add or remove codes as needed.">
        Governance codes
      </SectionTitle>
      {error ? <Notice tone="error">{error}</Notice> : null}

      {linked === null ? (
        <p style={{ color: color.textMuted }}>Loading…</p>
      ) : (
        <div style={{ display: "grid", gap: space.sm }}>
          {linked.length === 0 ? (
            <Panel>
              <p style={{ margin: 0, color: color.textMuted }}>
                No codes linked. Set the company's sector to add its defaults, or add codes below.
              </p>
            </Panel>
          ) : (
            linked.map((c) => (
              <Panel key={c.code}>
                <div style={{ display: "flex", justifyContent: "space-between", gap: space.sm, flexWrap: "wrap", alignItems: "center" }}>
                  <div style={{ minWidth: 0 }}>
                    <div style={{ fontWeight: font.weight.heavy, color: color.text }}>{c.title}</div>
                    <div style={{ fontSize: font.small, color: color.textMuted }}>
                      {c.code} · {c.issuer}
                    </div>
                  </div>
                  <div style={{ display: "flex", gap: space.sm, alignItems: "center", flexWrap: "wrap" }}>
                    {c.source === "sector_default" ? <Badge tone="blue">Sector default</Badge> : <Badge tone="gray">Added manually</Badge>}
                    {c.status !== "current" ? <Badge tone="amber">{c.status === "historical" ? "Historical" : "Superseded"}</Badge> : null}
                    <LinkButton danger disabled={busy} onClick={() => save(linkedCodes.filter((x) => x !== c.code))}>
                      Remove
                    </LinkButton>
                  </div>
                </div>
              </Panel>
            ))
          )}

          <Panel style={{ background: color.surfaceMuted }}>
            <div style={{ display: "flex", gap: space.sm, flexWrap: "wrap", alignItems: "flex-end" }}>
              <label style={{ flex: "1 1 260px", fontSize: 13, fontWeight: font.weight.bold, color: color.text }}>
                Add a code
                <select value={toAdd} onChange={(e) => setToAdd(e.target.value)} style={inputCss({ marginTop: 4 })} disabled={!available.length}>
                  <option value="">{available.length ? "Choose a code…" : "All codes are linked"}</option>
                  {available.map((c) => (
                    <option key={c.code} value={c.code}>
                      {c.title} ({c.code}){c.status !== "current" ? ` — ${c.status}` : ""}
                    </option>
                  ))}
                </select>
              </label>
              <Button onClick={() => save([...linkedCodes, toAdd])} disabled={busy || !toAdd}>
                Add
              </Button>
            </div>
          </Panel>
        </div>
      )}
    </div>
  );
}
