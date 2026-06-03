"""End-to-end gate behavior, the review's regression set, and the bool shim."""
from unittest.mock import patch

import pytest

from pobox_detector import (
    AddressDecision,
    AddressInput,
    Config,
    IndeterminateAddress,
    Result,
    check_po_box,
    evaluate_address,
)
from pobox_detector.smarty_stage import SmartyResponse

NO_CREDS = Config()                                  # provider unavailable
CREDS = Config(smarty_auth_id="x", smarty_auth_token="y")
STRUCTURED = AddressInput(line1="123 Main St", city="Reno", state="NV", postal_code="89501")

# Obfuscated inputs built from explicit codepoints (no invisible chars in source).
ZWJ, GREEK_O = chr(0x200D), chr(0x039F)
FW_P, FW_O, FW_HASH = chr(0xFF30), chr(0xFF2F), chr(0xFF03)
OBFUSCATED_PO = ["P" + ZWJ + "O Box 123", "P" + GREEK_O + " Box 123", FW_P + FW_O + " Box 123"]


def cand(record_type="S", dpv_cmra="N", dpv_match_code="Y", **extra):
    analysis = {"dpv_cmra": dpv_cmra, "dpv_match_code": dpv_match_code,
                "dpv_footnotes": "AABB", "dpv_vacant": "N", "dpv_no_stat": "N", "ews_match": False}
    analysis.update(extra)
    return {
        "delivery_line_1": "123 Main St", "last_line": "Reno NV 89501",
        "delivery_point_barcode": "895010123459",
        "metadata": {"record_type": record_type, "zip_type": "Standard", "carrier_route": "C001"},
        "analysis": analysis, "components": {},
    }


def _patch_smarty(resp):
    p = patch("pobox_detector.core.SmartyStage")
    p.start().return_value.lookup.return_value = resp
    return p


# --- The core property: nothing in the disguise list auto-allows without an
#     authoritative provider clearance. ---
REGRESSION = [
    "PO Box 123", "P.O. Box 123", "POB 123", "P.O.B. 123", "P O B 123",
    "Post Box 123", "P.O. Drawer 123", "Private Mailbox 456", "Private Mail Box 456",
    "PMB 456", "P M B 456",
    "123 Main St #456", "123 Main St Unit 456", "123 Main St Suite 456",
    "500 Main Street #59", "500 Main Street Unit 59",
    "555 S B B King Blvd Unit 1 Memphis TN 38103",
    "3214 N University Ave #409 Provo UT",
    "General Delivery Provo UT 84601",
    "123 Main St " + FW_HASH + "456",
] + OBFUSCATED_PO


@pytest.mark.parametrize("addr", REGRESSION)
def test_no_disguise_auto_allows(addr):
    assert evaluate_address(addr, NO_CREDS).decision is not AddressDecision.ALLOW_PHYSICAL


@pytest.mark.parametrize("addr", ["PO Box 123", "P.O.B. 123", "P M B 456",
                                  "Private Mailbox 456"] + OBFUSCATED_PO)
def test_obvious_and_obfuscated_po_block_on_regex(addr):
    d = evaluate_address(addr, NO_CREDS)
    assert d.decision is AddressDecision.BLOCK_PO_CMRA
    assert d.evidence.get("stage") == "regex"


def test_regex_block_does_not_call_provider():
    with patch("pobox_detector.core.SmartyStage") as Stage:
        d = evaluate_address("PO Box 5", CREDS)
    assert d.decision is AddressDecision.BLOCK_PO_CMRA
    Stage.return_value.lookup.assert_not_called()


def test_plain_street_without_provider_is_review_not_allow():
    assert evaluate_address("123 Main St", NO_CREDS).decision is AddressDecision.REVIEW_UNVERIFIED


def test_dry_run_does_not_allow():
    cfg = Config(smarty_auth_id="x", smarty_auth_token="y", dry_run=True)
    assert evaluate_address(STRUCTURED, cfg).decision is AddressDecision.REVIEW_UNVERIFIED


# --- provider-backed outcomes (structured input) ---
def test_clean_structured_candidate_allows():
    p = _patch_smarty(SmartyResponse(True, [cand()], "candidates=1"))
    try:
        assert evaluate_address(STRUCTURED, CREDS).decision is AddressDecision.ALLOW_PHYSICAL
    finally:
        p.stop()


def test_po_candidate_blocks():
    p = _patch_smarty(SmartyResponse(True, [cand(record_type="P")], "candidates=1"))
    try:
        assert evaluate_address(STRUCTURED, CREDS).decision is AddressDecision.BLOCK_PO_CMRA
    finally:
        p.stop()


def test_provider_failure_is_review_unverified():
    p = _patch_smarty(SmartyResponse(False, [], "http_500"))
    try:
        d = evaluate_address(STRUCTURED, CREDS)
    finally:
        p.stop()
    assert d.decision is AddressDecision.REVIEW_UNVERIFIED and "http_500" in d.reason


def test_provider_no_match_is_review_unverified():
    p = _patch_smarty(SmartyResponse(True, [], "no_candidates"))
    try:
        assert evaluate_address(STRUCTURED, CREDS).decision is AddressDecision.REVIEW_UNVERIFIED
    finally:
        p.stop()


def test_structured_cmra_blocks():
    p = _patch_smarty(SmartyResponse(True, [cand(dpv_cmra="Y")], "candidates=1"))
    try:
        d = evaluate_address(
            AddressInput(line1="3214 N University Ave", line2="#409", city="Provo", state="UT"),
            CREDS,
        )
    finally:
        p.stop()
    assert d.decision is AddressDecision.BLOCK_PO_CMRA


# --- freeform may block/review but never auto-allow ---
def test_freeform_clean_provider_does_not_allow():
    p = _patch_smarty(SmartyResponse(True, [cand()], "candidates=1"))
    try:
        d = evaluate_address("123 Main St Reno NV 89501", CREDS)   # freeform string
    finally:
        p.stop()
    assert d.decision is AddressDecision.REVIEW_UNVERIFIED and "freeform" in d.reason


def test_freeform_allow_permitted_when_policy_relaxed():
    cfg = Config(smarty_auth_id="x", smarty_auth_token="y", require_structured_for_allow=False)
    p = _patch_smarty(SmartyResponse(True, [cand()], "candidates=1"))
    try:
        d = evaluate_address("123 Main St Reno NV 89501", cfg)
    finally:
        p.stop()
    assert d.decision is AddressDecision.ALLOW_PHYSICAL


def test_freeform_po_still_blocks():
    assert evaluate_address("PO Box 9 Reno NV", NO_CREDS).decision is AddressDecision.BLOCK_PO_CMRA


def test_soft_regex_plus_clean_provider_is_ambiguous():
    # Soft regex hit on structured input + clean provider -> ambiguous (conflict).
    p = _patch_smarty(SmartyResponse(True, [cand()], "candidates=1"))
    try:
        d = evaluate_address(AddressInput(line1="Box 12", city="Reno", state="NV"), CREDS)
    finally:
        p.stop()
    assert d.decision is AddressDecision.REVIEW_AMBIGUOUS


# --- US-only country guard ---
def test_non_us_country_is_review_and_skips_provider():
    with patch("pobox_detector.core.SmartyStage") as Stage:
        d = evaluate_address(
            AddressInput(line1="123 King St", city="Toronto", state="ON", country="CA"), CREDS
        )
    assert d.decision is AddressDecision.REVIEW_UNVERIFIED and "unsupported_country" in d.reason
    Stage.return_value.lookup.assert_not_called()


def test_us_country_passes_guard():
    p = _patch_smarty(SmartyResponse(True, [cand()], "candidates=1"))
    try:
        d = evaluate_address(
            AddressInput(line1="123 Main St", city="Reno", state="NV", country="US"), CREDS
        )
    finally:
        p.stop()
    assert d.decision is AddressDecision.ALLOW_PHYSICAL


# --- backward-compatible boolean shim ---
def test_shim_block_is_po_box_true():
    r = check_po_box("PO Box 5", NO_CREDS)
    assert isinstance(r, Result) and r.is_po_box is True and r.confidence == "high"
    assert r.decision is AddressDecision.BLOCK_PO_CMRA


def test_shim_raises_on_review():
    with pytest.raises(IndeterminateAddress):
        check_po_box("123 Main St", NO_CREDS)


def test_shim_raise_carries_decision():
    with pytest.raises(IndeterminateAddress) as ei:
        check_po_box("123 Main St", NO_CREDS)
    assert ei.value.decision is AddressDecision.REVIEW_UNVERIFIED


def test_shim_allow_returns_result():
    p = _patch_smarty(SmartyResponse(True, [cand()], "candidates=1"))
    try:
        r = check_po_box(STRUCTURED, CREDS)
    finally:
        p.stop()
    assert r.is_po_box is False and r.confidence == "high"
    assert r.decision is AddressDecision.ALLOW_PHYSICAL and r.method == "smarty"


# --- config: candidates clamp + env ---
def test_candidates_clamped_to_smarty_range():
    assert Config(candidates=50).candidates == 10
    assert Config(candidates=0).candidates == 1


def test_config_from_env(monkeypatch):
    monkeypatch.setenv("SMARTY_AUTH_ID", "abc")
    monkeypatch.setenv("SMARTY_AUTH_TOKEN", "def")
    monkeypatch.setenv("POBOX_DRY_RUN", "1")
    cfg = Config.from_env()
    assert cfg.smarty_auth_id == "abc" and cfg.dry_run is True and cfg.smarty_available is False


def test_evaluate_reads_env_when_no_config(monkeypatch):
    monkeypatch.delenv("SMARTY_AUTH_ID", raising=False)
    monkeypatch.delenv("SMARTY_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("POBOX_DRY_RUN", raising=False)
    d = evaluate_address("123 Main St")
    assert d.decision is AddressDecision.REVIEW_UNVERIFIED and "smarty_unavailable" in d.reason
