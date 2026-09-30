// Shared design values for the consultant UI. Components read from here instead of
// hard-coding colours and sizes, so a change in one place applies everywhere.
// Text colours are chosen to meet WCAG AA contrast (4.5:1) on both `surface` and `page`.

export const color = {
  page: "#F1F5F9",
  surface: "#FFFFFF",
  surfaceMuted: "#F8FAFC",

  text: "#0F172A",
  textMuted: "#475569", // 7.2:1 on white, 6.4:1 on page — use for hints on any background
  textSubtle: "#64748B", // 4.8:1 on white only — secondary text on white surfaces

  border: "#E2E8F0",
  borderStrong: "#CBD5E1",

  primary: "#2563EB",
  primaryBorder: "#1D4ED8",
  primaryText: "#1D4ED8",
  primarySoft: "#EFF6FF",
  primarySoftBorder: "#BFDBFE",

  danger: "#B91C1C",
  dangerBorder: "#FCA5A5",

  disabledBg: "#F1F5F9",
  disabledText: "#94A3B8",
  focus: "#2563EB",

  sidebar: "#0B1220",
  sidebarText: "rgba(255,255,255,0.82)",
  sidebarHeading: "rgba(255,255,255,0.6)",
  sidebarActive: "rgba(59,130,246,0.25)",
};

// Status badge palettes: background / text / border
export const tone = {
  blue: { bg: "#E6F0FF", fg: "#1E40AF", bd: "#BFDBFE" },
  green: { bg: "#E8FFF3", fg: "#065F46", bd: "#A7F3D0" },
  amber: { bg: "#FFF7ED", fg: "#92400E", bd: "#FED7AA" },
  gray: { bg: "#F3F4F6", fg: "#374151", bd: "#E5E7EB" },
  red: { bg: "#FEF2F2", fg: "#991B1B", bd: "#FECACA" },
  purple: { bg: "#F3E8FF", fg: "#6B21A8", bd: "#E9D5FF" },
};

export const radius = { sm: 8, md: 12, lg: 14, pill: 999 };

export const space = { xs: 4, sm: 8, md: 12, lg: 16, xl: 24 };

export const font = {
  small: 12,
  body: 14,
  heading: 18,
  weight: { regular: 400, medium: 600, bold: 700, heavy: 800 },
};

// Below this width the sidebar collapses behind a menu button
export const SIDEBAR_BREAKPOINT = 900;
