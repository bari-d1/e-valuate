import React, { useEffect, useState } from "react";
import { trackingApi } from "../../../api/trackingApi.js";
import { color, font, radius, space } from "../../../theme.js";
import { inputCss, useAsync } from "../companies/helpers.js";
import { Notice, Panel } from "../companies/shared.jsx";
import { longDate, scheduleSentence, shortDate } from "./trackingHelpers.js";

/** Reminder settings, the deadline, closing the evaluation, and the participant timeline drawer. */

const NUMBERS = [
  ["first_after_days", "First reminder, days after the invite"],
  ["repeat_every_days", "Then repeat every (days)"],
  ["final_before_deadline_days", "Final reminder, days before the deadline"],
  ["max_reminders", "Most reminders per person"],
];

export function ReminderSettings({ ui, evalId, onChanged, refreshKey }) {
  const { Button, Badge } = ui;
  const [view, setView] = useState(null);
  const [draft, setDraft] = useState(null);
  const { busy, error, run } = useAsync();

  useEffect(() => {
    run(async () => {
      const v = await trackingApi.settings(evalId);
      setView(v);
      setDraft(v.settings);
    });
  }, [evalId, run, refreshKey]); // reload when the page reloads (e.g. a new deadline moves the schedule)

  if (!view || !draft) return null;
  const dirty = JSON.stringify(draft) !== JSON.stringify(view.settings);
  const save = (body) =>
    run(async () => {
      const v = await trackingApi.saveSettings(evalId, body);
      setView(v);
      setDraft(v.settings);
      await onChanged();
    });
  const dry = view.dry_run;

  return (
    <Panel>
      <div style={{ display: "flex", justifyContent: "space-between", gap: space.md, flexWrap: "wrap", alignItems: "center" }}>
        <div>
          <strong style={{ fontSize: font.body }}>Automatic reminders</strong>{" "}
          <Badge tone={view.settings.enabled ? "green" : "gray"}>{view.settings.enabled ? "On" : "Off"}</Badge>
          <div style={{ fontSize: font.small, color: color.textMuted, marginTop: 2 }}>
            Sent on weekday mornings by the reminder job. Never to anyone who has submitted.
          </div>
        </div>
        <Button variant={view.settings.enabled ? "secondary" : undefined} disabled={busy} onClick={() => save({ enabled: !view.settings.enabled })}>
          {view.settings.enabled ? "Turn off" : "Turn on"}
        </Button>
      </div>

      <div style={{ display: "grid", gap: space.sm, gridTemplateColumns: "repeat(auto-fit, minmax(190px, 1fr))", marginTop: space.md }}>
        {NUMBERS.map(([key, label]) => (
          <label key={key} style={{ display: "grid", gap: 4, fontSize: 13 }}>
            {label}
            <input
              type="number"
              min={key === "final_before_deadline_days" ? 0 : key === "max_reminders" ? 0 : 1}
              max={key === "max_reminders" ? 10 : 60}
              value={draft[key]}
              onChange={(e) => setDraft((d) => ({ ...d, [key]: e.target.value === "" ? "" : Number(e.target.value) }))}
              style={inputCss({ width: "100%" })}
            />
          </label>
        ))}
        <label style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 13, alignSelf: "end", minHeight: 38 }}>
          <input type="checkbox" checked={draft.skip_weekends} onChange={(e) => setDraft((d) => ({ ...d, skip_weekends: e.target.checked }))} />
          Skip weekends
        </label>
      </div>
      {dirty ? (
        <div style={{ display: "flex", gap: space.sm, marginTop: space.sm }}>
          <Button disabled={busy} onClick={() => save({ ...draft, enabled: undefined })}>
            Save schedule
          </Button>
          <Button variant="secondary" disabled={busy} onClick={() => setDraft(view.settings)}>
            Cancel
          </Button>
        </div>
      ) : null}

      <div style={{ marginTop: space.md, padding: space.md, borderRadius: radius.md, background: color.surfaceMuted, border: `1px solid ${color.border}` }}>
        <div style={{ fontSize: 13, color: color.textMuted }}>
          {view.schedule.based_on_invites
            ? `For people invited ${shortDate(view.schedule.based_on)}:`
            : "For anyone invited today:"}
        </div>
        <div style={{ fontWeight: font.weight.bold }}>{scheduleSentence(view.schedule.slots)}</div>
      </div>

      <div style={{ marginTop: space.md }}>
        <strong style={{ fontSize: 13 }}>
          {view.settings.enabled ? "Due today" : "Would be reminded today if switched on"} ({dry.would_remind.length})
        </strong>
        {dry.would_remind.length ? (
          <ul style={{ margin: `${space.xs}px 0 0`, paddingLeft: 18, fontSize: 13, display: "grid", gap: 2 }}>
            {dry.would_remind.map((x) => (
              <li key={x.participant_id}>
                {x.name}: {x.reason}
              </li>
            ))}
          </ul>
        ) : (
          <div style={{ fontSize: 13, color: color.textMuted }}>Nobody is due a reminder today.</div>
        )}
        {dry.skipped.length ? (
          <details style={{ marginTop: space.xs, fontSize: 13 }}>
            <summary style={{ cursor: "pointer" }}>{dry.skipped.length} outstanding but not due today</summary>
            <ul style={{ margin: `${space.xs}px 0 0`, paddingLeft: 18, color: color.textMuted, display: "grid", gap: 2 }}>
              {dry.skipped.map((x) => (
                <li key={x.participant_id}>
                  <span style={{ color: color.text }}>{x.name}</span>: {x.reason}
                </li>
              ))}
            </ul>
          </details>
        ) : null}
      </div>
      {error ? (
        <div style={{ marginTop: space.sm }}>
          <Notice tone="error">{error}</Notice>
        </div>
      ) : null}
    </Panel>
  );
}

export function DeadlinePanel({ ui, evalId, deadline, outstanding, onChanged }) {
  const { Button } = ui;
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(deadline || "");
  const [notify, setNotify] = useState(true);
  const [done, setDone] = useState("");
  const { busy, error, run } = useAsync();
  const save = () =>
    run(async () => {
      const r = await trackingApi.setDeadline(evalId, value, notify);
      const sent = r.notified.filter((x) => x.outcome === "sent").length;
      setDone(`Deadline set to ${longDate(r.deadline)}.${notify ? ` ${sent} outstanding participant${sent === 1 ? "" : "s"} told.` : ""}`);
      setEditing(false);
      await onChanged();
    });
  return (
    <Panel>
      <div style={{ display: "flex", justifyContent: "space-between", gap: space.md, flexWrap: "wrap", alignItems: "center" }}>
        <div>
          <strong style={{ fontSize: font.body }}>Deadline</strong>
          <div style={{ fontSize: 13 }}>{deadline ? longDate(deadline) : "Not set"}</div>
        </div>
        {!editing ? (
          <Button variant="secondary" onClick={() => { setValue(deadline || ""); setEditing(true); setDone(""); }}>
            Change deadline
          </Button>
        ) : null}
      </div>
      {editing ? (
        <div style={{ display: "grid", gap: space.sm, marginTop: space.sm }}>
          <label style={{ display: "grid", gap: 4, fontSize: 13, maxWidth: 220 }}>
            New deadline
            <input type="date" value={value} onChange={(e) => setValue(e.target.value)} style={inputCss()} />
          </label>
          <label style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 13 }}>
            <input type="checkbox" checked={notify} onChange={(e) => setNotify(e.target.checked)} />
            Email the {outstanding} participant{outstanding === 1 ? "" : "s"} who haven't submitted about the new date
          </label>
          <div style={{ display: "flex", gap: space.sm }}>
            <Button disabled={busy || !value} onClick={save}>
              Save deadline
            </Button>
            <Button variant="secondary" disabled={busy} onClick={() => setEditing(false)}>
              Cancel
            </Button>
          </div>
        </div>
      ) : null}
      {done ? <div style={{ marginTop: space.sm, fontSize: 13, color: "#065F46" }} role="status">{done}</div> : null}
      {error ? (
        <div style={{ marginTop: space.sm }}>
          <Notice tone="error">{error}</Notice>
        </div>
      ) : null}
    </Panel>
  );
}

export function ClosePanel({ ui, evalId, open, onChanged }) {
  const { Button } = ui;
  const [confirming, setConfirming] = useState(false);
  const { busy, error, run } = useAsync();
  const act = () =>
    run(async () => {
      await (open ? trackingApi.close(evalId) : trackingApi.reopen(evalId));
      setConfirming(false);
      await onChanged();
    });
  return (
    <Panel>
      <div style={{ display: "flex", justifyContent: "space-between", gap: space.md, flexWrap: "wrap", alignItems: "center" }}>
        <div>
          <strong style={{ fontSize: font.body }}>{open ? "Open for answers" : "Closed"}</strong>
          <div style={{ fontSize: 13, color: color.textMuted }}>
            {open
              ? "Close it when you have what you need: nobody can answer or submit after that."
              : "Participants see a polite closed message. Reopen to accept answers again."}
          </div>
        </div>
        {!confirming ? (
          <Button variant={open ? "danger" : undefined} onClick={() => setConfirming(true)}>
            {open ? "Close evaluation" : "Reopen evaluation"}
          </Button>
        ) : null}
      </div>
      {confirming ? (
        <div style={{ display: "grid", gap: space.sm, marginTop: space.sm, padding: space.md, borderRadius: radius.md, background: color.surfaceMuted }}>
          <span style={{ fontSize: 14 }}>
            {open
              ? "Close the evaluation? Anyone who hasn't submitted won't be able to finish, and no reminders will go out."
              : "Reopen the evaluation? Participants can answer and submit again, and reminders resume if they're on."}
          </span>
          <div style={{ display: "flex", gap: space.sm }}>
            <Button variant={open ? "danger" : undefined} disabled={busy} onClick={act}>
              {open ? "Yes, close it" : "Yes, reopen it"}
            </Button>
            <Button variant="secondary" disabled={busy} onClick={() => setConfirming(false)}>
              Cancel
            </Button>
          </div>
        </div>
      ) : null}
      {error ? (
        <div style={{ marginTop: space.sm }}>
          <Notice tone="error">{error}</Notice>
        </div>
      ) : null}
    </Panel>
  );
}

/** Every event for one participant, oldest first, in a panel at the side (full width on a phone). */
export function TimelineDrawer({ evalId, participant, onClose }) {
  const [data, setData] = useState(null);
  const { error, run } = useAsync();
  useEffect(() => {
    run(async () => setData(await trackingApi.timeline(evalId, participant.participant_id)));
  }, [evalId, participant, run]);
  useEffect(() => {
    const onKey = (e) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div
      onMouseDown={(e) => e.target === e.currentTarget && onClose()}
      style={{ position: "fixed", inset: 0, zIndex: 1000, background: "rgba(15, 23, 42, 0.45)", display: "flex", justifyContent: "flex-end" }}
    >
      <aside
        role="dialog"
        aria-modal="true"
        aria-labelledby="timeline-title"
        style={{ width: "min(440px, 100%)", height: "100%", overflowY: "auto", background: color.surface, padding: space.xl, boxShadow: "-12px 0 40px rgba(15,23,42,0.2)" }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: space.md }}>
          <div>
            <h2 id="timeline-title" style={{ margin: 0, fontSize: 18 }}>
              Timeline
            </h2>
            <div style={{ fontSize: 13, color: color.textMuted }}>{participant.name}</div>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close timeline"
            autoFocus
            style={{ width: 40, height: 40, border: 0, borderRadius: radius.pill, background: "transparent", fontSize: 24, cursor: "pointer", color: color.textMuted }}
          >
            ×
          </button>
        </div>
        {error ? <Notice tone="error">{error}</Notice> : null}
        {!data ? (
          <p style={{ color: color.textMuted }}>Loading…</p>
        ) : (
          <ol style={{ listStyle: "none", margin: `${space.lg}px 0 0`, padding: 0, display: "grid", gap: 0 }}>
            {data.events.map((e) => (
              <li key={e.id} style={{ display: "grid", gridTemplateColumns: "14px 1fr", gap: space.sm, paddingBottom: space.md }}>
                <span
                  aria-hidden="true"
                  style={{
                    width: 10,
                    height: 10,
                    marginTop: 6,
                    borderRadius: radius.pill,
                    background: e.type === "email_failed" ? color.danger : e.type === "submitted" ? "#059669" : e.evaluation_wide ? color.borderStrong : color.primary,
                  }}
                />
                <div>
                  <div style={{ fontSize: 14, color: e.type === "email_failed" ? color.danger : color.text, fontWeight: font.weight.medium }}>{e.text}</div>
                  <div style={{ fontSize: font.small, color: color.textMuted }}>
                    {new Date(e.at).toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })} · {e.actor}
                    {e.evaluation_wide ? " · whole evaluation" : ""}
                  </div>
                </div>
              </li>
            ))}
            {!data.events.length ? <li style={{ color: color.textMuted }}>Nothing yet.</li> : null}
          </ol>
        )}
      </aside>
    </div>
  );
}
