"""Normalization must de-obfuscate before screening, or Stage 1 is bypassable."""
import pytest

from pobox_detector.normalize import normalize_for_match, normalize_for_provider


@pytest.mark.parametrize("raw,expected", [
    ("P‍O Box 123", "PO BOX 123"),       # zero-width joiner
    ("P​O Box 123", "PO BOX 123"),       # zero-width space
    ("PΟBox 123", "POBOX 123"),          # Greek capital Omicron
    ("РО Box 123", "PO BOX 123"),   # Cyrillic ER + O
    ("ＰＯ Box 123", "PO BOX 123"),   # fullwidth P O (NFKC)
    ("１２３ Main St", "123 MAIN ST"),  # fullwidth digits
    ("123 Main St ＃456", "123 MAIN ST #456"),  # fullwidth hash
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
