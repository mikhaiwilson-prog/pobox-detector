"""Decision engine: full PO/CMRA/PBSA indicator set, fail-closed."""
import pytest

from pobox_detector.decision import AddressDecision as AD
from pobox_detector.decision import evaluate_smarty_candidates


def cand(record_type="S", dpv_cmra="N", dpv_match_code="Y", dpv_footnotes="AABB",
         dpv_vacant="N", dpv_no_stat="N", zip_type="Standard", carrier_route="C001",
         pmb_designator="", pmb_number="", ews_match=False,
         delivery_line_1="123 Main St", last_line="Reno NV 89501",
         barcode="895010123459"):
    return {
        "delivery_line_1": delivery_line_1,
        "last_line": last_line,
        "delivery_point_barcode": barcode,
        "metadata": {"record_type": record_type, "zip_type": zip_type,
                     "carrier_route": carrier_route},
        "analysis": {"dpv_cmra": dpv_cmra, "dpv_match_code": dpv_match_code,
                     "dpv_footnotes": dpv_footnotes, "dpv_vacant": dpv_vacant,
                     "dpv_no_stat": dpv_no_stat, "ews_match": ews_match},
        "components": {"pmb_designator": pmb_designator, "pmb_number": pmb_number},
    }


def d(candidates, **kw):
    return evaluate_smarty_candidates(candidates, **kw).decision


# --- hard blocks ---
@pytest.mark.parametrize("c", [
    cand(record_type="P"),
    cand(dpv_cmra="Y"),
    cand(dpv_footnotes="AAPB"),          # PO Box street-style
    cand(dpv_footnotes="RRAA"),          # confirmed PMB info
    cand(carrier_route="C771"),          # C770-C779 PBSA
    cand(carrier_route="C779"),
    cand(zip_type="POBox"),
    cand(pmb_number="409"),
    cand(pmb_designator="#"),
])
def test_hard_block_indicators(c):
    assert d([c]) is AD.BLOCK_PO_CMRA


# --- clean allow ---
def test_clean_physical_allows():
    assert d([cand()]) is AD.ALLOW_PHYSICAL


def test_consistent_multiple_clean_allows():
    # Two clean candidates that collapse to the same canonical delivery point.
    assert d([cand(), cand()]) is AD.ALLOW_PHYSICAL


# --- review (insufficient evidence) ---
@pytest.mark.parametrize("c", [
    cand(record_type=""),                # no DPV match
    cand(record_type="G"),               # general delivery
    cand(record_type="R"),               # rural route (not in default allow set)
    cand(dpv_cmra=""),                   # CMRA not evaluated
    cand(dpv_match_code="S"),            # secondary dropped
    cand(dpv_match_code="D"),            # missing secondary
    cand(dpv_match_code="N"),
    cand(dpv_vacant="Y"),
    cand(dpv_no_stat="Y"),
    cand(ews_match=True),                # street not yet ready for delivery
    cand(dpv_footnotes="AAR1"),          # CMRA w/o PMB
    cand(dpv_footnotes="AAP1"),          # box number missing
])
def test_review_unverified_indicators(c):
    assert d([c]) is AD.REVIEW_UNVERIFIED


def test_empty_candidate_list_is_review():
    assert d([]) is AD.REVIEW_UNVERIFIED


# --- ambiguity vs hard-block precedence across candidates ---
def test_mixed_review_candidates_is_ambiguous():
    assert d([cand(), cand(dpv_match_code="S")]) is AD.REVIEW_AMBIGUOUS


def test_any_po_candidate_blocks_even_with_a_clean_one():
    assert d([cand(), cand(record_type="P")]) is AD.BLOCK_PO_CMRA


def test_multiple_distinct_clean_candidates_is_ambiguous():
    # Two clean but DIFFERENT physical addresses — we don't know which was meant.
    a = cand(delivery_line_1="123 Main St", barcode="895010123459")
    b = cand(delivery_line_1="123 Main Ave", barcode="895010999999")
    assert d([a, b]) is AD.REVIEW_AMBIGUOUS


def test_multiple_clean_missing_canonical_is_ambiguous():
    # Clean flags but no canonical identity to prove equivalence -> review.
    a = cand(delivery_line_1="", last_line="")
    b = cand(delivery_line_1="", last_line="")
    assert d([a, b]) is AD.REVIEW_AMBIGUOUS


# --- policy knobs ---
def test_allowed_record_types_can_be_widened():
    from pobox_detector.decision import DEFAULT_ALLOWED_RECORD_TYPES
    widened = DEFAULT_ALLOWED_RECORD_TYPES | {"R"}
    assert d([cand(record_type="R")], allowed_record_types=widened) is AD.ALLOW_PHYSICAL


def test_dpv_match_requirement_can_be_relaxed():
    assert d([cand(dpv_match_code="S")], require_dpv_match_y=False) is AD.ALLOW_PHYSICAL
