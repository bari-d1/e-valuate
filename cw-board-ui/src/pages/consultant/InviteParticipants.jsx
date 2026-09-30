import React, { useEffect, useMemo, useState } from "react";

/**
 * src/pages/consultant/InviteParticipants.jsx
 * -------------------------------------------
 * Invite Participants page.
 *
 * Works with Router-based AppLegacy:
 * - Uses go("/consultant/participants") instead of setTask
 * - Persists last invite result locally so it doesn't disappear after list refresh
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
  go,
  renderNextActionBar,
  textareaStyle,

  // shared result state from AppLegacy
  result,

  wfTracksMetrics,
  wfQuestionsCount,
}) {
  const { Card, Badge, Field, Button } = ui;

  const reasonEval = lockReason("evaluation");
  const disabled = busy || !!reasonEval;

  // ✅ Keep the last invite result even if AppLegacy overwrites result with list_participants
  const [lastInviteResult, setLastInviteResult] = useState(null);
  const [sendEmailOnInvite, setSendEmailOnInvite] = useState(false);

  useEffect(() => {
    if (result?.action === "invite_participants" && result?.data) {
      setLastInviteResult(result.data);
    }
  }, [result]);

  // Prefer the most recent invite response we saw
  const inviteResult = lastInviteResult;

  const inviteItems = useMemo(() => {
    if (!inviteResult) return [];
    const created = inviteResult.created_items || [];
    const existing = inviteResult.existing_items || [];
    return [
      ...created.map((x) => ({ ...x, _kind: "created" })),
      ...existing.map((x) => ({ ...x, _kind: "existing" })),
    ];
  }, [inviteResult]);

  const emailOkCount = useMemo(
    () => inviteItems.filter((x) => x.email_sent === true).length,
    [inviteItems]
  );
  const emailFailCount = useMemo(
    () => inviteItems.filter((x) => x.email_sent === false && !x.email_skipped).length,
    [inviteItems]
  );

  const assignmentsCount =
    typeof wfTracksMetrics?.assignmentsCount === "number" ? wfTracksMetrics.assignmentsCount : 0;
  const qCount = typeof wfQuestionsCount === "number" ? wfQuestionsCount : 0;
  const hasQuestions = qCount > 0;
  const hasAssignments = assignmentsCount > 0;

  const postInviteNext = useMemo(() => {
    if (!hasQuestions) {
      return {
        message: "Roster saved. Add or seed questions next, then open Tracks & assignments.",
        primaryLabel: "Next: Add questions →",
        primaryRoute: "/consultant/questions",
        secondaryLabel: "View participant roster →",
        secondaryRoute: "/consultant/participants",
      };
    }
    if (!hasAssignments) {
      return {
        message:
          "Roster saved. Hub links are ready. Open Tracks & assignments to create questionnaire tasks for each person.",
        primaryLabel: "Next: Tracks & assignments →",
        primaryRoute: "/consultant/tracks",
        secondaryLabel: "View participant roster →",
        secondaryRoute: "/consultant/participants",
      };
    }
    return {
      message: "Roster saved and assignments exist. Review links on the roster or manage tracks.",
      primaryLabel: "View participant roster →",
      primaryRoute: "/consultant/participants",
      secondaryLabel: "Tracks & assignments →",
      secondaryRoute: "/consultant/tracks",
    };
  }, [hasQuestions, hasAssignments]);

  const copyToClipboard = async (text) => {
    try {
      await navigator.clipboard.writeText(text);
    } catch {
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
      subtitle="Add board members to this evaluation. They get their questionnaire links once you generate tasks on the Tracks page."
    >
      <div style={{ marginTop: 6 }}>{focus}</div>

      <div style={{ marginTop: 14 }}>
        <Field
          label="Participants (one per line)"
          hint="Email, then optionally full name and role, separated by commas."
        >
          <textarea
            value={inviteText}
            onChange={(e) => setInviteText(e.target.value)}
            placeholder={"jane.doe@example.com,Jane Doe,INED\njohn.smith@example.com,John Smith,ED"}
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
        <label
          style={{
            display: "flex",
            gap: 8,
            alignItems: "center",
            marginBottom: 10,
            fontSize: 13,
            cursor: disabled ? "default" : "pointer",
          }}
        >
          <input
            type="checkbox"
            checked={sendEmailOnInvite}
            onChange={(e) => setSendEmailOnInvite(e.target.checked)}
            disabled={disabled}
          />
          <span>
            Also email each person a welcome message with their link
          </span>
        </label>

        <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
          <Button
            onClick={() => inviteParticipants({ sendEmail: sendEmailOnInvite })}
            disabled={disabled}
            title={reasonEval || "Register participants on this evaluation"}
            variant="primary"
          >
            {busy ? "Saving…" : sendEmailOnInvite ? "Register and send email" : "Register participants"}
          </Button>

          {reasonEval ? <Badge tone="amber">{reasonEval}</Badge> : null}
        </div>

        {renderNextActionBar({
          onRefresh: () => {
            if (disabled) return;
            listParticipants({ silent: true });
          },
          backTo: "list_evaluations",
        })}
      </div>

      {/* ✅ Invite Results Panel (sticky) */}
      {inviteResult ? (
        <div
          style={{
            marginTop: 16,
            border: "1px solid #E5E7EB",
            borderRadius: 16,
            padding: 14,
            background: "#FFFFFF",
          }}
        >
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
            <Badge tone="gray">Created: {inviteResult.created ?? 0}</Badge>
            <Badge tone="gray">Existing: {inviteResult.skipped_existing ?? 0}</Badge>
            <Badge tone="green">Email sent: {emailOkCount}</Badge>
            <Badge tone={emailFailCount ? "red" : "gray"}>Email failed: {emailFailCount}</Badge>
          </div>

          <div
            style={{
              marginTop: 12,
              padding: 12,
              borderRadius: 12,
              border: "1px solid #A7F3D0",
              background: "#ECFDF5",
              color: "#14532D",
              fontSize: 13,
              lineHeight: 1.45,
            }}
          >
            <b>What&apos;s next?</b>
            <div style={{ marginTop: 6 }}>{postInviteNext.message}</div>
            <div style={{ marginTop: 10, display: "flex", gap: 10, flexWrap: "wrap" }}>
              <Button
                variant="primary"
                disabled={busy}
                onClick={() => go(postInviteNext.primaryRoute)}
              >
                {postInviteNext.primaryLabel}
              </Button>
              <Button
                variant="soft"
                disabled={busy}
                onClick={() => go(postInviteNext.secondaryRoute)}
              >
                {postInviteNext.secondaryLabel}
              </Button>
            </div>
          </div>

          <div style={{ marginTop: 12, overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
              <thead style={{ background: "#F8FAFC" }}>
                <tr>
                  {["Email", "Name", "Role", "Hub link", "First task link", "Email"].map((h) => (
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
                          {p.hub_url ? (
                            <>
                              <a
                                href={p.hub_url}
                                target="_blank"
                                rel="noreferrer"
                                style={{ fontWeight: 800, color: "#0F172A" }}
                              >
                                Hub
                              </a>
                              <Button variant="soft" onClick={() => copyToClipboard(p.hub_url)}>
                                Copy
                              </Button>
                            </>
                          ) : (
                            <span style={{ color: "#64748B", fontSize: 12 }}>—</span>
                          )}
                        </div>
                      </td>

                      <td style={{ padding: "10px 12px" }}>
                        <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
                          {(p.first_assignment_portal_url || p.portal_url) ? (
                            <>
                              <a
                                href={p.first_assignment_portal_url || p.portal_url}
                                target="_blank"
                                rel="noreferrer"
                                style={{ fontWeight: 800, color: "#0F172A" }}
                              >
                                Task
                              </a>
                              <Button
                                variant="soft"
                                onClick={() =>
                                  copyToClipboard(p.first_assignment_portal_url || p.portal_url)
                                }
                              >
                                Copy
                              </Button>
                            </>
                          ) : (
                            <span style={{ color: "#64748B", fontSize: 12 }}>After generate</span>
                          )}
                          <Badge tone="gray">{p._kind}</Badge>
                        </div>
                      </td>

                      <td style={{ padding: "10px 12px" }}>
                        {p.email_skipped ? (
                          <Badge tone="gray">Not sent (register only)</Badge>
                        ) : ok ? (
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

            {/* Optional: clear panel */}
            <div style={{ marginTop: 12, display: "flex", justifyContent: "flex-end" }}>
              <Button variant="soft" onClick={() => setLastInviteResult(null)} title="Hide invite results panel">
                Hide Results
              </Button>
            </div>
          </div>
        </div>
      ) : null}
    </Card>
  );
}
