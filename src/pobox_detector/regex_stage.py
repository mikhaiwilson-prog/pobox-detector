"""Stage 1: regex-based PO Box classifier. Pure-function, zero network."""
from __future__ import annotations
import re

PO_BOX_PATTERNS = [
    re.compile(r"\bp\.?\s*o\.?\s*box\b", re.IGNORECASE),
    re.compile(r"\bpost\s*office\s*box\b", re.IGNORECASE),
    re.compile(r"\bpo\s*#\s*\d", re.IGNORECASE),
    re.compile(r"\bpmb\b", re.IGNORECASE),
    re.compile(r"\bpostal\s*box\b", re.IGNORECASE),
    re.compile(r"\bpo\s*drawer\b", re.IGNORECASE),
    re.compile(r"\block\s*box\b", re.IGNORECASE),
]

STREET_SUFFIX = re.compile(
    r"\b\d+\b.*?\b("
    r"st|street|ave|avenue|blvd|boulevard|rd|road|dr|drive|ln|lane|"
    r"way|ct|court|pl|place|pkwy|parkway|hwy|highway|cir|circle|"
    r"ter|terrace|sq|square|trl|trail|loop"
    r")\b\.?",
    re.IGNORECASE,
)

UNIT_ONLY = re.compile(
    r"^\s*(ste|suite|unit|apt|apartment|floor|fl|#)\b.{0,8}$",
    re.IGNORECASE,
)

Classification = str  # "po_box" | "not_po_box" | "uncertain"


def classify(address: str) -> tuple[Classification, str]:
    """Return (classification, reason)."""
    if not address or not address.strip():
        return "uncertain", "empty"

    for pat in PO_BOX_PATTERNS:
        m = pat.search(address)
        if m:
            return "po_box", f"matched:{m.group(0)!r}"

    if STREET_SUFFIX.search(address):
        return "not_po_box", "street_suffix"

    stripped = address.strip()
    if len(stripped) < 10:
        return "uncertain", "too_short"
    if UNIT_ONLY.match(stripped):
        return "uncertain", "unit_only"

    ascii_count = sum(1 for c in stripped if c.isascii())
    if ascii_count / len(stripped) < 0.7:
        return "uncertain", "non_ascii_heavy"

    return "uncertain", "no_signal"
