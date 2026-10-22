"""
app.domain.governance
---------------------
Reference data for the governance code library: the codes we hold, which codes
apply to which sector by default, and normalisation of the free-text
Evaluation.sector.

Code metadata was checked against each source document (see `notes` where the
document does not state an exact date). Seeded by the Alembic migrations (which
keep frozen copies) and by scripts/seed_reference_data.py.
"""

from __future__ import annotations

from datetime import date
from typing import Dict, List, Optional

GOVERNANCE_CODES: List[Dict[str, object]] = [
    # Base code first: the others reference it through supplements_code.
    {
        "code": "NCCG_2018",
        "title": "Nigerian Code of Corporate Governance 2018",
        "issuer": "Financial Reporting Council of Nigeria (FRC)",
        "sector": None,
        "version": "2018",
        "issued_date": None,
        "effective_date": None,
        "status": "current",
        "supplements_code": None,
        "source_filename": "Nigerian-Code-of-Corporate-Governance-2018.pdf",
        "notes": (
            "The document states no issue or effective date; CBN 2023 says the FRC issued it in 2019. "
            "It lists the sectoral codes it replaced, including SEC 2011, NAICOM 2009, CBN 2014, "
            "NCC 2016 and PenCom 2008."
        ),
    },
    {
        "code": "NAICOM_2021",
        "title": "Corporate Governance Guidelines for Insurance and Reinsurance Companies in Nigeria 2021",
        "issuer": "National Insurance Commission (NAICOM)",
        "sector": "insurance",
        "version": "2021",
        "issued_date": date(2021, 3, 17),
        "effective_date": date(2021, 6, 1),
        "status": "current",
        "supplements_code": "NCCG_2018",
        "source_filename": "NAICOM-CORPORATE-GOVERNANCE-GUIDELINES.pdf",
        "notes": (
            "Read and interpreted in conjunction with NCCG 2018 (section 1.0 v); replaces the NAICOM Code of "
            "Good Corporate Governance for the Insurance Industry 2009. Dates are handwritten on the scanned "
            "final page (sections 12.0-13.0)."
        ),
    },
    {
        "code": "CBN_BANKS_2023",
        "title": "Corporate Governance Guidelines for Commercial, Merchant, Non-Interest and Payment Service Banks in Nigeria",
        "issuer": "Central Bank of Nigeria (CBN)",
        "sector": "banking",
        "version": "2023",
        "issued_date": date(2023, 7, 13),
        "effective_date": date(2023, 8, 1),
        "status": "current",
        "supplements_code": "NCCG_2018",
        "source_filename": "CBN Circular and Guidelines for Corporate Governance Code 2023.pdf",
        "notes": (
            "Adapts the NCCG 2018 principles; NCCG 2018 and these Guidelines both apply. States that NCCG 2018 "
            "replaced all sectoral codes. The same PDF also contains the CBN Corporate Governance Guidelines "
            "for Financial Holding Companies in Nigeria (same dates), not registered separately."
        ),
    },
    {
        "code": "CBN_MFB_2018",
        "title": "Code of Corporate Governance for Microfinance Banks in Nigeria",
        "issuer": "Central Bank of Nigeria (CBN)",
        "sector": "banking",
        "version": "2018",
        "issued_date": date(2018, 10, 24),
        "effective_date": date(2019, 4, 1),
        "status": "current",
        "supplements_code": None,
        "source_filename": "CODE-OF-CORPORATE-GOVERNANCE-FOR-MICROFINANCE-BANKS-IN-NIGERIA.pdf",
        "notes": "Issued before NCCG 2018 was published and does not refer to it, so not marked as a supplement.",
    },
    {
        "code": "PENCOM_2025",
        "title": "Revised Guideline on Corporate Governance for Licensed Pension Fund Operators",
        "issuer": "National Pension Commission (PenCom)",
        "sector": "pension",
        "version": "2025",
        "issued_date": None,
        "effective_date": None,
        "status": "current",
        "supplements_code": "NCCG_2018",
        "source_filename": "Revised-Guideline-on-Corporate-Governance-for-LPFOs-22-September-2025.pdf",
        "notes": (
            "To be used in conjunction with NCCG 2018. Cover dated September 2025 (the source filename says "
            "22 September 2025). Effective from the date of issuance and applies retroactively (section 8.1); "
            "supersedes previous PenCom guidelines."
        ),
    },
    {
        "code": "NCC_2025",
        "title": "Guidelines on Corporate Governance",
        "issuer": "Nigerian Communications Commission (NCC)",
        "sector": "telecommunications",
        "version": "2025",
        "issued_date": date(2025, 3, 3),
        "effective_date": None,
        "status": "current",
        "supplements_code": "NCCG_2018",
        "source_filename": "Guidelines-on-Corporate-Gov.pdf",
        "notes": (
            "Complements NCCG 2018, which licensees apply as the minimum benchmark. 'Made at Abuja this 3rd day "
            "of March 2025'; no separate effective date stated."
        ),
    },
    {
        "code": "SME_2024",
        "title": "SME Corporate Governance Guidelines",
        "issuer": "Financial Reporting Council of Nigeria (FRC)",
        "sector": "sme",
        "version": "2024",
        "issued_date": None,
        "effective_date": None,
        "status": "current",
        "supplements_code": None,
        "source_filename": "SME Corporate Governance Guidelines 2024.pdf",
        "notes": (
            "FRC adaptation of NCCG principles for MSMEs (standalone, not read with NCCG). Cover dated May 2024; "
            "applies from an effective date decided by the Council."
        ),
    },
    {
        "code": "SEC_2011",
        "title": "Code of Corporate Governance for Public Companies in Nigeria 2011",
        "issuer": "Securities and Exchange Commission (SEC)",
        "sector": None,
        "version": "2011",
        "issued_date": date(2011, 1, 27),
        "effective_date": date(2011, 4, 1),
        "status": "historical",
        "supplements_code": None,
        "source_filename": "SEC code of corporate governance 2011.pdf",
        "notes": (
            "CBN 2023 states NCCG 2018 replaced sectoral codes; awaiting client confirmation of whether "
            "SEC 2011 still applies."
        ),
    },
]

GOVERNANCE_CODE_KEYS = [str(c["code"]) for c in GOVERNANCE_CODES]
