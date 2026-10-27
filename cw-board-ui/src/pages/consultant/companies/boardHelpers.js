import { useEffect, useState } from "react";
import { boardApi } from "../../../api/orgApi.js";

/** Non-component helpers for the Board tab and member pages. */

export function roleLabel(registry, key) {
  if (!key) return null;
  const r = registry && registry.governance_roles.find((x) => x.key === key);
  return r ? r.label : key;
}

/** Board member registry (fact groups, roles, sources), loaded once per page. */
export function useMemberRegistry(run) {
  const [registry, setRegistry] = useState(null);
  useEffect(() => {
    run(async () => setRegistry(await boardApi.registry()));
  }, [run]);
  return registry;
}

export const TRISTATE = [
  { key: "yes", label: "Yes" },
  { key: "no", label: "No" },
  { key: "unknown", label: "Unknown" },
];
