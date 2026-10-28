import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { formApi } from "../../api/formApi.js";
import { color, font, radius, space } from "../../theme.js";
import { allQuestions, formatDate, progress, sectionQuestions, visibility } from "./formHelpers.js";
import { NavButton, PeerGrid, Question } from "./FormParts.jsx";
import useAutosave from "./useAutosave.js";
import useWideScreen from "./useWideScreen.js";

/**
 * The participant's one form (evaluations that use assembled question sets): /form/:token.
 *
 * Welcome → one section at a time → review → submit → thank you. Answers save as they go,
 * so the participant can stop and come back to the same link. After submission the link
 * shows a read-only summary. Nothing internal (codes, tags, tokens, AI wording) is shown.
 */

const SR_ONLY = { position: "absolute", width: 1, height: 1, overflow: "hidden", clip: "rect(0 0 0 0)", whiteSpace: "nowrap" };

function Shell({ form, children, status }) {
  return (
    <div style={{ minHeight: "100vh", background: color.page }}>
      <header
        style={{
          position: "sticky",
          top: 0,
          zIndex: 5,
          background: color.surface,
          borderBottom: `1px solid ${color.border}`,
          padding: `10px ${space.lg}px`,
        }}
      >
        <div style={{ maxWidth: 960, margin: "0 auto", display: "flex", justifyContent: "space-between", alignItems: "center", gap: space.md }}>
          <div style={{ minWidth: 0 }}>
            <div style={{ fontWeight: font.weight.heavy, fontSize: 15, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
              {form?.evaluation?.organisation || "Board evaluation"}
            </div>
            {form ? <div style={{ fontSize: 13, color: color.textMuted }}>{form.evaluation.name}</div> : null}
          </div>
          {status}
        </div>
      </header>
      <main style={{ maxWidth: 960, margin: "0 auto", padding: `${space.lg}px ${space.lg}px 96px` }}>{children}</main>
    </div>
  );
}

function Panel({ children, style }) {
  return (
    <section
      style={{
        background: color.surface,
        border: `1px solid ${color.border}`,
        borderRadius: radius.lg,
        padding: space.lg,
        display: "grid",
        gap: space.lg,
        ...style,
      }}
    >
      {children}
    </section>
  );
}

function SaveStatus({ status, savedAt }) {
  const words = {
    pending: "Saving…",
    saving: "Saving…",
    saved: savedAt ? "Saved" : "",
    retrying: "Not saved, retrying",
    stopped: "Not saved",
    idle: "",
  }[status];
  const bad = status === "retrying" || status === "stopped";
  return (
    <div
      role="status"
      aria-live="polite"
      style={{ fontSize: 13, fontWeight: font.weight.bold, color: bad ? color.danger : color.textMuted, whiteSpace: "nowrap" }}
    >
      {words}
    </div>
  );
}

function ProgressBar({ done, total }) {
  const pct = total ? Math.round((done / total) * 100) : 100;
  return (
    <div style={{ display: "grid", gap: 6 }}>
      <div
        role="progressbar"
        aria-label="Questions answered"
        aria-valuemin={0}
        aria-valuemax={total}
        aria-valuenow={done}
        aria-valuetext={`${done} of ${total} questions answered`}
        style={{ height: 8, borderRadius: radius.pill, background: color.border, overflow: "hidden" }}
      >
        <div style={{ width: `${pct}%`, height: "100%", background: color.primary, transition: "width 200ms ease" }} />
      </div>
      <div style={{ fontSize: 13, color: color.textMuted }}>
        {done} of {total} required questions answered
      </div>
    </div>
  );
}

function SectionList({ sections, current, answers, onGo }) {
  return (
    <nav aria-label="Sections">
      <ol style={{ listStyle: "none", margin: 0, padding: 0, display: "flex", flexWrap: "wrap", gap: space.sm }}>
        {sections.map((s, i) => {
          const p = progress(sectionQuestions(s), answers);
          const complete = p.requiredAnswered === p.required;
          const here = i === current;
          return (
            <li key={s.key}>
              <button
                type="button"
                onClick={() => onGo(i)}
                aria-current={here ? "step" : undefined}
                style={{
                  minHeight: 40,
                  padding: "8px 12px",
                  borderRadius: radius.pill,
                  border: `1.5px solid ${here ? color.primary : color.border}`,
                  background: here ? color.primarySoft : color.surface,
                  color: here ? color.primaryText : color.text,
                  fontWeight: font.weight.bold,
                  fontSize: 14,
                  cursor: "pointer",
                }}
              >
                {complete ? <span aria-hidden="true">✓ </span> : null}
                {s.title}
                {complete ? <span style={SR_ONLY}> (complete)</span> : null}
              </button>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}

function SectionView({ section, answers, onAnswer, invalid, wide, readOnly }) {
  const questions = useMemo(() => sectionQuestions(section), [section]);
  const vis = visibility(questions, answers);
  return (
    <div style={{ display: "grid", gap: space.xl }}>
      {section.blocks.map((b) => {
        if (b.kind === "grid") {
          return <PeerGrid key="grid" grid={b} answers={answers} onAnswer={onAnswer} wide={wide} readOnly={readOnly} errors={invalid} />;
        }
        if (!vis.get(b.id)) return null;
        return (
          <Question
            key={b.id}
            q={b}
            value={answers[b.id]}
            onChange={(v) => onAnswer(b.id, v)}
            error={invalid[b.id]}
            readOnly={readOnly}
            followUp={!!b.follows}
          />
        );
      })}
    </div>
  );
}

function Welcome({ form, onStart, done, total }) {
  const ev = form.evaluation;
  const started = form.status === "in_progress" || done > 0;
  return (
    <Panel>
      <div style={{ display: "grid", gap: space.sm }}>
        <div style={{ fontSize: 14, color: color.textMuted, fontWeight: font.weight.bold }}>{ev.organisation}</div>
        <h1 style={{ margin: 0, fontSize: 26, lineHeight: 1.25 }}>{ev.name}</h1>
        {form.participant?.name ? <p style={{ margin: 0, fontSize: 16 }}>Welcome, {form.participant.name}.</p> : null}
      </div>
      <ul style={{ margin: 0, paddingLeft: 20, display: "grid", gap: 6, fontSize: 16 }}>
        {form.estimated_minutes ? <li>It takes about {form.estimated_minutes} minutes.</li> : null}
        {ev.deadline ? <li>Please complete it by {formatDate(ev.deadline)}.</li> : null}
        <li>Your answers save as you go, you can come back to this link any time.</li>
      </ul>
      <p style={{ margin: 0, padding: space.md, borderRadius: radius.md, background: color.surfaceMuted, border: `1px solid ${color.border}`, fontSize: 15 }}>
        {ev.notice}
      </p>
      {started ? <ProgressBar done={done} total={total} /> : null}
      <NavButton primary onClick={onStart} style={{ fontSize: 17 }}>
        {started ? "Continue" : "Start"}
      </NavButton>
    </Panel>
  );
}

function Review({ form, answers, onGo, onSubmit, submitting, submitError, serverMissing }) {
  const [confirming, setConfirming] = useState(false);
  const all = allQuestions(form);
  const p = progress(all, answers);
  const missing = serverMissing?.length ? serverMissing.map((m) => m.question_id) : p.missing.map((q) => q.id);
  const sectionOf = (id) => form.sections.findIndex((s) => sectionQuestions(s).some((q) => q.id === id));
  const missingItems = missing.map((id) => {
    const si = sectionOf(id);
    const s = form.sections[si];
    const block = s?.blocks.find((b) => b.id === id);
    const grid = s?.blocks.find((b) => b.kind === "grid");
    let text = block?.text;
    let about = block?.about;
    if (!block && grid) {
      const st = grid.statements.find((x) => Object.values(x.cells).includes(id));
      const col = st && Object.entries(st.cells).find(([, v]) => v === id)?.[0];
      text = st?.text;
      about = grid.colleagues.find((c) => c.id === col)?.name;
    }
    return { id, si, title: s?.title, text: text || "A question", about };
  });
  return (
    <Panel>
      <h1 style={{ margin: 0, fontSize: 24 }}>Check and submit</h1>
      <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "grid", gap: space.sm }}>
        {form.sections.map((s, i) => {
          const sp = progress(sectionQuestions(s), answers);
          return (
            <li key={s.key} style={{ display: "flex", justifyContent: "space-between", gap: space.md, padding: "10px 0", borderBottom: `1px solid ${color.border}`, fontSize: 15 }}>
              <button type="button" onClick={() => onGo(i)} style={{ background: "none", border: 0, padding: 0, color: color.primaryText, textDecoration: "underline", fontSize: 15, cursor: "pointer", textAlign: "left" }}>
                {s.title}
              </button>
              <span style={{ color: sp.requiredAnswered === sp.required ? "#065F46" : color.text, fontWeight: font.weight.bold }}>
                {sp.answered} of {sp.questions} answered
              </span>
            </li>
          );
        })}
      </ul>
      {missingItems.length ? (
        <div role="alert" style={{ display: "grid", gap: space.sm, padding: space.md, borderRadius: radius.md, border: `1.5px solid ${color.dangerBorder}`, background: "#FEF2F2" }}>
          <strong style={{ fontSize: 16 }}>
            {missingItems.length === 1 ? "1 question still needs an answer" : `${missingItems.length} questions still need an answer`}
          </strong>
          <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "grid", gap: space.sm }}>
            {missingItems.slice(0, 12).map((m) => (
              <li key={m.id}>
                <button
                  type="button"
                  onClick={() => onGo(m.si, m.id)}
                  style={{ background: "none", border: 0, padding: 0, color: color.primaryText, textDecoration: "underline", fontSize: 15, cursor: "pointer", textAlign: "left" }}
                >
                  {m.title}: {m.about ? `${m.about}, ` : ""}
                  {m.text}
                </button>
              </li>
            ))}
          </ul>
          {missingItems.length > 12 ? <div style={{ fontSize: 14 }}>…and {missingItems.length - 12} more.</div> : null}
        </div>
      ) : (
        <p style={{ margin: 0, fontSize: 16 }}>Every required question is answered.</p>
      )}
      {submitError ? (
        <div role="alert" style={{ color: color.danger, fontWeight: font.weight.bold }}>
          {submitError}
        </div>
      ) : null}
      {confirming ? (
        <div style={{ display: "grid", gap: space.md, padding: space.md, borderRadius: radius.md, background: color.surfaceMuted, border: `1px solid ${color.border}` }}>
          <p style={{ margin: 0, fontSize: 16 }}>Submit your answers? You won't be able to change them afterwards.</p>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: space.sm }}>
            <NavButton onClick={() => setConfirming(false)} disabled={submitting}>
              Go back
            </NavButton>
            <NavButton primary onClick={onSubmit} disabled={submitting}>
              {submitting ? "Submitting…" : "Yes, submit"}
            </NavButton>
          </div>
        </div>
      ) : (
        <NavButton primary disabled={missingItems.length > 0} onClick={() => setConfirming(true)}>
          Submit my answers
        </NavButton>
      )}
    </Panel>
  );
}

function Summary({ form, answers, wide, justSubmitted }) {
  return (
    <div style={{ display: "grid", gap: space.lg }}>
      <Panel>
        <h1 style={{ margin: 0, fontSize: 24 }}>{justSubmitted ? "Thank you" : "Your answers have been submitted"}</h1>
        <p style={{ margin: 0, fontSize: 16 }}>
          {justSubmitted ? "Your answers have been submitted. " : ""}
          {form.evaluation.consultancy} will use them to prepare the board evaluation report. You can close this page.
        </p>
        {form.submitted_at ? (
          <p style={{ margin: 0, color: color.textMuted, fontSize: 14 }}>Submitted on {formatDate(form.submitted_at.slice(0, 10))}.</p>
        ) : null}
      </Panel>
      <details style={{ background: color.surface, border: `1px solid ${color.border}`, borderRadius: radius.lg, padding: space.lg }}>
        <summary style={{ cursor: "pointer", fontWeight: font.weight.bold, fontSize: 16, minHeight: 32 }}>See a summary of your answers</summary>
        <div style={{ display: "grid", gap: space.xl, marginTop: space.lg }}>
          {form.sections.map((s) => (
            <section key={s.key} aria-label={s.title} style={{ display: "grid", gap: space.lg }}>
              <h2 style={{ margin: 0, fontSize: 19 }}>{s.title}</h2>
              <SectionView section={s} answers={answers} onAnswer={() => {}} invalid={{}} wide={wide} readOnly />
            </section>
          ))}
        </div>
      </details>
    </div>
  );
}

function Problem({ title, message }) {
  return (
    <Panel style={{ maxWidth: 640, margin: "0 auto" }}>
      <h1 style={{ margin: 0, fontSize: 22 }}>{title}</h1>
      <p style={{ margin: 0, fontSize: 16 }}>{message}</p>
    </Panel>
  );
}

const PROBLEM_TITLES = {
  invalid_link: "This link doesn't work",
  expired: "The deadline has passed",
  closed: "This evaluation has closed",
  being_updated: "Your questions are being updated",
  submitted: "Already submitted",
  network: "Can't connect",
};

export default function FormPage() {
  const { token } = useParams();
  const wide = useWideScreen();
  const [form, setForm] = useState(null);
  const [loadError, setLoadError] = useState(null);
  const [answers, setAnswers] = useState({});
  const [screen, setScreen] = useState("welcome"); // "welcome" | section index | "review" | "done"
  const [submitting, setSubmitting] = useState(false);
  const [justSubmitted, setJustSubmitted] = useState(false);
  const [submitError, setSubmitError] = useState("");
  const [serverMissing, setServerMissing] = useState([]);
  const focusAfter = useRef(null);
  const { queue, saveNow, status, savedAt, invalid, stopError } = useAutosave(token);

  useEffect(() => {
    let alive = true;
    formApi
      .load(token)
      .then((f) => {
        if (!alive) return;
        setForm(f);
        setAnswers(f.answers || {});
        if (f.status === "submitted") setScreen("done");
      })
      .catch((e) => alive && setLoadError(e));
    return () => {
      alive = false;
    };
  }, [token]);

  const all = useMemo(() => (form ? allQuestions(form) : []), [form]);
  const p = useMemo(() => progress(all, answers), [all, answers]);

  const onAnswer = useCallback(
    (id, value) => {
      setAnswers((a) => ({ ...a, [id]: value }));
      setServerMissing((m) => m.filter((x) => x.question_id !== id));
      queue(id, value);
    },
    [queue]
  );

  const go = useCallback((target, questionId) => {
    focusAfter.current = questionId ? `q-${questionId}` : "section-heading";
    setScreen(target);
  }, []);

  useEffect(() => {
    const id = focusAfter.current;
    if (!id) {
      window.scrollTo(0, 0);
      return;
    }
    focusAfter.current = null;
    const el = document.getElementById(id) || document.getElementById("section-heading");
    if (id === "section-heading") window.scrollTo(0, 0); // new section: start at the top, progress in view
    if (el) {
      if (id !== "section-heading") el.scrollIntoView({ block: "start" });
      const focusable = el.matches("input, select, textarea, h1, h2") ? el : el.querySelector("input, select, textarea");
      (focusable || el).focus?.({ preventScroll: true });
    }
  }, [screen]);

  const start = () => {
    const firstOpen = form.sections.findIndex((s) => progress(sectionQuestions(s), answers).missing.length > 0);
    go(firstOpen === -1 ? 0 : firstOpen);
  };

  const submit = async () => {
    setSubmitting(true);
    setSubmitError("");
    const saved = await saveNow();
    if (!saved) {
      setSubmitError("Some answers haven't saved yet. Check your connection, then try again.");
      setSubmitting(false);
      return;
    }
    try {
      const r = await formApi.submit(token);
      setForm((f) => ({ ...f, status: "submitted", submitted_at: r.submitted_at }));
      setJustSubmitted(true);
      setScreen("done");
    } catch (e) {
      if (e.code === "missing_answers") setServerMissing(e.missing);
      setSubmitError(e.message);
    } finally {
      setSubmitting(false);
    }
  };

  if (loadError) {
    return (
      <Shell>
        <Problem title={PROBLEM_TITLES[loadError.code] || "Something went wrong"} message={loadError.message} />
      </Shell>
    );
  }
  if (!form) {
    return (
      <Shell>
        <p role="status" style={{ color: color.textMuted, fontSize: 16 }}>
          Loading your questionnaire…
        </p>
      </Shell>
    );
  }

  const statusLine = <SaveStatus status={status} savedAt={savedAt} />;
  if (stopError && screen !== "done") {
    return (
      <Shell form={form} status={statusLine}>
        <Problem title={PROBLEM_TITLES[stopError.code] || "Your answers can't be saved"} message={stopError.message} />
      </Shell>
    );
  }
  if (screen === "done") {
    return (
      <Shell form={form}>
        <Summary form={form} answers={answers} wide={wide} justSubmitted={justSubmitted} />
      </Shell>
    );
  }
  if (screen === "welcome") {
    return (
      <Shell form={form} status={statusLine}>
        <Welcome form={form} onStart={start} done={p.requiredAnswered} total={p.required} />
      </Shell>
    );
  }

  const top = (
    <div style={{ display: "grid", gap: space.md, marginBottom: space.lg }}>
      <ProgressBar done={p.requiredAnswered} total={p.required} />
      <SectionList sections={form.sections} current={screen === "review" ? -1 : screen} answers={answers} onGo={(i) => go(i)} />
    </div>
  );

  if (screen === "review") {
    return (
      <Shell form={form} status={statusLine}>
        {top}
        <Review
          form={form}
          answers={answers}
          onGo={go}
          onSubmit={submit}
          submitting={submitting}
          submitError={submitError}
          serverMissing={serverMissing}
        />
      </Shell>
    );
  }

  const section = form.sections[screen];
  const last = screen === form.sections.length - 1;
  return (
    <Shell form={form} status={statusLine}>
      {top}
      <Panel>
        <h2 id="section-heading" tabIndex={-1} style={{ margin: 0, fontSize: 22 }}>
          {section.title}
          <span style={{ display: "block", fontSize: 14, fontWeight: font.weight.regular, color: color.textMuted }}>
            Section {screen + 1} of {form.sections.length}
          </span>
        </h2>
        <SectionView section={section} answers={answers} onAnswer={onAnswer} invalid={invalid} wide={wide} />
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: space.sm }}>
          <NavButton onClick={() => go(screen === 0 ? "welcome" : screen - 1)}>← Back</NavButton>
          <NavButton primary onClick={() => go(last ? "review" : screen + 1)}>
            {last ? "Check and submit" : "Next section →"}
          </NavButton>
        </div>
      </Panel>
    </Shell>
  );
}
