import React, { useCallback, useEffect, useState } from "react";
import { NavLink, Navigate, useNavigate, useParams } from "react-router-dom";
import { SECTOR_OPTIONS, orgApi, sectorFromOption, sectorLabel } from "../../../api/orgApi.js";
import { color, font, radius, space } from "../../../theme.js";
import BoardMemberPage from "./BoardMemberPage.jsx";
import BoardTab from "./BoardTab.jsx";
import Modal from "./Modal.jsx";
import CommitteesTab from "./CommitteesTab.jsx";
import DocumentsTab from "./DocumentsTab.jsx";
import EvaluationsTab from "./EvaluationsTab.jsx";
import GovernanceCodesTab from "./GovernanceCodesTab.jsx";
import ProfileTab from "./ProfileTab.jsx";
import { Notice, Panel } from "./shared.jsx";
import { inputCss, useAsync } from "./helpers.js";

const TABS = [
  { key: "documents", label: "Documents", Component: DocumentsTab },
  { key: "profile", label: "Profile", Component: ProfileTab },
  { key: "board", label: "Board", Component: BoardTab },
  { key: "committees", label: "Committees", Component: CommitteesTab },
  { key: "codes", label: "Governance codes", Component: GovernanceCodesTab },
  { key: "evaluations", label: "Evaluations", Component: EvaluationsTab },
];

function tabStyle(active) {
  return {
    padding: "8px 14px",
    borderRadius: radius.sm,
    textDecoration: "none",
    fontSize: font.body,
    fontWeight: active ? font.weight.heavy : font.weight.medium,
    color: active ? color.primaryText : color.textMuted,
    background: active ? color.primarySoft : "transparent",
    border: `1px solid ${active ? color.primarySoftBorder : "transparent"}`,
    whiteSpace: "nowrap",
  };
}

function EditDetails({ ui, org, onSaved, onCancel }) {
  const { Button, Field } = ui;
  const { busy, error, run } = useAsync();
  const [name, setName] = useState(org.name);
  const current = org.sector_sub_type ? `${org.sector_key}/${org.sector_sub_type}` : org.sector_key || "";
  const [sector, setSector] = useState(current);

  const save = () =>
    run(async () => {
      const body = { name: name.trim() };
      if (sector !== current) Object.assign(body, sectorFromOption(sector));
      onSaved(await orgApi.update(org.organisation_id, body));
    });

  return (
    <Panel style={{ marginTop: space.md }}>
      {error ? <Notice tone="error">{error}</Notice> : null}
      <div style={{ display: "grid", gap: space.md, gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", alignItems: "end" }}>
        <Field label="Company name">
          <input value={name} onChange={(e) => setName(e.target.value)} style={inputCss()} />
        </Field>
        <Field label="Sector" hint="Changing it replaces the sector's default governance codes.">
          <select value={sector} onChange={(e) => setSector(e.target.value)} style={inputCss()}>
            <option value="">Not set</option>
            {SECTOR_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </Field>
        <div style={{ display: "flex", gap: space.sm, flexWrap: "wrap" }}>
          <Button onClick={save} disabled={busy || !name.trim()}>
            {busy ? "Saving…" : "Save"}
          </Button>
          <Button variant="secondary" onClick={onCancel} disabled={busy}>
            Cancel
          </Button>
        </div>
      </div>
    </Panel>
  );
}

export default function CompanyPage({ ui, onEvaluationCreatedPath }) {
  const { Badge, Button, Card } = ui;
  const { orgId, tab, memberId } = useParams();
  const navigate = useNavigate();
  const { error, run } = useAsync();
  const [org, setOrg] = useState(null);
  const [registry, setRegistry] = useState(null);
  const [editing, setEditing] = useState(false);
  const [boardVersion, setBoardVersion] = useState(0); // reloads the board list after the member dialog closes

  const reloadOrg = useCallback(() => run(async () => setOrg(await orgApi.get(orgId))), [orgId, run]);
  useEffect(() => {
    reloadOrg();
    run(async () => setRegistry(await orgApi.registry()));
  }, [reloadOrg, run]);

  const active = TABS.find((t) => t.key === tab);
  if (!active) return <Navigate to={`/consultant/companies/${orgId}/documents`} replace />;
  const Component = active.Component;
  const memberOpen = tab === "board" && !!memberId;
  const closeMember = () => {
    setBoardVersion((v) => v + 1);
    navigate(`/consultant/companies/${orgId}/board`);
  };

  return (
    <Card
      title={org ? org.name : "Company"}
      subtitle={
        org
          ? `${sectorLabel(org.sector_key, org.sector_sub_type)} · Profile version ${org.profile_version}`
          : "Loading…"
      }
      right={
        org ? (
          <div style={{ display: "flex", gap: space.sm, alignItems: "center", flexWrap: "wrap" }}>
            {org.profile_status === "reviewed" ? (
              <Badge tone="green">Profile reviewed</Badge>
            ) : (
              <Badge tone="amber">Profile draft</Badge>
            )}
            {!editing ? (
              <Button variant="secondary" onClick={() => setEditing(true)}>
                Edit details
              </Button>
            ) : null}
          </div>
        ) : null
      }
    >
      <p style={{ margin: `0 0 ${space.md}px` }}>
        <a
          href="/consultant/companies"
          onClick={(e) => {
            e.preventDefault();
            navigate("/consultant/companies");
          }}
          style={{ fontSize: 13, color: color.primaryText }}
        >
          ← All companies
        </a>
      </p>

      {error ? <Notice tone="error">{error}</Notice> : null}
      {editing && org ? (
        <EditDetails
          ui={ui}
          org={org}
          onSaved={(updated) => {
            setOrg(updated);
            setEditing(false);
          }}
          onCancel={() => setEditing(false)}
        />
      ) : null}

      <nav
        aria-label="Company sections"
        style={{ display: "flex", gap: 6, overflowX: "auto", margin: `${space.lg}px 0`, paddingBottom: 2 }}
      >
        {TABS.map((t) => (
          <NavLink key={t.key} to={`/consultant/companies/${orgId}/${t.key}`} style={({ isActive }) => tabStyle(isActive)}>
            {t.label}
            {t.key === "profile" && org && org.open_proposals && org.open_proposals.facts + org.open_proposals.committees > 0 ? (
              <span style={{ marginLeft: 6 }}>
                <Badge tone="amber">{org.open_proposals.facts + org.open_proposals.committees}</Badge>
              </span>
            ) : null}
          </NavLink>
        ))}
      </nav>

      {org && registry ? (
        <Component
          ui={ui}
          org={org}
          registry={registry}
          reloadOrg={reloadOrg}
          onEvaluationCreatedPath={onEvaluationCreatedPath}
          refreshKey={boardVersion}
        />
      ) : (
        <p style={{ color: color.textMuted }}>Loading…</p>
      )}

      {/* A board member opens over the board list; the URL keeps a direct link to them */}
      {memberOpen && org && registry ? (
        <Modal labelledBy="board-member-title" onClose={closeMember}>
          <BoardMemberPage key={memberId} ui={ui} org={org} memberId={memberId} />
        </Modal>
      ) : null}
    </Card>
  );
}
