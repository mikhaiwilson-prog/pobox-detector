"""Smarty stage tests. Mocks urllib.request.urlopen directly."""
from __future__ import annotations
import io
import json
import urllib.error
from unittest.mock import MagicMock, patch

import pytest

from pobox_detector.config import Config
from pobox_detector.smarty_stage import SmartyStage


@pytest.fixture
def cfg():
    return Config(smarty_auth_id="id", smarty_auth_token="tok", dry_run=False)


def _fake_response(payload, status=200):
    cm = MagicMock()
    body = payload if isinstance(payload, (bytes, bytearray)) else json.dumps(payload).encode()
    cm.read.return_value = body
    cm.status = status
    cm.__enter__.return_value = cm
    cm.__exit__.return_value = False
    return cm


@patch("pobox_detector.smarty_stage.urllib.request.urlopen")
def test_record_type_p_is_po_box(mock_urlopen, cfg):
    mock_urlopen.return_value = _fake_response(
        [{"metadata": {"record_type": "P"}, "analysis": {"dpv_cmra": "N"}}]
    )
    r = SmartyStage(cfg).lookup("PO Box 5, Reno NV")
    assert r.ok is True and r.is_po_box is True
    assert "record_type=P" in r.reason


@patch("pobox_detector.smarty_stage.urllib.request.urlopen")
def test_record_type_s_is_not_po_box(mock_urlopen, cfg):
    mock_urlopen.return_value = _fake_response(
        [{"metadata": {"record_type": "S"}, "analysis": {"dpv_cmra": "N"}}]
    )
    r = SmartyStage(cfg).lookup("123 Main St")
    assert r.ok is True and r.is_po_box is False


@patch("pobox_detector.smarty_stage.urllib.request.urlopen")
def test_cmra_folded_into_po_box(mock_urlopen, cfg):
    mock_urlopen.return_value = _fake_response(
        [{"metadata": {"record_type": "S"}, "analysis": {"dpv_cmra": "Y"}}]
    )
    r = SmartyStage(cfg).lookup("123 Main St")
    assert r.ok is True and r.is_po_box is True
    assert "cmra" in r.reason.lower()


@patch("pobox_detector.smarty_stage.urllib.request.urlopen")
def test_empty_array_is_no_match(mock_urlopen, cfg):
    mock_urlopen.return_value = _fake_response([])
    r = SmartyStage(cfg).lookup("garbled")
    assert r.ok is False
    assert r.reason == "no_match"


@patch("pobox_detector.smarty_stage.urllib.request.urlopen")
def test_quota_exhausted(mock_urlopen, cfg):
    mock_urlopen.side_effect = urllib.error.HTTPError(
        "https://us-street.api.smarty.com/street-address", 402, "Payment Required", {}, io.BytesIO(b"")
    )
    r = SmartyStage(cfg).lookup("123 Main St")
    assert r.ok is False
    assert r.reason == "quota_exhausted"


@patch("pobox_detector.smarty_stage.urllib.request.urlopen")
def test_invalid_json_does_not_raise(mock_urlopen, cfg):
    mock_urlopen.return_value = _fake_response(b"not json")
    r = SmartyStage(cfg).lookup("123 Main St")
    assert r.ok is False
    assert r.reason == "invalid_json"


@patch("pobox_detector.smarty_stage.urllib.request.urlopen")
def test_no_comma_address_sends_street_only(mock_urlopen, cfg):
    mock_urlopen.return_value = _fake_response(
        [{"metadata": {"record_type": "S"}, "analysis": {"dpv_cmra": "N"}}]
    )
    SmartyStage(cfg).lookup("123 Main St Reno NV 89501")
    url = mock_urlopen.call_args[0][0]
    assert "street=" in url and "city=" not in url


@patch("pobox_detector.smarty_stage.urllib.request.urlopen")
def test_missing_metadata_keys(mock_urlopen, cfg):
    mock_urlopen.return_value = _fake_response([{}])
    r = SmartyStage(cfg).lookup("anything")
    assert r.ok is True and r.is_po_box is False


@patch("pobox_detector.smarty_stage.urllib.request.urlopen")
def test_http_500_degrades(mock_urlopen, cfg):
    mock_urlopen.side_effect = urllib.error.HTTPError(
        "https://us-street.api.smarty.com/street-address", 500, "Internal Server Error", {}, io.BytesIO(b"")
    )
    r = SmartyStage(cfg).lookup("123 Main St")
    assert r.ok is False
    assert r.reason == "http_500"


@patch("pobox_detector.smarty_stage.urllib.request.urlopen")
def test_auth_params_attached(mock_urlopen, cfg):
    mock_urlopen.return_value = _fake_response(
        [{"metadata": {"record_type": "S"}, "analysis": {"dpv_cmra": "N"}}]
    )
    SmartyStage(cfg).lookup("123 Main St, Reno, NV 89501")
    url = mock_urlopen.call_args[0][0]
    assert "auth-id=id" in url
    assert "auth-token=tok" in url
    assert "street=" in url
