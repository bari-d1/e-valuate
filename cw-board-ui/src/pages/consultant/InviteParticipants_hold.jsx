import React, { useMemo } from "react";

/**
 * src/pages/InviteParticipants.jsx
 * --------------------------------
 * Invite Participants page.
 *
 * Enhancements:
 * - Displays invite results (created + existing) after calling the invite endpoint.
 * - Shows "Email sent" success/failure per participant (based on backend response).
 * - Provides "Copy portal link" button per participant (useful in dev/testing).
 *
 * Expected backend response shape from:
 * POST /api/v1/evaluations/{evaluation_id}/participants/invite
 * {
 *   created_items: [{ email, full_name, role, portal_url, email_sent, email_error, ... }],
 *   existing_items: [{ ...same }],
 *   ...
 * }
 */
export default function InviteParticipantsPage({
  ui,
  busy,
  focus,
  inviteText,
  setInviteText,
  inviteParticipants,
  listParticipants,
  lockReason,
  setTask,
  renderNextActionBar,
  textareaStyle,

  // ✅ NEW: pass the shared result state from AppLegacy
  result,
}) {
  const { Card, Badge, Field, Button } = ui;

  const reasonEval = lockReason("evaluation");
  const disabled = busy || !!reasonEval;

  // ✅ Invite results are shown when the last action was invite_participants
  const inviteResult = result?.action === "invite_participants" ? result?.data : null;

  const inviteItems = useMemo(() => {
    if (!inviteResult) return [];
    const created = inviteResult.created_items || [];
    const existing = inviteResult.existing_items || [];
    // keep created first, then existing
    return [...created.map((x) => ({ ...x, _kind: "created" })), ...existing.map((x) => ({ ...x, _kind: "existing" }))];
  }, [inviteResult]);

  const emailOkCount = useMemo(() => inviteItems.filter((x) => x.email_sent === true).length, [inviteItems]);
  const emailFailCount = useMemo(() => inviteItems.filter((x) => x.email_sent === false).length, [inviteItems]);

  const copyToClipboard = async (text) => {
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      // fallback (older browsers)
      const ta = document.createElement("textarea");
      ta.value = text;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      document.body.removeChild(ta);
    }
  };

  return (
    <Card
      title="Invite Participants"
      subtitle="Add board members/directors to an evaluation (idempotent by email)."
      right={<Badge tone="blue">Consultant</Badge>}
    >
      <div style={{ marginTop: 6 }}>{focus}</div>

      <div style={{ marginTop: 14 }}>
        <Field
          label="Participants (one per line)"
          hint='Formats: "email" OR "email,Full Name" OR "email,Full Name,Role"'
        >
          <textarea
            value={inviteText}
            onChange={(e) => setInviteText(e.target.value)}
            style={textareaStyle(160)}
            spellCheck={false}
          />
        </Field>
      </div>

      <div
        style={{
          marginTop: 14,
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 12,
          flexWrap: "wrap",
        }}
      >
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
          <Button
            onClick={inviteParticipants}
            disabled={disabled}
            title={reasonEval || "Invite participants"}
            variant="primary"
          >
            {busy ? "Inviting..." : "Invite Participants"}
          </Button>

          <Button
            onClick={() => {
              if (disabled) return;
              listParticipants();
              setTask("list_participants");
            }}
            disabled={disabled}
            title={reasonEval || "View participants"}
            variant="soft"
          >
            View Participants
          </Button>

          {reasonEval ? <Badge tone="amber">{reasonEval}</Badge> : null}
        </div>

        {renderNextActionBar({
          onRefresh: () => {
            if (disabled) return;
            listParticipants();
            setTask("list_participants");
          },
          backTo: "list_evaluations",
        })}
      </div>

      {/* ✅ Invite Results Panel */}
      {inviteResult ? (
        <div style={{ marginTop: 16, border: "1px solid #E5E7EB", borderRadius: 16, padding: 14, background: "#FFFFFF" }}>
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
            <Badge tone="gray">Created: {inviteResult.created ?? 0}</Badge>
            <Badge tone="gray">Existing: {inviteResult.skipped_existing ?? 0}</Badge>
            <Badge tone="green">Email sent: {emailOkCount}</Badge>
            <Badge tone={emailFailCount ? "red" : "gray"}>Email failed: {emailFailCount}</Badge>
          </div>

          <div style={{ marginTop: 12, overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
              <thead style={{ background: "#F8FAFC" }}>
                <tr>
                  {["Email", "Name", "Role", "Portal Link", "Email Status"].map((h) => (
                    <th
                      key={h}
                      style={{
                        textAlign: "left",
                        padding: "10px 12px",
                        borderBottom: "1px solid #E5E7EB",
                        color: "#0F172A",
                        fontWeight: 800,
                        whiteSpace: "nowrap",
                      }}
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>

              <tbody>
                {inviteItems.map((p) => {
                  const ok = p.email_sent === true;
                  const fail = p.email_sent === false;

                  return (
                    <tr key={p.participant_id || p.email} style={{ borderBottom: "1px solid #F1F5F9" }}>
                      <td style={{ padding: "10px 12px", fontWeight: 800 }}>{p.email}</td>
                      <td style={{ padding: "10px 12px" }}>{p.full_name || "—"}</td>
                      <td style={{ padding: "10px 12px" }}>{p.role || "—"}</td>

                      <td style={{ padding: "10px 12px" }}>
                        <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
                          <a
                            href={p.portal_url}
                            target="_blank"
                            rel="noreferrer"
                            style={{ fontWeight: 800, color: "#0F172A" }}
                          >
                            Open →
                          </a>

                          <Button
                            variant="soft"
                            disabled={!p.portal_url}
                            onClick={() => copyToClipboard(p.portal_url)}
                            title="Copy portal link"
                          >
                            Copy
                          </Button>

                          <Badge tone="gray">{p._kind}</Badge>
                        </div>
                      </td>

                      <td style={{ padding: "10px 12px" }}>
                        {ok ? (
                          <Badge tone="green">Sent</Badge>
                        ) : fail ? (
                          <div style={{ display: "grid", gap: 6 }}>
                            <Badge tone="red">Failed</Badge>
                            {p.email_error ? (
                              <div style={{ color: "#991B1B", fontFamily: "monospace", fontSize: 12 }}>
                                {String(p.email_error).slice(0, 180)}
                              </div>
                            ) : null}
                          </div>
                        ) : (
                          <Badge tone="gray">Not attempted</Badge>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}
    </Card>
  );
}
