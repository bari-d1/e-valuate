import { useCallback, useEffect, useRef, useState } from "react";
import { formApi } from "../../api/formApi.js";

const PAUSE_MS = 800; // save after a short pause in answering or typing
const RETRY_MS = [2000, 4000, 8000, 15000, 30000];

/**
 * Save answers as the participant goes.
 *
 * queue(questionId, value) records a change; changes are sent together after a short pause.
 * status: "idle" | "pending" | "saving" | "saved" | "retrying" | "stopped".
 * Failed saves are retried with growing delays; answers the server rejects come back in
 * `invalid` ({questionId: message}). A "stopped" save (the form was submitted, closed or is being
 * updated) reports `stopError` and doesn't retry. Leaving with unsaved changes asks first.
 */
export default function useAutosave(token, { onSaved } = {}) {
  const pending = useRef(new Map()); // questionId -> value not yet sent
  const inFlight = useRef(false);
  const timer = useRef(null);
  const attempt = useRef(0);
  const [status, setStatus] = useState("idle");
  const [savedAt, setSavedAt] = useState(null);
  const [invalid, setInvalid] = useState({});
  const [stopError, setStopError] = useState(null);
  const onSavedRef = useRef(onSaved);
  const flushRef = useRef(null); // retries and follow-up saves call the latest flush
  useEffect(() => {
    onSavedRef.current = onSaved;
  }, [onSaved]);

  const flush = useCallback(async () => {
    clearTimeout(timer.current);
    if (inFlight.current || !pending.current.size || stopError) return;
    const batch = new Map(pending.current);
    inFlight.current = true;
    setStatus("saving");
    try {
      const res = await formApi.save(
        token,
        [...batch].map(([question_id, value]) => ({ question_id, value }))
      );
      for (const [id, v] of batch) if (pending.current.get(id) === v) pending.current.delete(id);
      attempt.current = 0;
      setInvalid((cur) => {
        const next = { ...cur };
        for (const id of batch.keys()) delete next[id];
        return next;
      });
      setSavedAt(new Date());
      onSavedRef.current?.(res);
      setStatus(pending.current.size ? "pending" : "saved");
    } catch (e) {
      if (e.status === 422 && e.errors?.length) {
        // Keep the valid ones queued and report the rest beside their questions
        const bad = Object.fromEntries(e.errors.map((x) => [x.question_id, x.message]));
        for (const id of Object.keys(bad)) pending.current.delete(id);
        setInvalid((cur) => ({ ...cur, ...bad }));
        setStatus(pending.current.size ? "pending" : "saved");
      } else if ([404, 409, 410].includes(e.status)) {
        setStopError(e);
        setStatus("stopped");
      } else {
        const wait = RETRY_MS[Math.min(attempt.current, RETRY_MS.length - 1)];
        attempt.current += 1;
        setStatus("retrying");
        inFlight.current = false;
        timer.current = setTimeout(() => flushRef.current(), wait);
        return;
      }
    }
    inFlight.current = false;
    if (pending.current.size) timer.current = setTimeout(() => flushRef.current(), PAUSE_MS);
  }, [token, stopError]);
  useEffect(() => {
    flushRef.current = flush;
  }, [flush]);

  const queue = useCallback(
    (questionId, value) => {
      pending.current.set(questionId, value);
      if (status !== "retrying") setStatus("pending");
      clearTimeout(timer.current);
      timer.current = setTimeout(flush, PAUSE_MS);
    },
    [flush, status]
  );

  /** Send everything now; resolves true when nothing is left unsaved. */
  const saveNow = useCallback(async () => {
    for (let i = 0; i < 20 && (pending.current.size || inFlight.current); i += 1) {
      if (!inFlight.current) await flush();
      else await new Promise((r) => setTimeout(r, 150));
      if (stopError) break;
    }
    return pending.current.size === 0 && !inFlight.current;
  }, [flush, stopError]);

  useEffect(() => {
    const warn = (e) => {
      if (pending.current.size || inFlight.current) {
        e.preventDefault();
        e.returnValue = "";
      }
    };
    window.addEventListener("beforeunload", warn);
    return () => {
      window.removeEventListener("beforeunload", warn);
      clearTimeout(timer.current);
    };
  }, []);

  return { queue, saveNow, status, savedAt, invalid, stopError };
}
