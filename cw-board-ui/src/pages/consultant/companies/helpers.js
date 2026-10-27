import { useCallback, useState } from "react";
import { color, font, radius } from "../../../theme.js";

/** Non-component helpers shared by the company pages. */

export const visuallyHidden = {
  position: "absolute",
  width: 1,
  height: 1,
  overflow: "hidden",
  clip: "rect(0 0 0 0)",
  whiteSpace: "nowrap",
};

export function inputCss(extra = {}) {
  return {
    width: "100%",
    boxSizing: "border-box",
    padding: "8px 10px",
    fontSize: font.body,
    border: `1px solid ${color.borderStrong}`,
    borderRadius: radius.sm,
    background: color.surface,
    color: color.text,
    ...extra,
  };
}

export function useAsync() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const run = useCallback(async (fn) => {
    setBusy(true);
    setError("");
    try {
      return await fn();
    } catch (e) {
      setError(e?.message || String(e));
      return undefined;
    } finally {
      setBusy(false);
    }
  }, []);
  return { busy, error, setError, run };
}

export { formatDate } from "../../../utils/format.js";
