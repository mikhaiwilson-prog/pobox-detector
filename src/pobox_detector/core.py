"""Top-level public API: check_po_box() and Result."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Literal

from .config import Config
from .regex_stage import classify
from .smarty_stage import SmartyStage


@dataclass(frozen=True)
class Result:
    is_po_box: bool
    confidence: Literal["high", "low"]
    method: Literal["regex", "smarty"]
    reason: str


def check_po_box(address: str, config: Config | None = None) -> Result:
    """Classify an address as PO Box / not PO Box.

    Pass `config` explicitly for library use, or omit to read from env vars
    (SMARTY_AUTH_ID, SMARTY_AUTH_TOKEN, POBOX_DRY_RUN).

    CMRA addresses (Smarty `dpv_cmra=Y`) are folded into is_po_box=True.
    """
    cfg = config if config is not None else Config.from_env()
    cls, reason = classify(address)

    if cls == "po_box":
        return Result(True, "high", "regex", reason)
    if cls == "not_po_box":
        return Result(False, "high", "regex", reason)

    if cfg.dry_run:
        return Result(False, "low", "regex", f"dry_run; regex={reason}")
    if not cfg.smarty_available:
        return Result(False, "low", "regex", f"smarty_unavailable:missing_credentials; regex={reason}")

    smarty_result = SmartyStage(cfg).lookup(address)
    if smarty_result.ok:
        return Result(smarty_result.is_po_box, "high", "smarty", smarty_result.reason)
    return Result(False, "low", "regex", f"smarty_failed:{smarty_result.reason}; regex={reason}")
