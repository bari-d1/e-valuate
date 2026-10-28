import { useEffect, useState } from "react";

/** True on screens at least `min` pixels wide (tables and side-by-side layouts); false on phones. */
export default function useWideScreen(min = 760) {
  const query = `(min-width: ${min}px)`;
  const [wide, setWide] = useState(() => typeof window !== "undefined" && window.matchMedia(query).matches);
  useEffect(() => {
    const m = window.matchMedia(query);
    const on = () => setWide(m.matches);
    m.addEventListener("change", on);
    return () => m.removeEventListener("change", on);
  }, [query]);
  return wide;
}
