"""Normalization must de-obfuscate before screening, or Stage 1 is bypassable.

Obfuscation inputs are built from explicit codepoints via chr() so no literal
invisible or look-alike characters appear in this source.
"""
import pytest

from pobox_detector.normalize import normalize_for_match, normalize_for_provider

ZWSP, ZWNJ, ZWJ, WJ, BOM = (chr(c) for c in (0x200B, 0x200C, 0x200D, 0x2060, 0xFEFF))
GREEK_O = chr(0x039F)          # Greek capital Omicron
CYR_ER, CYR_O = chr(0x0420), chr(0x041E)   # Cyrillic ER, O
FW_P, FW_O, FW_HASH = chr(0xFF30), chr(0xFF2F), chr(0xFF03)   # fullwidth P, O, #


@pytest.mark.parametrize("raw,expected", [
    ("P" + ZWJ + "O Box 123", "PO BOX 123"),
    ("P" + ZWSP + "O Box 123", "PO BOX 123"),
    ("P" + WJ + "O Box 123", "PO BOX 123"),
    ("P" + BOM + "O Box 123", "PO BOX 123"),
    ("P" + GREEK_O + "Box 123", "POBOX 123"),
    (CYR_ER + CYR_O + " Box 123", "PO BOX 123"),
    (FW_P + FW_O + " Box 123", "PO BOX 123"),
    (chr(0xFF11) + chr(0xFF12) + chr(0xFF13) + " Main St", "123 MAIN ST"),   # fullwidth digits
    ("123 Main St " + FW_HASH + "456", "123 MAIN ST #456"),
])
def test_de_obfuscation(raw, expected):
    assert normalize_for_match(raw) == expected


def test_provider_form_preserves_case_and_hash():
    assert normalize_for_provider("123 Main St #409, Provo UT") == "123 Main St #409 Provo UT"


def test_collapses_whitespace_and_separators():
    assert normalize_for_provider("  PO\tBox\n5 ,  Reno ") == "PO Box 5 Reno"


def test_empty_is_safe():
    assert normalize_for_match("") == ""
    assert normalize_for_provider(None) == ""
