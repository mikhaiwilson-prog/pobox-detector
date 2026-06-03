"""Stage 1 is positive-only: it may BLOCK or REVIEW, but NEVER clears."""
import pytest

from pobox_detector.regex_stage import screen


@pytest.mark.parametrize("addr", [
    "PO Box 123",
    "P.O. Box 4567",
    "Post Office Box 8",
    "po box 99",
    "POB 123",
    "P.O.B. 123",
    "P O B 123",
    "Post Box 123",
    "Postal Box 7",
    "P.O. Drawer 123",
    "Postal Drawer 9",
    "PMB 456",
    "P M B 456",
    "Private Mailbox 456",
    "Private Mail Box 456",
    "CMRA",
    "Commercial Mail Receiving Agency",
    "Lock Box 123",
    "PO #501",
])
def test_block_tokens(addr):
    signal, reason = screen(addr)
    assert signal == "block", reason


@pytest.mark.parametrize("addr", [
    "General Delivery Provo UT 84601",
    "Private Box 12",
    "Drawer 500",
    "Mailbox 12",
    "Box 42",
])
def test_review_tokens(addr):
    signal, reason = screen(addr)
    assert signal == "review", reason


@pytest.mark.parametrize("addr", [
    "123 Main St",
    "742 Evergreen Terrace",
    "3214 N University Ave #409 Provo UT",
    "500 Main Street #59",
    "500 Main Street Unit 59",
    "123 Main St Suite 456",
    "555 S B B King Blvd Unit 1 Memphis TN 38103",
])
def test_no_indicator_never_blocks(addr):
    # A street suffix / unit number is NOT a PO indicator and NOT a clearance.
    signal, _ = screen(addr)
    assert signal == "none"


def test_screen_has_no_allow_signal():
    # The only signals are block/review/none; "none" still requires provider
    # verification to allow — regex can never clear an address.
    signals = {screen(a)[0] for a in ["123 Main St", "PO Box 1", "Box 5"]}
    assert signals <= {"block", "review", "none"}
