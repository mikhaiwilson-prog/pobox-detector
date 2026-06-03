"""Public API tests."""
from unittest.mock import patch

import pytest

from pobox_detector import Config, Result, check_po_box
from pobox_detector.smarty_stage import SmartyResult


def test_regex_high_confidence_po_box():
    out = check_po_box("PO Box 99", config=Config())
    assert out == Result(is_po_box=True, confidence="high", method="regex", reason="matched:'PO Box'")


def test_regex_high_confidence_street():
    out = check_po_box("123 Main St", config=Config())
    assert out.is_po_box is False
    assert out.confidence == "high"
    assert out.method == "regex"


def test_uncertain_no_creds_degrades():
    out = check_po_box("Ste 400", config=Config())
    assert out.confidence == "low"
    assert out.method == "regex"
    assert "smarty_unavailable" in out.reason


def test_uncertain_dry_run():
    out = check_po_box("Unit B", config=Config(smarty_auth_id="x", smarty_auth_token="y", dry_run=True))
    assert out.confidence == "low"
    assert out.method == "regex"
    assert "dry_run" in out.reason


def test_uncertain_calls_smarty():
    cfg = Config(smarty_auth_id="x", smarty_auth_token="y")
    fake = SmartyResult(ok=True, is_po_box=True, reason="smarty:record_type=P")
    with patch("pobox_detector.core.SmartyStage") as Stage:
        Stage.return_value.lookup.return_value = fake
        out = check_po_box("ambiguous fragment xyz", config=cfg)
    assert out == Result(is_po_box=True, confidence="high", method="smarty", reason="smarty:record_type=P")


def test_smarty_failure_degrades():
    cfg = Config(smarty_auth_id="x", smarty_auth_token="y")
    fake = SmartyResult(ok=False, is_po_box=False, reason="http_500")
    with patch("pobox_detector.core.SmartyStage") as Stage:
        Stage.return_value.lookup.return_value = fake
        out = check_po_box("ambiguous fragment xyz", config=cfg)
    assert out.method == "regex"
    assert out.confidence == "low"
    assert out.is_po_box is False
    assert "smarty_failed:http_500" in out.reason


def test_config_from_env(monkeypatch):
    monkeypatch.setenv("SMARTY_AUTH_ID", "abc")
    monkeypatch.setenv("SMARTY_AUTH_TOKEN", "def")
    monkeypatch.setenv("POBOX_DRY_RUN", "1")
    cfg = Config.from_env()
    assert cfg.smarty_auth_id == "abc"
    assert cfg.smarty_auth_token == "def"
    assert cfg.dry_run is True
    assert cfg.smarty_available is False  # dry_run wins


def test_check_po_box_reads_env_when_no_config(monkeypatch):
    monkeypatch.delenv("SMARTY_AUTH_ID", raising=False)
    monkeypatch.delenv("SMARTY_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("POBOX_DRY_RUN", raising=False)
    out = check_po_box("Ste 400")
    assert "smarty_unavailable" in out.reason


def test_result_is_frozen():
    r = Result(is_po_box=False, confidence="high", method="regex", reason="x")
    with pytest.raises(Exception):
        r.is_po_box = True  # type: ignore[misc]
