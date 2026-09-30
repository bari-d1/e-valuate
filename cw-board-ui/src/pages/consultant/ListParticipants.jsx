import React, { useEffect, useMemo } from "react";

/**
 * List Participants page (router-based)
 */
export default function ListParticipantsPage({
  ui,
  busy,
  focus,
  result,

  lockReason,
  listParticipants,
  notifyParticipantLinks,

  go,

  renderFlowBar,

  tableWrapStyle,
  tdStyle,

  wfTracksMetrics,
  wfQuestionsCount,
  questionsCount = 0,
}) {
  const { Card, Badge, Button } = ui || {};

  const missing = [];
  if (!ui?.Card) missing.push("ui.Card");
  if (!ui?.Badge) missing.push("ui.Badge");
  if (!ui?.Button) missing.push("ui.Button");
  if (typeof renderFlowBar !== "function") missing.push("renderFlowBar (function)");
  if (typeof tableWrapStyle !== "function") missing.push("tableWrapStyle (function)");
  if (typeof tdStyle !== "function") missing.push("tdStyle (function)");
  if (typeof lockReason !== "function") missing.push("lockReason (function)");
  if (typeof listParticipants !== "function") missing.push("listParticipants (function)");
  if (typeof notifyParticipantLinks !== "function") missing.push("notifyParticipantLinks (function)");
  if (typeof go !== "function") missing.push("go (function)");

  if (missing.length) {
    return (
      <div style={{ padding: 16, border: "1px solid #FECACA", background: "#FEF2F2", borderRadius: 12 }}>
        <div style={{ fontWeight: 900, color: "#991B1B" }}>ListParticipantsPage: Missing props</div>
        <div style={{ marginTop: 8, color: "#991B1B", fontFamily: "monospace", fontSize: 12 }}>
          {missing.join(", ")}
        </div>
      </div>
    );
  }

  const isList = result?.action === "list_participants";
  const items = isList ? result?.data?.items || [] : [];
  const total = isList ? (result?.data?.count ?? items.length ?? 0) : 0;

  const respondedCount = useMemo(() => {
    if (!isList) return 0;
    return items.filter((x) => String(x.status || "").toLowerCase() === "responded").length;
  }, [isList, items]);

  const invitedCount = useMemo(() => {
    if (!isList) return 0;
    return items.filter((x) => String(x.status || "").toLowerCase() === "invited").length;
  }, [isList, items]);

  const pendingAssignmentsCount = useMemo(() => {
    if (!isList) return 0;
    return items.filter((x) => String(x.portal_status || "") === "pending_assignments").length;
  }, [isList, items]);

  const notifyResult = result?.action === "notify_participant_links" ? result?.data : null;

  const assignmentsCount =
    typeof wfTracksMetrics?.assignmentsCount === "number" ? wfTracksMetrics.assignmentsCount : 0;
  const qCount = Math.max(
    typeof wfQuestionsCount === "number" ? wfQuestionsCount : 0,
    typeof questionsCount === "number" ? questionsCount : 0
  );
  const hasQuestions = qCount > 0;
  const hasAssignments = assignmentsCount > 0;

  const reasonParticipants = lockReason("participants");
  const reasonListQuestions = lockReason("list_questions");
  const reasonTracks = lockReason("tracks");

  const ROUTES = {
    tracks: "/consultant/tracks",
    questions: "/consultant/questions",
    genAI: "/consultant/questions/generate",
    seedQuestions: "/consultant/questions/seed",
    evaluations: "/consultant/evaluations",
    invite: "/consultant/participants/invite",
  };

  const someParticipantsNeedTasks = pendingAssignmentsCount > 0;

  const workflowStep = useMemo(() => {
    if (!hasQuestions) return "questions";
    if (!hasAssignments || someParticipantsNeedTasks) return "tracks";
    return "monitor";
  }, [hasQuestions, hasAssignments, someParticipantsNeedTasks]);

  const notifyLabel = hasAssignments ? "Resend links (hub + tasks)" : "Send hub links by email";
  const notifyTitle = hasAssignments
    ? "Email each person their hub link and all questionnaire task links"
    : "Email hub links only — generate tracks & assignments first for task links";

  const primaryNext = useMemo(() => {
    if (!hasQuestions) {
      return {
        key: "questions",
        label: "Next: Add questions →",
        route: ROUTES.questions,
        disabled: !!reasonListQuestions,
        title: reasonListQuestions || "Seed or add questions for this questionnaire",
        variant: "primary",
      };
    }
    if (!hasAssignments || someParticipantsNeedTasks) {
      return {
        key: "tracks",
        label: someParticipantsNeedTasks
          ? "Generate tasks for new participants →"
          : "Next: Tracks & assignments →",
        route: ROUTES.tracks,
        disabled: !!reasonTracks,
        title:
          reasonTracks ||
          (someParticipantsNeedTasks
            ? "Re-run Generate assignments — creates tasks only for people who do not have them yet"
            : "Enable tracks and generate assignment tasks"),
        variant: "primary",
      };
    }
    return {
      key: "tracks",
      label: "Manage tracks & assignments →",
      route: ROUTES.tracks,
      disabled: !!reasonTracks,
      title: "View assignments and portal links",
      variant: "primary",
    };
  }, [hasQuestions, hasAssignments, someParticipantsNeedTasks, reasonListQuestions, reasonTracks]);

  useEffect(() => {
    if (!reasonParticipants) {
      listParticipants({ silent: true }).catch(() => {});
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <Card
      title="Participants"
      subtitle="Roster for this evaluation — confirm who is registered, then continue setup below."
    >
      {focus}

      {isList && total > 0 ? (
        <div
          style={{
            marginTop: 12,
            padding: 14,
            borderRadius: 12,
            border: workflowStep === "tracks" ? "1px solid #86EFAC" : "1px solid #BFDBFE",
            background: workflowStep === "tracks" ? "#F0FDF4" : "#EFF6FF",
            color: workflowStep === "tracks" ? "#14532D" : "#1E3A8A",
            fontSize: 13,
            lineHeight: 1.5,
          }}
        >
          {!hasQuestions ? (
            <>
              <b>Roster saved ({total} participant{total === 1 ? "" : "s"}).</b> Add or seed questions for your
              questionnaire before generating assessment tasks.
            </>
          ) : !hasAssignments ? (
            <>
              <b>Roster ready ({total} participant{total === 1 ? "" : "s"}).</b> Hub links in the table below work now.
              <span> Open <b>Tracks &amp; assignments</b> and run <b>Generate assignments</b> to create questionnaire tasks.</span>
            </>
          ) : someParticipantsNeedTasks ? (
            <>
              <b>New participants need tasks.</b> {pendingAssignmentsCount} of {total} on the roster have{" "}
              <b>Tasks not generated</b> (no questionnaire links yet). Earlier participants may already have tasks (
              {assignmentsCount} assignment row{assignmentsCount === 1 ? "" : "s"} in total). Go to{" "}
              <b>Tracks &amp; assignments</b> and click <b>Generate assignments</b> again — it only adds missing tasks,
              it does not duplicate existing ones.
            </>
          ) : (
            <>
              <b>Setup complete for distribution.</b> {assignmentsCount} assignment task
              {assignmentsCount === 1 ? "" : "s"} for {total} participant{total === 1 ? "" : "s"}. Use{" "}
              <b>Resend links</b> to email hub + task URLs, or open Tracks to manage links.
            </>
          )}
          <div style={{ marginTop: 12, display: "flex", gap: 10, flexWrap: "wrap" }}>
            <Button
              variant={primaryNext.variant}
              disabled={busy || primaryNext.disabled}
              title={primaryNext.title}
              onClick={() => go(primaryNext.route)}
            >
              {primaryNext.label}
            </Button>
            {!hasQuestions ? (
              <Button variant="soft" disabled={busy} onClick={() => go(ROUTES.seedQuestions)}>
                Seed default questions
              </Button>
            ) : null}
            <Button variant="soft" disabled={busy} onClick={() => go(ROUTES.invite)}>
              Invite more participants
            </Button>
          </div>
        </div>
      ) : null}

      {notifyResult ? (
        <div
          style={{
            marginTop: 12,
            padding: 12,
            borderRadius: 12,
            border: "1px solid #A7F3D0",
            background: "#ECFDF5",
            fontSize: 13,
            color: "#065F46",
          }}
        >
          <b>Emails sent:</b> {notifyResult.email_sent ?? 0} participant(s).
          {(notifyResult.email_failed || []).length > 0 ? (
            <span style={{ marginLeft: 8, color: "#991B1B" }}>
              Failed: {(notifyResult.email_failed || []).length}
            </span>
          ) : null}
        </div>
      ) : null}

      {renderFlowBar({
        left: [
          {
            key: "refresh",
            label: busy ? "Loading..." : "Refresh List",
            onClick: listParticipants,
            disabled: busy || !!reasonParticipants,
            title: reasonParticipants || "Load latest participants",
            variant: "soft",
          },
          {
            key: "notify",
            label: busy ? "Sending…" : notifyLabel,
            onClick: () => notifyParticipantLinks({ onlyPending: false }),
            disabled: busy || !!reasonParticipants || !isList || items.length === 0,
            title: notifyTitle,
            variant: "soft",
          },
        ],
        meta: isList ? (
          <>
            <Badge tone="gray">Total: {total}</Badge>
            <Badge tone="green">Responded: {respondedCount}</Badge>
            <Badge tone="amber">Invited: {invitedCount}</Badge>
            {hasAssignments ? (
              <Badge tone="green">Assignment rows: {assignmentsCount}</Badge>
            ) : (
              <Badge tone="amber">No assignments yet</Badge>
            )}
            {someParticipantsNeedTasks ? (
              <Badge tone="amber">Need generate: {pendingAssignmentsCount}</Badge>
            ) : null}
          </>
        ) : (
          <Badge tone="gray">
            {reasonParticipants ? reasonParticipants : "Click Refresh List to load participants"}
          </Badge>
        ),
      })}

      {isList ? (
        <div style={{ marginTop: 14 }}>
          <div style={tableWrapStyle()}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
              <thead style={{ background: "#F8FAFC" }}>
                <tr>
                  {["Name", "Email", "Role", "Status", "Task hub", "Invited At", "Responded At"].map((h) => (
                    <th
                      key={h}
                      style={{
                        textAlign: "left",
                        padding: "10px 12px",
                        borderBottom: "1px solid #E5E7EB",
                        color: "#0F172A",
                        fontWeight: 800,
                      }}
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {items.map((p) => (
                  <tr key={p.participant_id} style={{ borderBottom: "1px solid #F1F5F9" }}>
                    <td style={tdStyle()}>{p.full_name || "—"}</td>
                    <td style={tdStyle()}>{p.email}</td>
                    <td style={tdStyle()}>{p.role || "—"}</td>
                    <td style={tdStyle()}>
                      <span
                        style={{
                          padding: "3px 8px",
                          borderRadius: 999,
                          fontWeight: 800,
                          fontSize: 12,
                          border: "1px solid #E5E7EB",
                          background:
                            String(p.status).toLowerCase() === "responded" ? "#E8FFF3" : "#FFF7ED",
                          color:
                            String(p.status).toLowerCase() === "responded" ? "#065F46" : "#92400E",
                        }}
                      >
                        {p.status}
                      </span>
                      {String(p.portal_status || "") === "pending_assignments" ? (
                        <span
                          style={{
                            display: "block",
                            marginTop: 4,
                            fontSize: 11,
                            color: "#64748B",
                            fontWeight: 600,
                          }}
                        >
                          Tasks not generated
                        </span>
                      ) : null}
                    </td>
                    <td style={tdStyle()}>
                      {p.hub_url ? (
                        <a href={p.hub_url} target="_blank" rel="noreferrer" style={{ fontWeight: 800 }}>
                          Open hub
                        </a>
                      ) : (
                        "—"
                      )}
                    </td>
                    <td style={tdStyle()}>{p.invited_at || "—"}</td>
                    <td style={tdStyle()}>{p.responded_at || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : (
        <div style={{ marginTop: 12, color: "#64748B", fontSize: 13 }}>
          {reasonParticipants ? (
            <>
              <b>Locked:</b> {reasonParticipants}
            </>
          ) : (
            <>
              Click <b>Refresh List</b> to load participants, or <a href={ROUTES.invite}>invite participants</a> first.
            </>
          )}
        </div>
      )}
    </Card>
  );
}
