"""The fail-closed decision model.

Regex may BLOCK, but only an authoritative, unambiguous provider result with no
PO/CMRA/PBSA indicators may ALLOW. Everything else — blank fields, ambiguity,
provider failure — is REVIEW. A provider `ok=False` must NEVER become ALLOW.

Smarty field references (us-street API):
  metadata.record_type   P=PO Box, G=General Delivery, R=Rural Route,
                         S=Street, H=High-rise, F=Firm; blank => no DPV match
  metadata.zip_type      "POBox" for PO-Box-only ZIPs
  metadata.carrier_route C770–C779 => PO Box Street Addressing
  analysis.dpv_cmra      Y=CMRA, N=not CMRA, blank=not evaluated
  analysis.dpv_match_code Y=confirmed, S/D=confirmed w/ secondary problem, N=no
  analysis.dpv_footnotes PB=PO Box street-style, RR=confirmed PMB, R1=CMRA w/o
                         PMB, P1/P3=box number missing/invalid, G1=general del.
  components.pmb_designator / pmb_number  private mailbox markers
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum

# record_type values that represent a usable physical address. Compliance can
# tune this per customer type (e.g. individuals vs entities).
DEFAULT_ALLOWED_RECORD_TYPES = frozenset({"S", "H", "F"})

_PBSA_CARRIER = re.compile(r"C77[0-9]")  # C770–C779 = PO Box Street Addressing

# dpv_footnote codes that, while not a hard PO/CMRA confirmation, mean we lack
# the evidence to clear the address.
_REVIEW_FOOTNOTES = frozenset({"P1", "P3", "G1", "R1"})


class AddressDecision(str, Enum):
    ALLOW_PHYSICAL = "allow_physical"
    BLOCK_PO_CMRA = "block_po_cmra"
    REVIEW_UNVERIFIED = "review_unverified"
    REVIEW_AMBIGUOUS = "review_ambiguous"


@dataclass(frozen=True)
class Decision:
    decision: AddressDecision
    reason: str
    evidence: dict = field(default_factory=dict)

    @property
    def allowed(self) -> bool:
        return self.decision is AddressDecision.ALLOW_PHYSICAL

    @property
    def blocked(self) -> bool:
        return self.decision is AddressDecision.BLOCK_PO_CMRA


def _footnote_codes(s: str) -> set[str]:
    """dpv_footnotes is concatenated 2-char codes, e.g. 'AABBPB'."""
    s = s or ""
    return {s[i:i + 2] for i in range(0, len(s) - 1, 2)}


def _carrier_is_pbsa(carrier_route: str) -> bool:
    return bool(_PBSA_CARRIER.fullmatch(carrier_route or ""))


def _canonical_signature(c: dict) -> tuple[str, str, str, str]:
    """Identity of the resolved delivery point (top-level Smarty fields).

    Two candidates with the same signature are the same physical address; two
    with different signatures are genuinely different addresses, so a
    multi-candidate response cannot be auto-cleared.
    """
    return (
        (c.get("delivery_line_1") or "").strip().upper(),
        (c.get("delivery_line_2") or "").strip().upper(),
        (c.get("last_line") or "").strip().upper(),
        (c.get("delivery_point_barcode") or "").strip(),
    )


def evaluate_smarty_candidates(
    candidates: list[dict],
    *,
    allowed_record_types: frozenset[str] = DEFAULT_ALLOWED_RECORD_TYPES,
    require_dpv_match_y: bool = True,
) -> Decision:
    """Fail-closed verdict over the full candidate set.

    Any candidate carrying a PO/CMRA/PBSA indicator blocks the whole address.
    ALLOW requires a clean, verified physical candidate and no review flags.
    """
    if not candidates:
        return Decision(
            AddressDecision.REVIEW_UNVERIFIED, "smarty:no_candidates", {"stage": "smarty"}
        )

    evidence: dict = {"stage": "smarty", "candidate_count": len(candidates), "flags": []}

    for c in candidates:
        meta = c.get("metadata") or {}
        analysis = c.get("analysis") or {}
        comp = c.get("components") or {}

        record_type = meta.get("record_type", "") or ""
        zip_type = meta.get("zip_type", "") or ""
        carrier_route = meta.get("carrier_route", "") or ""
        dpv_cmra = analysis.get("dpv_cmra", "") or ""
        dpv_match = analysis.get("dpv_match_code", "") or ""
        dpv_vacant = analysis.get("dpv_vacant", "") or ""
        dpv_no_stat = analysis.get("dpv_no_stat", "") or ""
        ews_match = analysis.get("ews_match")   # street not yet deliverable
        codes = _footnote_codes(analysis.get("dpv_footnotes", ""))
        pmb = comp.get("pmb_designator") or comp.get("pmb_number")

        hard_block = (
            record_type == "P"
            or dpv_cmra == "Y"
            or "PB" in codes
            or "RR" in codes
            or bool(pmb)
            or _carrier_is_pbsa(carrier_route)
            or zip_type == "POBox"
        )
        if hard_block:
            return Decision(
                AddressDecision.BLOCK_PO_CMRA,
                "smarty:po_cmra_or_pbsa_indicator",
                {
                    "stage": "smarty",
                    "record_type": record_type,
                    "zip_type": zip_type,
                    "carrier_route": carrier_route,
                    "dpv_cmra": dpv_cmra,
                    "dpv_footnotes": "".join(sorted(codes)),
                    "pmb_designator": comp.get("pmb_designator"),
                    "pmb_number": comp.get("pmb_number"),
                },
            )

        review = (
            record_type not in allowed_record_types   # blank, G, R, etc.
            or dpv_cmra == ""                          # CMRA not evaluated -> cannot clear
            or (require_dpv_match_y and dpv_match != "Y")
            or dpv_vacant == "Y"
            or dpv_no_stat == "Y"
            or bool(ews_match)                         # not yet ready for delivery
            or bool(_REVIEW_FOOTNOTES & codes)
        )
        if review:
            evidence["flags"].append({
                "record_type": record_type,
                "dpv_match_code": dpv_match,
                "dpv_cmra": dpv_cmra,
                "dpv_vacant": dpv_vacant,
                "dpv_no_stat": dpv_no_stat,
                "ews_match": bool(ews_match),
                "dpv_footnotes": "".join(sorted(codes)),
            })

    if evidence["flags"]:
        if len(candidates) > 1:
            return Decision(AddressDecision.REVIEW_AMBIGUOUS, "smarty:mixed_candidates", evidence)
        return Decision(AddressDecision.REVIEW_UNVERIFIED, "smarty:insufficient_evidence", evidence)

    # All candidates are clean physical addresses. A single candidate clears;
    # multiple must collapse to one canonical delivery point — otherwise we do
    # not know which physical address the customer meant.
    if len(candidates) == 1:
        return Decision(AddressDecision.ALLOW_PHYSICAL, "smarty:verified_physical", evidence)

    signatures = {_canonical_signature(c) for c in candidates}
    if any(not sig[0] or not sig[2] for sig in signatures):
        return Decision(
            AddressDecision.REVIEW_AMBIGUOUS, "smarty:multi_candidate_missing_canonical", evidence
        )
    if len(signatures) > 1:
        return Decision(
            AddressDecision.REVIEW_AMBIGUOUS, "smarty:multiple_distinct_candidates", evidence
        )
    return Decision(AddressDecision.ALLOW_PHYSICAL, "smarty:verified_physical", evidence)
