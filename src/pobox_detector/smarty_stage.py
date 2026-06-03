"""Stage 2: Smarty US Street Address API fallback. Stdlib only.

Only invoked when the regex stage is uncertain. CMRA hits (UPS-Store-style
mailboxes) are folded into is_po_box=True per product decision.

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
from dataclasses import dataclass

from .config import Config

URL = "https://us-street.api.smarty.com/street-address"
TIMEOUT_S = 10
_SSL_CONTEXT = ssl.create_default_context()


@dataclass
class SmartyResult:
    ok: bool          # True only if Smarty returned a usable verdict
    is_po_box: bool   # meaningful when ok=True
    reason: str


class SmartyStage:
    def __init__(self, cfg: Config) -> None:
        self._cfg = cfg

    def lookup(self, address: str) -> SmartyResult:
        params = {
            "auth-id": self._cfg.smarty_auth_id or "",
            "auth-token": self._cfg.smarty_auth_token or "",
            **self._parse(address),
        }
        url = f"{URL}?{urllib.parse.urlencode(params)}"
        try:
            with urllib.request.urlopen(url, timeout=TIMEOUT_S, context=_SSL_CONTEXT) as resp:
                body = resp.read()
                status = resp.status
        except urllib.error.HTTPError as e:
            if e.code == 402:
                return SmartyResult(False, False, "quota_exhausted")
            return SmartyResult(False, False, f"http_{e.code}")
        except urllib.error.URLError as e:
            return SmartyResult(False, False, f"http_error:URLError:{e.reason!s}")
        except Exception as e:
            return SmartyResult(False, False, f"http_error:{e.__class__.__name__}")

        if status != 200:
            return SmartyResult(False, False, f"http_{status}")

        try:
            candidates = json.loads(body) or []
        except (ValueError, json.JSONDecodeError):
            return SmartyResult(False, False, "invalid_json")
        if not candidates:
            return SmartyResult(False, False, "no_match")

        top = candidates[0]
        record_type = (top.get("metadata") or {}).get("record_type", "")
        cmra = (top.get("analysis") or {}).get("dpv_cmra", "")
        is_po = record_type == "P" or cmra == "Y"
        cmra_note = ",cmra=Y" if cmra == "Y" else ""
        return SmartyResult(
            ok=True,
            is_po_box=is_po,
            reason=f"smarty:record_type={record_type or '?'}{cmra_note}",
        )

    @staticmethod
    def _parse(address: str) -> dict[str, str]:
        parts = [p.strip() for p in address.split(",")]
        out: dict[str, str] = {"street": parts[0] if parts else address}
        if len(parts) >= 2:
            out["city"] = parts[1]
        if len(parts) >= 3:
            tail = parts[2].split()
            if tail:
                out["state"] = tail[0]
            if len(tail) >= 2:
                out["zipcode"] = tail[1]
        return out
