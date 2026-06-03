"""Fail-closed address classifier for CIP / KYB eligibility gating.

The gate answers "do we have high-confidence evidence this is a usable physical
address, and not a PO Box, CMRA, PBSA, General Delivery, or unverified address?"
— not merely "is this string a PO Box?".

Pipeline: normalize -> positive-only regex (may BLOCK, never ALLOWS) -> Smarty
US Street Address verification over every candidate, checking the full set of
PO/CMRA/PBSA indicators. Anything missing, ambiguous, provider-failed, non-US,
or freeform-only is REVIEW, never a pass.

US-only: an address with an explicit non-US country is returned as
REVIEW_UNVERIFIED rather than validated against the US endpoint.

Public API:
    evaluate_address(address, config=None) -> Decision   # the gate; use this
    AddressDecision                                       # ALLOW/BLOCK/REVIEW*
    Decision(decision, reason, evidence)
    AddressInput(line1, line2, city, state, postal_code, country)
    Config(...)
    check_po_box(address, config=None) -> Result          # deprecated bool shim
    IndeterminateAddress                                  # raised by the shim on REVIEW
"""
from .config import Config
from .core import IndeterminateAddress, Result, check_po_box, evaluate_address
from .decision import AddressDecision, Decision
from .models import AddressInput

__all__ = [
    "evaluate_address",
    "AddressDecision",
    "Decision",
    "AddressInput",
    "Config",
    "Result",
    "check_po_box",
    "IndeterminateAddress",
]
__version__ = "0.3.0"
