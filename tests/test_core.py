"""End-to-end gate behavior, the review's regression set, and the bool shim."""
from unittest.mock import patch

import pytest

from pobox_detector import (
    AddressDecision,
    AddressInput,
    Config,
    Result,
    check_po_box,
    evaluate_address,
)
from pobox_detector.smarty_stage import SmartyResponse

NO_CREDS = Config()  # no Smarty credentials -> provider unavailable


def cand(record_type="S", dpv_cmra="N", dpv_match_code="Y", **extra):
    meta = {"record_type": record_type, "zip_type": "Standard", "carrier_route": "C001"}
    analysis = {"dpv_cmra": dpv_cmra, "dpv_match_code": dpv_match_code,
                "dpv_footnotes": "AABB", "dpv_vacant": "N", "dpv_no_stat": "N"}
    analysis.update(extra)
    return {"metadata": meta, "analysis": analysis, "components": {}}


# -- The single most important property: nothing in the review's disguise list
#    auto-allows when there is no authoritative provider clearance. --
REGRESSION = [
    "PO Box 123", "P.O. Box 123", "POB 123", "P.O.B. 123", "P O B 123",
    "Post Box 123", "P.O. Drawer 123", "Private Mailbox 456", "Private Mail Box 456",
    "PMB 456", "P M B 456",
    "123 Main St #456", "123 Main St Unit 456", "123 Main St Suite 456",
    "500 Main Street #59", "500 Main Street Unit 59",
    "555 S B B King Blvd Unit 1 Memphis TN 38103",
    "3214 N University Ave #409 Provo UT",
    "General Delivery Provo UT 84601",
    "P‍O Box 123",            # zero-width joiner
    "PΟ Box 123",            # Greek Omicron
    "ＰＯ Box 123",            # fullwidth
    "123 Main St ＃456",      # fullwidth hash
]


@pytest.mark.parametrize("addr", REGRESSION)
def test_no_disguise_auto_allows(addr):
    assert evaluate_address(addr, NO_CREDS).decision is not AddressDecision.ALLOW_PHYSICAL


@pytest.mark.parametrize("addr", [
    "PO Box 123", "P.O.B. 123", "P M B 456", "Private Mailbox 456",
    "P‍O Box 123", "PΟ Box 123", "ＰＯ Box 123",
])
def test_obvious_and_obfuscated_po_block_on_regex(addr):
    d = evaluate_address(addr, NO_CREDS)
    assert d.decision is AddressDecision.BLOCK_PO_CMRA
    assert d.evidence.get("stage") == "regex"


def test_regex_block_does_not_call_provider():
    cfg = Config(smarty_auth_id="x", smarty_auth_token="y")
    with patch("pobox_detector.core.SmartyStage") as Stage:
        d = evaluate_address("PO Box 5", cfg)
    assert d.decision is AddressDecision.BLOCK_PO_CMRA
    Stage.return_value.lookup.assert_not_called()


def test_plain_street_without_provider_is_review_not_allow():
    # The original sin: a street suffix used to auto-clear. Now it must not.
    assert evaluate_address("123 Main St", NO_CREDS).decision is AddressDecision.REVIEW_UNVERIFIED


def test_dry_run_does_not_allow():
    cfg = Config(smarty_auth_id="x", smarty_auth_token="y", dry_run=True)
    assert evaluate_address("123 Main St", cfg).decision is AddressDecision.REVIEW_UNVERIFIED


# -- provider-backed outcomes --
def _patch_smarty(resp):
    p = patch("pobox_detector.core.SmartyStage")
    Stage = p.start()
    Stage.return_value.lookup.return_value = resp
    return p


def test_clean_candidate_allows():
    p = _patch_smarty(SmartyResponse(True, [cand()], "candidates=1"))
    try:
        cfg = Config(smarty_auth_id="x", smarty_auth_token="y")
        d = evaluate_address("123 Main St, Reno, NV 89501", cfg)
    finally:
        p.stop()
    assert d.decision is AddressDecision.ALLOW_PHYSICAL


def test_po_candidate_blocks():
    p = _patch_smarty(SmartyResponse(True, [cand(record_type="P")], "candidates=1"))
    try:
        cfg = Config(smarty_auth_id="x", smarty_auth_token="y")
        d = evaluate_address("500 Main Street #59", cfg)
    finally:
        p.stop()
    assert d.decision is AddressDecision.BLOCK_PO_CMRA


def test_provider_failure_is_review_unverified():
    p = _patch_smarty(SmartyResponse(False, [], "http_500"))
    try:
        cfg = Config(smarty_auth_id="x", smarty_auth_token="y")
        d = evaluate_address("123 Main St", cfg)
    finally:
        p.stop()
    assert d.decision is AddressDecision.REVIEW_UNVERIFIED
    assert "http_500" in d.reason


def test_provider_no_match_is_review_unverified():
    p = _patch_smarty(SmartyResponse(True, [], "no_candidates"))
    try:
        cfg = Config(smarty_auth_id="x", smarty_auth_token="y")
        d = evaluate_address("nowhere real", cfg)
    finally:
        p.stop()
    assert d.decision is AddressDecision.REVIEW_UNVERIFIED


def test_soft_regex_plus_clean_provider_is_ambiguous():
    # "Box 12" is a soft regex hit; even a clean provider allow becomes review.
    p = _patch_smarty(SmartyResponse(True, [cand()], "candidates=1"))
    try:
        cfg = Config(smarty_auth_id="x", smarty_auth_token="y")
        d = evaluate_address("Box 12", cfg)
    finally:
        p.stop()
    assert d.decision is AddressDecision.REVIEW_AMBIGUOUS


def test_structured_input_flows_to_provider():
    p = _patch_smarty(SmartyResponse(True, [cand(dpv_cmra="Y")], "candidates=1"))
    try:
        cfg = Config(smarty_auth_id="x", smarty_auth_token="y")
        d = evaluate_address(
            AddressInput(line1="3214 N University Ave", line2="#409", city="Provo", state="UT"),
            cfg,
        )
    finally:
        p.stop()
    assert d.decision is AddressDecision.BLOCK_PO_CMRA


# -- backward-compatible boolean shim --
def test_shim_block_is_po_box_true_high():
    r = check_po_box("PO Box 5", NO_CREDS)
    assert isinstance(r, Result)
    assert r.is_po_box is True and r.confidence == "high"
    assert r.decision is AddressDecision.BLOCK_PO_CMRA


def test_shim_review_is_low_confidence_not_cleared():
    r = check_po_box("123 Main St", NO_CREDS)
    # is_po_box False but confidence low + decision REVIEW => NOT a clearance.
    assert r.is_po_box is False and r.confidence == "low"
    assert r.decision is AddressDecision.REVIEW_UNVERIFIED


def test_shim_allow_is_high_confidence():
    p = _patch_smarty(SmartyResponse(True, [cand()], "candidates=1"))
    try:
        cfg = Config(smarty_auth_id="x", smarty_auth_token="y")
        r = check_po_box("123 Main St, Reno, NV 89501", cfg)
    finally:
        p.stop()
    assert r.is_po_box is False and r.confidence == "high"
    assert r.decision is AddressDecision.ALLOW_PHYSICAL
    assert r.method == "smarty"


# -- config / env --
def test_config_from_env(monkeypatch):
    monkeypatch.setenv("SMARTY_AUTH_ID", "abc")
    monkeypatch.setenv("SMARTY_AUTH_TOKEN", "def")
    monkeypatch.setenv("POBOX_DRY_RUN", "1")
    cfg = Config.from_env()
    assert cfg.smarty_auth_id == "abc" and cfg.smarty_auth_token == "def"
    assert cfg.dry_run is True and cfg.smarty_available is False


def test_evaluate_reads_env_when_no_config(monkeypatch):
    monkeypatch.delenv("SMARTY_AUTH_ID", raising=False)
    monkeypatch.delenv("SMARTY_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("POBOX_DRY_RUN", raising=False)
    d = evaluate_address("123 Main St")
    assert d.decision is AddressDecision.REVIEW_UNVERIFIED
    assert "smarty_unavailable" in d.reason
