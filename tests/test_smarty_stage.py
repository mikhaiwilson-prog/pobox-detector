"""Smarty stage: query construction + fail-closed provider states.

The stage returns raw candidates; `ok=False` must never read as 'not a PO Box'.
"""
from __future__ import annotations

import io
import json
import urllib.error
from unittest.mock import MagicMock, patch

import pytest

from pobox_detector.config import Config
from pobox_detector.models import AddressInput
from pobox_detector.smarty_stage import SmartyStage


@pytest.fixture
def cfg():
    return Config(smarty_auth_id="id", smarty_auth_token="tok")


def _resp(payload, status=200):
    cm = MagicMock()
    body = payload if isinstance(payload, (bytes, bytearray)) else json.dumps(payload).encode()
    cm.read.return_value = body
    cm.status = status
    cm.__enter__.return_value = cm
    cm.__exit__.return_value = False
    return cm


def _free(s):
    return AddressInput.from_freeform(s)


# --- query construction ---
@patch("pobox_detector.smarty_stage.urllib.request.urlopen")
def test_requests_ten_candidates(mock, cfg):
    mock.return_value = _resp([{"metadata": {"record_type": "S"}}])
    SmartyStage(cfg).lookup(_free("123 Main St Reno NV 89501"))
    assert "candidates=10" in mock.call_args[0][0]


@patch("pobox_detector.smarty_stage.urllib.request.urlopen")
def test_freeform_sends_street_only_no_comma_parse(mock, cfg):
    mock.return_value = _resp([{"metadata": {"record_type": "S"}}])
    SmartyStage(cfg).lookup(_free("123 Main St, Apt 4, New York, NY 10001"))
    url = mock.call_args[0][0]
    assert "street=" in url and "city=" not in url and "state=" not in url


@patch("pobox_detector.smarty_stage.urllib.request.urlopen")
def test_structured_fields_map_to_smarty_inputs(mock, cfg):
    mock.return_value = _resp([{"metadata": {"record_type": "S"}}])
    SmartyStage(cfg).lookup(AddressInput(
        line1="3214 N University Ave", line2="#409", city="Provo", state="UT", postal_code="84604"
    ))
    url = mock.call_args[0][0]
    assert "street=3214" in url
    assert "secondary=%23409" in url      # '#' is URL-encoded, secondary preserved
    assert "city=Provo" in url and "state=UT" in url and "zipcode=84604" in url


@patch("pobox_detector.smarty_stage.urllib.request.urlopen")
def test_auth_params_attached(mock, cfg):
    mock.return_value = _resp([{"metadata": {"record_type": "S"}}])
    SmartyStage(cfg).lookup(_free("123 Main St, Reno, NV 89501"))
    url = mock.call_args[0][0]
    assert "auth-id=id" in url and "auth-token=tok" in url


# --- response handling ---
@patch("pobox_detector.smarty_stage.urllib.request.urlopen")
def test_multiple_candidates_returned_raw(mock, cfg):
    mock.return_value = _resp([{"metadata": {"record_type": "S"}},
                               {"metadata": {"record_type": "P"}}])
    r = SmartyStage(cfg).lookup(_free("ambiguous"))
    assert r.ok is True and len(r.candidates) == 2


@patch("pobox_detector.smarty_stage.urllib.request.urlopen")
def test_no_candidates_is_ok_but_empty(mock, cfg):
    mock.return_value = _resp([])
    r = SmartyStage(cfg).lookup(_free("garbled"))
    assert r.ok is True and r.candidates == [] and r.reason == "no_candidates"


# --- fail-closed provider states ---
@pytest.mark.parametrize("code,reason", [
    (402, "quota_exhausted"),
    (429, "quota_exhausted"),
    (401, "http_401"),
    (500, "http_500"),
])
@patch("pobox_detector.smarty_stage.urllib.request.urlopen")
def test_http_errors_fail_closed(mock, cfg, code, reason):
    mock.side_effect = urllib.error.HTTPError("u", code, "x", {}, io.BytesIO(b""))
    r = SmartyStage(cfg).lookup(_free("123 Main St"))
    assert r.ok is False and r.reason == reason


@patch("pobox_detector.smarty_stage.urllib.request.urlopen")
def test_timeout_fails_closed(mock, cfg):
    mock.side_effect = urllib.error.URLError("timed out")
    r = SmartyStage(cfg).lookup(_free("123 Main St"))
    assert r.ok is False and "URLError" in r.reason


@patch("pobox_detector.smarty_stage.urllib.request.urlopen")
def test_invalid_json_fails_closed(mock, cfg):
    mock.return_value = _resp(b"not json")
    r = SmartyStage(cfg).lookup(_free("123 Main St"))
    assert r.ok is False and r.reason == "invalid_json"


@patch("pobox_detector.smarty_stage.urllib.request.urlopen")
def test_non_list_json_fails_closed(mock, cfg):
    mock.return_value = _resp({"error": "nope"})
    r = SmartyStage(cfg).lookup(_free("123 Main St"))
    assert r.ok is False and r.reason == "invalid_json"
