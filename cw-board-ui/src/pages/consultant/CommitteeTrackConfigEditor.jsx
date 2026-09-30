import React from "react";

/**
 * Structured editor for COMMITTEE_EVAL track config.
 */

export default function CommitteeTrackConfigEditor({
  ui,
  state,
  onChange,
  participants,
  disabled,
}) {
  const { Field, Button, Badge } = ui;
  const [newCommitteeName, setNewCommitteeName] = React.useState("");

  const participantList = Array.isArray(participants) ? participants : [];

  const updateState = (patch) => {
    onChange({ ...state, ...patch });
  };

  const addCommittee = () => {
    const name = String(newCommitteeName || "").trim();
    if (!name) return;
    const existing = state.committees || [];
    if (existing.some((c) => c.toLowerCase() === name.toLowerCase())) {
      return;
    }
    const committees = [...existing, name];
    const membershipByCommittee = {
      ...(state.membershipByCommittee || {}),
      [name]: { mode: "all", emails: [] },
    };
    updateState({ committees, membershipByCommittee });
    setNewCommitteeName("");
  };

  const removeCommittee = (name) => {
    const committees = (state.committees || []).filter((c) => c !== name);
    const membershipByCommittee = { ...(state.membershipByCommittee || {}) };
    delete membershipByCommittee[name];
    updateState({ committees, membershipByCommittee });
  };

  const setMembershipMode = (committeeName, mode) => {
    const row = state.membershipByCommittee?.[committeeName] || { mode: "all", emails: [] };
    updateState({
      membershipByCommittee: {
        ...(state.membershipByCommittee || {}),
        [committeeName]: {
          mode,
          emails: mode === "all" ? [] : row.emails || [],
        },
      },
    });
  };

  const toggleMemberEmail = (committeeName, email) => {
    const norm = String(email || "").trim().toLowerCase();
    const row = state.membershipByCommittee?.[committeeName] || { mode: "selected", emails: [] };
    const set = new Set(row.emails || []);
    if (set.has(norm)) set.delete(norm);
    else set.add(norm);
    updateState({
      membershipByCommittee: {
        ...(state.membershipByCommittee || {}),
        [committeeName]: { mode: "selected", emails: [...set] },
      },
    });
  };

  const committees = state.committees || [];

  return (
    <div
      style={{
        padding: 12,
        borderRadius: 12,
        border: "1px solid #BFDBFE",
        background: "#F8FAFC",
      }}
    >
      <div style={{ fontWeight: 900, fontSize: 13, marginBottom: 6 }}>Committee evaluation setup</div>
      <div style={{ fontSize: 12, color: "#64748B", marginBottom: 10, lineHeight: 1.45 }}>
        Add each committee to assess. By default every invited participant can complete each committee questionnaire;
        restrict membership per committee when only some directors sit on that committee.
      </div>

      {participantList.length === 0 ? (
        <div
          style={{
            marginBottom: 10,
            padding: 10,
            borderRadius: 10,
            background: "#FFFBEB",
            border: "1px solid #FDE68A",
            fontSize: 12,
            color: "#92400E",
          }}
        >
          <b>No participants yet.</b> You can add committee names now; invite participants before saving or generating
          assignments. Restricted membership requires people on the roster.
        </div>
      ) : null}

      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center", marginBottom: 10 }}>
        <input
          type="text"
          value={newCommitteeName}
          onChange={(e) => setNewCommitteeName(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              addCommittee();
            }
          }}
          placeholder="e.g. Audit, Risk, Remuneration"
          disabled={disabled}
          style={{
            flex: "1 1 200px",
            minWidth: 160,
            padding: "8px 10px",
            borderRadius: 10,
            border: "1px solid #E5E7EB",
            fontSize: 13,
          }}
        />
        <Button variant="soft" disabled={disabled || !String(newCommitteeName || "").trim()} onClick={addCommittee}>
          Add committee
        </Button>
      </div>

      {committees.length === 0 ? (
        <div style={{ fontSize: 12, color: "#64748B" }}>No committees added yet.</div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {committees.map((cname) => {
            const row = state.membershipByCommittee?.[cname] || { mode: "all", emails: [] };
            const mode = row.mode === "selected" ? "selected" : "all";
            return (
              <div
                key={cname}
                style={{
                  padding: 10,
                  borderRadius: 10,
                  border: "1px solid #E5E7EB",
                  background: "white",
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8 }}>
                  <span style={{ fontWeight: 900, fontSize: 13 }}>{cname}</span>
                  <Button variant="soft" disabled={disabled} onClick={() => removeCommittee(cname)}>
                    Remove
                  </Button>
                </div>

                <div style={{ marginTop: 10, fontSize: 12, fontWeight: 800, color: "#475569" }}>Who can respond</div>
                <label style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 6, fontSize: 13, cursor: disabled ? "default" : "pointer" }}>
                  <input
                    type="radio"
                    name={`membership-${cname}`}
                    checked={mode === "all"}
                    disabled={disabled}
                    onChange={() => setMembershipMode(cname, "all")}
                  />
                  All invited participants
                </label>
                <label style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 4, fontSize: 13, cursor: disabled ? "default" : "pointer" }}>
                  <input
                    type="radio"
                    name={`membership-${cname}`}
                    checked={mode === "selected"}
                    disabled={disabled}
                    onChange={() => setMembershipMode(cname, "selected")}
                  />
                  Only selected members
                </label>

                {mode === "selected" ? (
                  <div style={{ marginTop: 8, paddingLeft: 4 }}>
                    {participantList.length === 0 ? (
                      <span style={{ fontSize: 12, color: "#B45309" }}>Invite participants to select members.</span>
                    ) : (
                      <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                        {participantList.map((p) => {
                          const email = String(p.email || "").trim().toLowerCase();
                          const checked = (row.emails || []).includes(email);
                          return (
                            <label
                              key={email || p.participant_id}
                              style={{
                                display: "flex",
                                gap: 8,
                                alignItems: "center",
                                fontSize: 12,
                                cursor: disabled ? "default" : "pointer",
                              }}
                            >
                              <input
                                type="checkbox"
                                checked={checked}
                                disabled={disabled}
                                onChange={() => toggleMemberEmail(cname, email)}
                              />
                              <span>
                                {[p.full_name, p.email].filter(Boolean).join(" — ") || p.email}
                                {p.role ? (
                                  <span style={{ marginLeft: 6 }}>
                                    <Badge tone="gray">{p.role}</Badge>
                                  </span>
                                ) : null}
                              </span>
                            </label>
                          );
                        })}
                      </div>
                    )}
                  </div>
                ) : null}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
