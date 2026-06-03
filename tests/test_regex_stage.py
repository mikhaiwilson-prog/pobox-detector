import pytest
from pobox_detector.regex_stage import classify


@pytest.mark.parametrize("addr", [
    "PO Box 123",
    "P.O. Box 4567",
    "Post Office Box 8",
    "po box 99",
    "PMB 42, 100 Main St",
    "PO #501",
    "PO Drawer 500",
    "Lock Box 123",
])
def test_obvious_po_box(addr):
    result, reason = classify(addr)
    assert result == "po_box", reason


@pytest.mark.parametrize("addr", [
    "123 Main St",
    "4567 Oak Avenue, Apt 2",
    "99 Industrial Blvd",
    "1 Infinite Loop",
    "742 Evergreen Terrace",
])
def test_obvious_street(addr):
    result, reason = classify(addr)
    assert result == "not_po_box", reason


@pytest.mark.parametrize("addr", [
    "Ste 400",
    "Unit B",
    "#42",
    "",
    "   ",
    "Bâtiment 7",
    "Floor 3",
])
def test_uncertain(addr):
    result, _ = classify(addr)
    assert result == "uncertain"
