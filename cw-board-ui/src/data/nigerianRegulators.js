// Nigerian regulators a board evaluation may need to reference.
// PROVISIONAL — a researched starting point; replace with the client-approved list when available.
// `code` is what gets saved on the evaluation (keep it stable once evaluations use it).

export const REGULATOR_GROUPS = [
  {
    group: "Issue corporate governance codes",
    items: [
      { code: "FRC", name: "Financial Reporting Council of Nigeria", note: "Nigerian Code of Corporate Governance 2018" },
      { code: "CBN", name: "Central Bank of Nigeria", note: "Banks and other financial institutions" },
      { code: "SEC", name: "Securities and Exchange Commission", note: "Public companies and capital market operators" },
      { code: "NAICOM", name: "National Insurance Commission", note: "Insurers and reinsurers" },
      { code: "PenCom", name: "National Pension Commission", note: "Pension fund administrators and custodians" },
      { code: "NCC", name: "Nigerian Communications Commission", note: "Telecommunications companies" },
    ],
  },
  {
    group: "Other financial sector",
    items: [
      { code: "NDIC", name: "Nigeria Deposit Insurance Corporation", note: "Deposit-taking institutions" },
      { code: "NGX RegCo", name: "Nigerian Exchange Regulation Limited", note: "Listing rules for listed companies" },
    ],
  },
  {
    group: "Energy",
    items: [
      { code: "NUPRC", name: "Nigerian Upstream Petroleum Regulatory Commission", note: "Oil and gas exploration and production" },
      { code: "NMDPRA", name: "Nigerian Midstream and Downstream Petroleum Regulatory Authority", note: "Refining, gas and distribution" },
      { code: "NERC", name: "Nigerian Electricity Regulatory Commission", note: "Electricity companies" },
    ],
  },
  {
    group: "Cross-sector",
    items: [
      { code: "CAC", name: "Corporate Affairs Commission", note: "Company registration and CAMA 2020" },
      { code: "NDPC", name: "Nigeria Data Protection Commission", note: "Data protection (NDPA 2023)" },
      { code: "FCCPC", name: "Federal Competition and Consumer Protection Commission", note: "Competition and consumer protection" },
    ],
  },
];

export const REGULATOR_CODES = REGULATOR_GROUPS.flatMap((g) => g.items.map((r) => r.code));
