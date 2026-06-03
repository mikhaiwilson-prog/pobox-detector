"""Stage 1: positive-only PO Box / CMRA screening. Pure function, zero network.

CRITICAL: this stage may BLOCK or flag for REVIEW, but it NEVER clears an
address. A street suffix is not evidence of a physical address — CMRAs and USPS
PO Box Street Addressing deliberately use street-style formats (e.g.
"500 Main Street #59" that still delivers to a PO Box). Only an authoritative
provider result may ALLOW (see decision.py).
"""
from __future__ import annotations

import re

from .normalize import normalize_for_match

# Unambiguous PO Box / CMRA / private-mailbox tokens -> BLOCK.
_BLOCK: list[tuple[str, re.Pattern[str]]] = [
    ("po_box", re.compile(r"\bp\.?\s*o\.?\s*box\b", re.I)),
    ("post_office_box", re.compile(r"\bpost\s*office\s*box\b", re.I)),
    ("pob", re.compile(r"\bp\.?\s*o\.?\s*b\b", re.I)),
    ("po_hash", re.compile(r"\bp\.?\s*o\.?\s*#\s*\d", re.I)),
    ("post_box", re.compile(r"\bpost(?:al)?\s*box\b", re.I)),
    ("po_drawer", re.compile(r"\bp\.?\s*o\.?\s*drawer\b", re.I)),
    ("postal_drawer", re.compile(r"\bpostal\s*drawer\b", re.I)),
    ("pmb", re.compile(r"\bp\.?\s*m\.?\s*b\b", re.I)),
    ("private_mailbox", re.compile(r"\bprivate\s*mail\s*box\b", re.I)),
    ("cmra", re.compile(r"\bcmra\b", re.I)),
    ("cmra_full", re.compile(r"\bcommercial\s*mail\s*receiving\s*agency\b", re.I)),
    ("lock_box", re.compile(r"\block\s*box\b", re.I)),
    ("pbsa", re.compile(r"\bpo\s*box\s*street\s*address", re.I)),
]

# Broad / easily-spoofed mailbox-ish tokens -> REVIEW. Never an instant block
# (too many false positives), never an allow. The provider makes the call; if
# it cannot, we floor at review.
_REVIEW: list[tuple[str, re.Pattern[str]]] = [
    ("general_delivery", re.compile(r"\bgeneral\s+delivery\b", re.I)),
    ("private_box", re.compile(r"\bprivate\s*box\b", re.I)),
    ("bare_drawer", re.compile(r"\bdrawer\s+\d", re.I)),
    ("bare_mailbox", re.compile(r"\bmail\s*box\s+\d", re.I)),
    ("bare_box", re.compile(r"\bbox\s+\d", re.I)),
]

Signal = str  # "block" | "review" | "none"


def screen(text: str) -> tuple[Signal, str]:
    """Screen normalized address text. Returns (signal, reason).

    "block"  -> confirmed PO/CMRA token; terminal.
    "review" -> ambiguous mailbox-ish token; needs provider adjudication.
    "none"   -> no PO indicator; still requires provider verification to ALLOW.
    """
    norm = normalize_for_match(text)
    if not norm:
        return "none", "empty"
    for name, pat in _BLOCK:
        m = pat.search(norm)
        if m:
            return "block", f"regex:{name}:{m.group(0).strip()!r}"
    for name, pat in _REVIEW:
        m = pat.search(norm)
        if m:
            return "review", f"regex:{name}:{m.group(0).strip()!r}"
    return "none", "no_po_indicator"
