"""Stage 2: Smarty US Street Address API. Stdlib only.

Returns the RAW candidate list (up to `candidates`), not a verdict — the
fail-closed verdict is computed in decision.py. `ok=False` means the provider
could not be trusted (timeout, quota, SSL, bad JSON); callers must treat that as
REVIEW, never as "not a PO Box".

Uses the system trust store (`ssl.create_default_context()`). Deployments on
macOS Python without a CA bundle should run `Install Certificates.command` or
set SSL_CERT_FILE.
"""
from __future__ import annotations

import json
import ssl
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field

from .config import Config
from .models import AddressInput
from .normalize import normalize_for_provider

URL = "https://us-street.api.smarty.com/street-address"
TIMEOUT_S = 10
_SSL_CONTEXT = ssl.create_default_context()


@dataclass
class SmartyResponse:
    ok: bool                            # True only if the response is trustworthy
    candidates: list[dict] = field(default_factory=list)
    reason: str = ""


class SmartyStage:
    def __init__(self, cfg: Config) -> None:
        self._cfg = cfg

    def lookup(self, addr: AddressInput) -> SmartyResponse:
        params = {
            "auth-id": self._cfg.smarty_auth_id or "",
            "auth-token": self._cfg.smarty_auth_token or "",
            "candidates": str(self._cfg.candidates),
            **self._build_query(addr),
        }
        url = f"{URL}?{urllib.parse.urlencode(params)}"
        try:
            with urllib.request.urlopen(url, timeout=TIMEOUT_S, context=_SSL_CONTEXT) as resp:
                body = resp.read()
                status = resp.status
        except urllib.error.HTTPError as e:
            reason = "quota_exhausted" if e.code in (402, 429) else f"http_{e.code}"
            return SmartyResponse(False, [], reason)
        except urllib.error.URLError as e:
            return SmartyResponse(False, [], f"http_error:URLError:{e.reason!s}")
        except Exception as e:
            return SmartyResponse(False, [], f"http_error:{e.__class__.__name__}")

        if status != 200:
            return SmartyResponse(False, [], f"http_{status}")
        try:
            data = json.loads(body)
        except (ValueError, json.JSONDecodeError):
            return SmartyResponse(False, [], "invalid_json")
        if not isinstance(data, list):
            return SmartyResponse(False, [], "invalid_json")
        if not data:
            # Valid response, zero matches: the address did not verify -> review.
            return SmartyResponse(True, [], "no_candidates")
        return SmartyResponse(True, data, f"candidates={len(data)}")

    @staticmethod
    def _build_query(addr: AddressInput) -> dict[str, str]:
        if addr.is_freeform:
            # Hand Smarty the whole string as freeform `street`; do NOT
            # comma-parse (only the first 50 chars of street are considered).
            return {"street": normalize_for_provider(addr.freeform)}
        q: dict[str, str] = {}
        if addr.line1:
            q["street"] = normalize_for_provider(addr.line1)
        if addr.line2:
            q["secondary"] = normalize_for_provider(addr.line2)
        if addr.city:
            q["city"] = normalize_for_provider(addr.city)
        if addr.state:
            q["state"] = normalize_for_provider(addr.state)
        if addr.postal_code:
            q["zipcode"] = normalize_for_provider(addr.postal_code)
        return q
