import { useEffect, useState } from "react";
import { questionBankApi } from "../../../api/questionBankApi.js";

/** Non-component helpers shared by the question bank pages. */

export const STATUS_TONE = { draft: "amber", approved: "green", retired: "gray" };

export const ANSWER_TYPE_LABELS = {
  rating: "Rating",
  yesno: "Yes / no",
  comment: "Comment",
  single_select: "Single choice",
  multi_select: "Multiple choice",
};

export const BINDING_LABELS = {
  none: "Once (the board or the secretariat)",
  self: "About the respondent themselves",
  each_subject_instance: "Once per person or committee of these types",
  respondent_committees: "Once per committee the respondent sits on",
};

export const TAG_LABELS = {
  subject_types: "Subject types",
  subject_binding: "Subject binding",
  respondent_rule: "Respondent rule",
  activation_rule: "Activation rule",
  theme: "Theme",
  evidence_source: "Evidence source",
  governance_refs: "Governance clauses",
};

/** {placeholder} keys used in a text, in order, without duplicates. */
export function placeholdersIn(...texts) {
  const out = [];
  texts.forEach((t) => {
    for (const m of String(t || "").matchAll(/\{([a-z_][a-z0-9_.]*)\}/g)) if (!out.includes(m[1])) out.push(m[1]);
  });
  return out;
}

/** Name for a code from a [{code, name}] list, falling back to the code. */
export function nameOf(list, code) {
  return (list || []).find((x) => x.code === code)?.name || code;
}

/** Load /question-bank/meta once per page. */
export function useBankMeta(run) {
  const [meta, setMeta] = useState(null);
  useEffect(() => {
    run(async () => setMeta(await questionBankApi.meta()));
  }, [run]);
  return meta;
}
