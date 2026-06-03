"""Public API.

`evaluate_address(...) -> Decision` is the fail-closed gate — use this.
`check_po_box(...) -> Result` is a backward-compatible boolean shim.

Pipeline:
  normalize -> regex screen
    regex BLOCK               -> BLOCK_PO_CMRA (terminal; no provider call)
    otherwise                 -> Smarty (every candidate, full indicator set)
      provider untrusted      -> REVIEW_UNVERIFIED         (fail closed)
      authoritative + clean    -> ALLOW_PHYSICAL
      PO/CMRA/PBSA indicator    -> BLOCK_PO_CMRA
      ambiguous / insufficient  -> REVIEW_AMBIGUOUS / REVIEW_UNVERIFIED
  A soft regex hit floors the result at REVIEW — it can never become ALLOW.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .config import Config
from .decision import AddressDecision, Decision, evaluate_smarty_candidates
from .models import AddressInput
from .regex_stage import screen
from .smarty_stage import SmartyStage


def _as_input(address: str | AddressInput) -> AddressInput:
    return address if isinstance(address, AddressInput) else AddressInput.from_freeform(address)


def evaluate_address(address: str | AddressInput, config: Config | None = None) -> Decision:
    """Classify an address into one of four fail-closed states.

    Pass a structured `AddressInput` when you can (it lets the provider isolate
    the secondary/PMB designator); a plain string is treated as freeform.
    """
    cfg = config if config is not None else Config.from_env()
    addr = _as_input(address)

    signal, reason = screen(addr.combined_text())
    if signal == "block":
        return Decision(AddressDecision.BLOCK_PO_CMRA, reason, {"stage": "regex"})

    # Regex cannot clear an address — an authoritative provider result is
    # required. Without one, fail closed to review.
    if cfg.dry_run:
        return Decision(AddressDecision.REVIEW_UNVERIFIED, f"dry_run; {reason}", {"stage": "regex"})
    if not cfg.smarty_available:
        return Decision(
            AddressDecision.REVIEW_UNVERIFIED,
            f"smarty_unavailable:missing_credentials; {reason}",
            {"stage": "regex"},
        )

    resp = SmartyStage(cfg).lookup(addr)
    if not resp.ok:
        return Decision(
            AddressDecision.REVIEW_UNVERIFIED,
            f"smarty_failed:{resp.reason}",
            {"stage": "smarty", "ok": False},
        )

    decision = evaluate_smarty_candidates(
        resp.candidates,
        allowed_record_types=cfg.allowed_record_types,
        require_dpv_match_y=cfg.require_dpv_match_y,
    )

    # A soft regex flag must not be overridden by a clean provider allow:
    # the conflict itself warrants review.
    if signal == "review" and decision.decision is AddressDecision.ALLOW_PHYSICAL:
        evidence = dict(decision.evidence)
        evidence["regex"] = reason
        return Decision(
            AddressDecision.REVIEW_AMBIGUOUS,
            f"regex_review_vs_smarty_allow; {reason}",
            evidence,
        )
    return decision


# --- Backward-compatible boolean shim --------------------------------------


@dataclass(frozen=True)
class Result:
    is_po_box: bool
    confidence: Literal["high", "low"]
    method: Literal["regex", "smarty"]
    reason: str
    decision: AddressDecision | None = None


def check_po_box(address: str | AddressInput, config: Config | None = None) -> Result:
    """DEPRECATED boolean view of `evaluate_address`.

    `is_po_box` is True only for a confirmed PO/CMRA block. REVIEW states surface
    as `is_po_box=False, confidence="low"` — do NOT treat `confidence="low"` as
    "cleared to use". Gate on `evaluate_address(...).decision` instead.
    """
    d = evaluate_address(address, config)
    stage = d.evidence.get("stage")
    method: Literal["regex", "smarty"] = "smarty" if stage == "smarty" else "regex"
    is_po = d.decision is AddressDecision.BLOCK_PO_CMRA
    high = d.decision in (AddressDecision.ALLOW_PHYSICAL, AddressDecision.BLOCK_PO_CMRA)
    return Result(is_po, "high" if high else "low", method, d.reason, d.decision)
