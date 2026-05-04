"""Agency normalization helpers for ingestion."""

from __future__ import annotations

import re
from typing import Dict


def _clean_agency_name(value: str) -> str:
    """Normalize spacing and punctuation for matching."""
    cleaned = re.sub(r"\s+", " ", (value or "").strip())
    return cleaned.upper()


def normalize_agency(raw_agency_description: str) -> Dict[str, str]:
    """Return canonical, parent, and sub-agency labels."""
    raw_value = (raw_agency_description or "").strip()
    normalized = _clean_agency_name(raw_value)
    if not normalized:
        return {
            "canonical_agency": "",
            "parent_agency": "",
            "sub_agency": "",
        }

    parent_agency = normalized.title()
    canonical_agency = normalized.title()
    sub_agency = ""

    if "HEALTH AND HUMAN SERVICES" in normalized:
        parent_agency = "Department Of Health And Human Services"
        if any(token in normalized for token in ["AGING", "PUBLIC HEALTH", "SOCIAL SERVICES", "MEDICAID"]):
            canonical_agency = normalized.title()
            sub_agency = normalized.title()
        else:
            canonical_agency = parent_agency
    elif "TRANSPORTATION" in normalized:
        parent_agency = "Department Of Transportation"
        canonical_agency = normalized.title()
        if normalized != "DEPARTMENT OF TRANSPORTATION":
            sub_agency = normalized.title()
    elif "UNIVERSITY OF NORTH CAROLINA" in normalized or normalized.startswith("UNC "):
        parent_agency = "The University Of North Carolina"
        canonical_agency = normalized.title()
        if canonical_agency != parent_agency:
            sub_agency = canonical_agency
    elif "PUBLIC SAFETY" in normalized:
        parent_agency = "Department Of Public Safety"
        canonical_agency = normalized.title()
        if canonical_agency != parent_agency:
            sub_agency = canonical_agency
    elif "ADMINISTRATIVE OFFICE OF THE COURTS" in normalized:
        parent_agency = "Administrative Office Of The Courts"
        canonical_agency = parent_agency
    elif normalized.startswith("OFFICE OF "):
        parent_agency = normalized.title()
        canonical_agency = parent_agency

    return {
        "canonical_agency": canonical_agency,
        "parent_agency": parent_agency,
        "sub_agency": sub_agency,
    }
