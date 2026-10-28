/** Pure helpers for the participant form: visibility of follow-ups, answered checks and progress. */

/** Every answerable question in a section, with peer grid cells listed as rating questions. */
export function sectionQuestions(section) {
  const out = [];
  for (const b of section.blocks) {
    if (b.kind === "grid") {
      for (const s of b.statements) {
        for (const [colleague, id] of Object.entries(s.cells)) {
          out.push({ id, answer_type: "rating", required: b.required, follows: null, confirm: null, grid: true, colleague });
        }
      }
    } else {
      out.push(b);
    }
  }
  return out;
}

export function allQuestions(form) {
  return form.sections.flatMap(sectionQuestions);
}

export function hasAnswer(q, v) {
  if (v === null || v === undefined) return false;
  if (q.confirm) return v.status === "correct" || v.status === "needs_updating";
  if (typeof v === "string") return v.trim().length > 0;
  if (Array.isArray(v)) return v.length > 0;
  return true;
}

/** Follow-ups show only when the question they follow is shown and has the right answer. */
export function visibility(questions, answers) {
  const byId = new Map(questions.map((q) => [q.id, q]));
  const seen = new Map();
  const shown = (q, depth = 0) => {
    if (seen.has(q.id)) return seen.get(q.id);
    let ok = true;
    if (q.follows && depth < 10) {
      const parent = byId.get(q.follows.question_id);
      ok = !!parent && shown(parent, depth + 1) && answers[parent.id] === q.follows.answer;
    }
    seen.set(q.id, ok);
    return ok;
  };
  questions.forEach((q) => shown(q));
  return seen;
}

/** Answered and required counts over the visible questions. */
export function progress(questions, answers) {
  const vis = visibility(questions, answers);
  const shown = questions.filter((q) => vis.get(q.id));
  const required = shown.filter((q) => q.required);
  return {
    questions: shown.length,
    answered: shown.filter((q) => hasAnswer(q, answers[q.id])).length,
    required: required.length,
    requiredAnswered: required.filter((q) => hasAnswer(q, answers[q.id])).length,
    missing: required.filter((q) => !hasAnswer(q, answers[q.id])),
  };
}

export function formatDate(iso) {
  if (!iso) return "";
  const d = new Date(`${iso}T00:00:00`);
  return d.toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" });
}

/** An answer as plain words, for the review and the read-only summary. */
export function answerText(q, v, scale) {
  if (!hasAnswer(q, v)) return "Not answered";
  if (q.confirm) {
    if (v.status === "correct") return "Correct";
    return v.correction ? `Needs updating: ${v.correction}` : "Needs updating";
  }
  if (q.answer_type === "rating") {
    if (v === "dont_know") return "Don't know";
    const point = (scale || q.scale)?.points?.find((p) => p.value === v);
    return point?.label ? `${v} · ${point.label}` : String(v);
  }
  if (q.answer_type === "yesno") return v === "yes" ? "Yes" : "No";
  if (Array.isArray(v)) return v.join("; ");
  return String(v);
}
