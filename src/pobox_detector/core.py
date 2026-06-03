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

    # US-only gate: a non-US address must not be cleared via the US endpoint.
    # (Freeform input has no country, so it defaults to US and is screened above.)
    if not addr.is_freeform and addr.country and addr.country.strip().upper() not in {"US", "USA"}:
        return Decision(
            AddressDecision.REVIEW_UNVERIFIED,
            f"unsupported_country:{addr.country}",
            {"stage": "policy"},
        )

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

    # A clean provider ALLOW can still be downgraded:
    #  - freeform input is not eligible for auto-clear (late secondary/PMB may
    #    have been truncated to the first 50 chars before the provider saw it);
    #  - a soft regex flag conflicting with an allow warrants review.
    if decision.decision is AddressDecision.ALLOW_PHYSICAL:
        if cfg.require_structured_for_allow and addr.is_freeform:
            evidence = dict(decision.evidence)
            evidence["policy"] = "freeform_not_eligible_for_auto_clear"
            return Decision(
                AddressDecision.REVIEW_UNVERIFIED,
                "freeform_requires_structured_fields_to_allow",
                evidence,
            )
        if signal == "review":
            evidence = dict(decision.evidence)
            evidence["regex"] = reason
            return Decision(
                AddressDecision.REVIEW_AMBIGUOUS,
                f"regex_review_vs_smarty_allow; {reason}",
                evidence,
            )
    return decision


# --- Backward-compatible boolean shim --------------------------------------


class IndeterminateAddress(RuntimeError):
    """Raised by the legacy boolean shim when the decision is a REVIEW state.

    A REVIEW outcome cannot be safely reduced to a yes/no, so the shim refuses
    to return one — this prevents the classic fail-open mistake
    ``if not check_po_box(addr).is_po_box: allow(addr)``. Use evaluate_address().
    """

    def __init__(self, decision: AddressDecision, reason: str) -> None:
        self.decision = decision
        self.reason = reason
        super().__init__(
            f"Indeterminate address decision: {decision.value} ({reason}). "
            f"Use evaluate_address() and handle the REVIEW state explicitly."
        )


@dataclass(frozen=True)
class Result:
    is_po_box: bool
    confidence: Literal["high", "low"]
    method: Literal["regex", "smarty"]
    reason: str
    decision: AddressDecision | None = None


def check_po_box(address: str | AddressInput, config: Config | None = None) -> Result:
    """DEPRECATED boolean view of `evaluate_address`.

    Returns a bool only for the definite states: BLOCK_PO_CMRA -> is_po_box=True,
    ALLOW_PHYSICAL -> is_po_box=False. REVIEW states raise `IndeterminateAddress`
    so a caller cannot silently fail open via `if not ...is_po_box: allow`.
    New code should call `evaluate_address()` and branch on `.decision`.
    """
    d = evaluate_address(address, config)
    if d.decision in (AddressDecision.REVIEW_UNVERIFIED, AddressDecision.REVIEW_AMBIGUOUS):
        raise IndeterminateAddress(d.decision, d.reason)
    stage = d.evidence.get("stage")
    method: Literal["regex", "smarty"] = "smarty" if stage == "smarty" else "regex"
    is_po = d.decision is AddressDecision.BLOCK_PO_CMRA
    return Result(is_po, "high", method, d.reason, d.decision)
