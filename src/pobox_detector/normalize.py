"""Input normalization — runs BEFORE any regex or provider call.

Obfuscated mailbox addresses (zero-width joiners, Greek/Cyrillic look-alikes,
fullwidth forms) must be de-obfuscated first, or Stage 1 screening can be
trivially bypassed. NFKC folds fullwidth/compatibility forms; an explicit
confusables map handles Greek/Cyrillic letters that NFKC leaves alone because
they are distinct scripts, not compatibility-equivalent.
"""
from __future__ import annotations

import re
import unicodedata

# U+200B..U+200D (zero-width space/non-joiner/joiner), U+2060 (word joiner),
# U+FEFF (zero-width no-break space / BOM).
_ZERO_WIDTH = re.compile("[​-‍⁠﻿]")
_SEPARATORS = re.compile(r"[,\n\r\t]+")
_WHITESPACE = re.compile(r"\s+")

# Greek/Cyrillic letters that visually mimic Latin and survive NFKC. Mapped to
# their Latin look-alike so "PΟ Box" (Greek Omicron) screens as "PO BOX".
_CONFUSABLES: dict[int, str] = {
    # Cyrillic uppercase
    0x0410: "A", 0x0412: "B", 0x0421: "C", 0x0415: "E", 0x041D: "H",
    0x041A: "K", 0x041C: "M", 0x041E: "O", 0x0420: "P", 0x0422: "T",
    0x0423: "Y", 0x0425: "X", 0x0406: "I", 0x0408: "J", 0x0405: "S",
    # Cyrillic lowercase
    0x0430: "a", 0x0435: "e", 0x043E: "o", 0x0440: "p", 0x0441: "c",
    0x0445: "x", 0x0443: "y", 0x0455: "s", 0x0456: "i", 0x0458: "j",
    0x043C: "m", 0x043A: "k",
    # Greek uppercase
    0x0391: "A", 0x0392: "B", 0x0395: "E", 0x0396: "Z", 0x0397: "H",
    0x0399: "I", 0x039A: "K", 0x039C: "M", 0x039D: "N", 0x039F: "O",
    0x03A1: "P", 0x03A4: "T", 0x03A5: "Y", 0x03A7: "X",
    # Greek lowercase
    0x03BF: "o", 0x03C1: "p", 0x03C7: "x", 0x03BA: "k", 0x03B9: "i",
}


def _base(s: str) -> str:
    s = unicodedata.normalize("NFKC", s or "")
    s = _ZERO_WIDTH.sub("", s)
    return s.translate(_CONFUSABLES)


def normalize_for_provider(s: str) -> str:
    """NFKC + de-obfuscate, then collapse whitespace. Preserves case and '#'
    so the value can be handed to the address-validation provider intact."""
    s = _base(s)
    s = _SEPARATORS.sub(" ", s)
    return _WHITESPACE.sub(" ", s).strip()


def normalize_for_match(s: str) -> str:
    """Aggressive form for regex screening: provider form, uppercased."""
    return normalize_for_provider(s).upper()
