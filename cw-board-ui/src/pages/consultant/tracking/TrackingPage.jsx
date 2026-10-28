import React, { useCallback, useEffect, useMemo, useState } from "react";
import { trackingApi } from "../../../api/trackingApi.js";
import { color, font, radius, space } from "../../../theme.js";
import { inputCss, useAsync } from "../companies/helpers.js";
import { Notice, Panel } from "../companies/shared.jsx";
import useWideScreen from "../../form/useWideScreen.js";
import ParticipantList from "./ParticipantList.jsx";
import { ClosePanel, DeadlinePanel, ReminderSettings, TimelineDrawer } from "./TrackingPanels.jsx";
import { OUTSTANDING, STATUS_ORDER, STATUS_TONES, daysLeftText, shortDate } from "./trackingHelpers.js";

/**
 * Responses: who has their link, who has opened it, who's in progress and who has submitted,
 * and chasing the rest. For evaluations that use assembled question sets. Progress only:
 * nobody's answers are shown here.
 */

const SORTS = {
  status: (a, b) => STATUS_ORDER.indexOf(a.status) - STATUS_ORDER.indexOf(b.status) || a.name.localeCompare(b.name),
  progress: (a, b) => share(a) - share(b) || a.name.localeCompare(b.name),
  activity: (a, b) => (a.last_activity_at || "").localeCompare(b.last_activity_at || "") || a.name.localeCompare(b.name),
  name: (a, b) => a.name.localeCompare(b.name),
};
const share = (r) => (r.progress.required ? r.progress.answered / r.progress.required : 0);

function SummaryStrip({ ui, data }) {
  const { Badge } = ui;
  const ev = data.evaluation;
  const order = ["submitted", "in_progress", "opened", "sent", "email_failed", "ready", "not_ready"];
  return (
    <Panel>
      <div style={{ display: "flex", flexWrap: "wrap", gap: space.lg, alignItems: "center", justifyContent: "space-between" }}>
        <div style={{ display: "grid", gap: 6, flex: "1 1 260px", minWidth: 0 }}>
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13 }}>
            <strong>
              {data.submitted} of {data.participants_total} submitted
            </strong>
            <span style={{ color: color.textMuted }}>{data.completion_percent}% of questions answered</span>
          </div>
          <div
            role="progressbar"
            aria-label="Overall completion"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={data.completion_percent}
            style={{ height: 10, borderRadius: radius.pill, background: color.border, overflow: "hidden" }}
          >
            <div style={{ width: `${data.completion_percent}%`, height: "100%", background: color.primary }} />
          </div>
        </div>
        <div style={{ display: "grid", gap: 2, fontSize: 13 }}>
          <span>
            <Badge tone={ev.open ? "green" : "gray"}>{ev.open ? "Open" : "Closed"}</Badge>{" "}
            <span style={{ fontWeight: font.weight.bold }}>{daysLeftText(ev.days_left)}</span>
          </span>
          <span style={{ color: color.textMuted }}>
            Automatic reminders {data.reminders.enabled ? "on" : "off"}
            {data.reminders.enabled && data.reminders.next_batch_on ? ` · next ${shortDate(data.reminders.next_batch_on)}` : ""}
          </span>
        </div>
      </div>
      <ul aria-label="Participants by status" style={{ listStyle: "none", margin: `${space.md}px 0 0`, padding: 0, display: "flex", flexWrap: "wrap", gap: space.sm }}>
        {order
          .filter((k) => data.counts[k] || ["submitted", "in_progress", "sent"].includes(k))
          .map((k) => (
            <li key={k}>
              <Badge tone={STATUS_TONES[k]}>
                {data.status_labels[k]}: {data.counts[k]}
              </Badge>
            </li>
          ))}
      </ul>
    </Panel>
  );
}

/** The in-page confirmation for reminders: who will be emailed and who is skipped, and why. */
function RemindConfirm({ ui, preview, override, setOverride, onSend, onCancel, busy }) {
  const { Button } = ui;
  const will = preview.filter((x) => x.outcome === "would_send");
  const skipped = preview.filter((x) => x.outcome === "skipped");
  const recent = skipped.filter((x) => x.reason === "Reminded less than 24 hours ago.");
  return (
    <Panel highlight style={{ display: "grid", gap: space.sm }}>
      <strong>
        {will.length
          ? `Send a reminder to ${will.length} participant${will.length === 1 ? "" : "s"}?`
          : "Nobody can be reminded right now."}
      </strong>
      {will.length ? (
        <div style={{ fontSize: 13 }}>
          Emailed: {will.map((x) => x.name).join(", ")}. Each gets their own link and their own progress, nothing about anyone else.
        </div>
      ) : null}
      {skipped.length ? (
        <div style={{ fontSize: 13 }}>
          Skipped:
          <ul style={{ margin: "2px 0 0", paddingLeft: 18, color: color.textMuted }}>
            {skipped.map((x) => (
              <li key={x.participant_id}>
                <span style={{ color: color.text }}>{x.name}</span>: {x.reason}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      {recent.length ? (
        <label style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 13 }}>
          <input type="checkbox" checked={override} onChange={(e) => setOverride(e.target.checked)} />
          Remind the {recent.length} reminded in the last 24 hours as well
        </label>
      ) : null}
      <div style={{ display: "flex", gap: space.sm, flexWrap: "wrap" }}>
        <Button disabled={busy || !will.length} onClick={onSend}>
          {busy ? "Sending…" : `Send ${will.length} reminder${will.length === 1 ? "" : "s"}`}
        </Button>
        <Button variant="secondary" disabled={busy} onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </Panel>
  );
}

/** Confirm a regenerate, or take the reason for reopening a form. */
function ActionPanel({ ui, action, onDone, onCancel, evalId }) {
  const { Button } = ui;
  const [reason, setReason] = useState("");
  const { busy, error, run } = useAsync();
  const { type, row } = action;
  const go = () =>
    run(async () => {
      if (type === "regenerate") {
        const r = await trackingApi.regenerateLink(evalId, row.participant_id);
        onDone(row, r.sent ? "New link created and sent. The old link no longer works." : r.error
          ? `New link created, but the email failed: ${r.error}` : "New link created. The old link no longer works.", r.error ? "error" : "ok");
      } else {
        await trackingApi.reopenForm(evalId, row.participant_id, reason.trim());
        onDone(row, "Form reopened. They can change their answers and submit again.", "ok");
      }
    });
  return (
    <Panel highlight style={{ display: "grid", gap: space.sm }}>
      {type === "regenerate" ? (
        <span>
          Create a new link for <strong>{row.name}</strong>? Their current link stops working straight away (use this if it was
          forwarded or leaked). Their saved answers stay, and the new link is emailed to them.
        </span>
      ) : (
        <label style={{ display: "grid", gap: 4 }}>
          <span>
            Reopen <strong>{row.name}</strong>'s submitted form so they can change their answers? Their questions don't change.
          </span>
          <span style={{ fontSize: 13 }}>Reason (kept in the timeline)</span>
          <input value={reason} onChange={(e) => setReason(e.target.value)} maxLength={1000} style={inputCss()} placeholder="e.g. Asked to correct a committee answer" />
        </label>
      )}
      <div style={{ display: "flex", gap: space.sm }}>
        <Button disabled={busy || (type === "reopen" && !reason.trim())} onClick={go}>
          {type === "regenerate" ? "Create and send new link" : "Reopen form"}
        </Button>
        <Button variant="secondary" disabled={busy} onClick={onCancel}>
          Cancel
        </Button>
      </div>
      {error ? <Notice tone="error">{error}</Notice> : null}
    </Panel>
  );
}

export default function TrackingPage({ ui, evalId }) {
  const { Card, Button } = ui;
  const wide = useWideScreen(860);
  const [data, setData] = useState(null);
  const [legacy, setLegacy] = useState("");
  const [sort, setSort] = useState("status");
  const [outstandingOnly, setOutstandingOnly] = useState(false);
  const [selected, setSelected] = useState([]);
  const [preview, setPreview] = useState(null); // {ids, results}
  const [override, setOverride] = useState(false);
  const [action, setAction] = useState(null); // {type: "regenerate" | "reopen", row}
  const [timelineFor, setTimelineFor] = useState(null);
  const [notes, setNotes] = useState({}); // participant id -> {text, tone}
  const [busyId, setBusyId] = useState(null);
  const { busy, error, setError, run } = useAsync();

  const load = useCallback(
    () =>
      run(async () => {
        try {
          setData(await trackingApi.summary(evalId));
          setLegacy("");
        } catch (e) {
          if (e.status === 409) setLegacy(e.message);
          else throw e;
        }
      }),
    [evalId, run]
  );
  useEffect(() => {
    if (evalId) load();
  }, [evalId, load]);

  const rows = useMemo(() => {
    const list = (data?.participants || []).filter((r) => !outstandingOnly || OUTSTANDING.has(r.status));
    return [...list].sort(SORTS[sort]);
  }, [data, sort, outstandingOnly]);
  const outstanding = (data?.participants || []).filter((r) => OUTSTANDING.has(r.status));

  const note = (row, text, tone = "ok") => setNotes((n) => ({ ...n, [row.participant_id]: { text, tone } }));

  const askReminders = (ids) =>
    run(async () => {
      setOverride(false);
      const r = await trackingApi.remind(evalId, ids, { dryRun: true, override: true });
      // Ask again without the override so the 24-hour rule shows as a skip reason the consultant can lift
      const strict = await trackingApi.remind(evalId, ids, { dryRun: true });
      setPreview({ ids, results: strict.results, withOverride: r.results });
    });

  const sendReminders = () =>
    run(async () => {
      const r = await trackingApi.remind(evalId, preview.ids, { override });
      r.results.forEach((x) => {
        const row = { participant_id: x.participant_id };
        if (x.outcome === "sent") note(row, "Reminder sent.");
        else if (x.outcome === "failed") note(row, `Reminder failed: ${x.reason}`, "error");
      });
      setPreview(null);
      setSelected([]);
      await load();
    });

  const onAction = async (type, row) => {
    setError("");
    if (type === "timeline") return setTimelineFor(row);
    if (type === "regenerate" || type === "reopen") return setAction({ type, row });
    if (type === "remind") return askReminders([row.participant_id]);
    if (type === "resend") {
      setBusyId(row.participant_id);
      await run(async () => {
        const r = await trackingApi.resendLink(evalId, row.participant_id);
        note(row, r.sent ? "Link sent." : `The email failed: ${r.error}`, r.sent ? "ok" : "error");
        await load();
      });
      setBusyId(null);
    }
    return undefined;
  };

  const shownPreview = preview
    ? override
      ? preview.withOverride
      : preview.results
    : null;

  return (
    <Card title="Responses" subtitle="Who has their link, who has opened it, who's in progress and who has submitted. Progress only: answers aren't shown here.">
      {!evalId ? <Notice>Choose an evaluation first.</Notice> : null}
      {legacy ? <Notice>{legacy}</Notice> : null}
      {error ? (
        <div style={{ marginBottom: space.md }}>
          <Notice tone="error">{error}</Notice>
        </div>
      ) : null}
      {data ? (
        <div style={{ display: "grid", gap: space.lg, gridTemplateColumns: "minmax(0, 1fr)" }}>
          <SummaryStrip ui={ui} data={data} />

          <section aria-label="Participants" style={{ display: "grid", gap: space.md }}>
            <div style={{ display: "flex", gap: space.md, flexWrap: "wrap", alignItems: "center", justifyContent: "space-between" }}>
              <div style={{ display: "flex", gap: space.md, flexWrap: "wrap", alignItems: "center", fontSize: 13 }}>
                <label style={{ display: "flex", gap: 6, alignItems: "center" }}>
                  Sort by
                  <select value={sort} onChange={(e) => setSort(e.target.value)} style={inputCss({ width: "auto" })}>
                    <option value="status">Status</option>
                    <option value="progress">Progress</option>
                    <option value="activity">Last activity</option>
                    <option value="name">Name</option>
                  </select>
                </label>
                <label style={{ display: "flex", gap: 6, alignItems: "center" }}>
                  <input type="checkbox" checked={outstandingOnly} onChange={(e) => setOutstandingOnly(e.target.checked)} />
                  Outstanding only
                </label>
              </div>
              <div style={{ display: "flex", gap: space.sm, flexWrap: "wrap" }}>
                <Button
                  variant="secondary"
                  disabled={busy || !outstanding.length || !data.evaluation.open}
                  onClick={() => setSelected(selected.length === outstanding.length ? [] : outstanding.map((r) => r.participant_id))}
                >
                  {selected.length === outstanding.length && outstanding.length ? "Clear selection" : `Select all outstanding (${outstanding.length})`}
                </Button>
                <Button disabled={busy || !selected.length || !data.evaluation.open} onClick={() => askReminders(selected)}>
                  Remind selected ({selected.length})
                </Button>
              </div>
            </div>

            {shownPreview ? (
              <RemindConfirm
                ui={ui}
                preview={shownPreview}
                override={override}
                setOverride={setOverride}
                busy={busy}
                onSend={sendReminders}
                onCancel={() => setPreview(null)}
              />
            ) : null}
            {action ? (
              <ActionPanel
                ui={ui}
                evalId={evalId}
                action={action}
                onCancel={() => setAction(null)}
                onDone={async (row, text, tone) => {
                  note(row, text, tone);
                  setAction(null);
                  await load();
                }}
              />
            ) : null}

            <ParticipantList
              ui={ui}
              rows={rows}
              selected={selected}
              onToggle={(id) => setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]))}
              onAction={onAction}
              busyId={busyId}
              wide={wide}
              open={data.evaluation.open}
              notes={notes}
            />
          </section>

          <div style={{ display: "grid", gap: space.md, gridTemplateColumns: wide ? "minmax(0, 3fr) minmax(0, 2fr)" : "minmax(0, 1fr)", alignItems: "start" }}>
            <ReminderSettings ui={ui} evalId={evalId} onChanged={load} refreshKey={data} />
            <div style={{ display: "grid", gap: space.md }}>
              <DeadlinePanel ui={ui} evalId={evalId} deadline={data.evaluation.deadline} outstanding={outstanding.length} onChanged={load} />
              <ClosePanel ui={ui} evalId={evalId} open={data.evaluation.open} onChanged={load} />
            </div>
          </div>
        </div>
      ) : !legacy && evalId ? (
        <p style={{ color: color.textMuted }}>Loading…</p>
      ) : null}
      {timelineFor ? <TimelineDrawer evalId={evalId} participant={timelineFor} onClose={() => setTimelineFor(null)} /> : null}
    </Card>
  );
}
