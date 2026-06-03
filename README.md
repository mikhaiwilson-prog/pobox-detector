# pobox-detector

Fail-closed address classifier for CIP / KYB eligibility gating.

The question this answers is **not** "is this string a PO Box?" It is: *"Do we
have high-confidence evidence this is a usable physical address — not a PO Box,
CMRA, PBSA, General Delivery, or unverified address?"* For a banking use case,
**regex may block, but regex never conclusively allows.** Only an authoritative
address-validation result with every PO/CMRA/PBSA signal checked may allow;
everything else is blocked, re-prompted, or sent to manual review.

**US-only.** Verification is US addresses only. An address with an explicit
non-US country, and any freeform-only string, can be blocked or reviewed but is
never auto-cleared.

## Decision model

`evaluate_address(...)` returns one of four states — never a bare boolean:

| `AddressDecision` | Meaning | Suggested action |
|---|---|---|
| `ALLOW_PHYSICAL` | Verified physical address, no PO/CMRA/PBSA signal | Accept |
| `BLOCK_PO_CMRA` | Confirmed PO Box / CMRA / PO Box Street Address | Reject, re-prompt |
| `REVIEW_UNVERIFIED` | Not enough evidence (provider failed, blank fields, no match) | Manual review |
| `REVIEW_AMBIGUOUS` | Candidates disagree, or a soft regex hit conflicts with an allow | Manual review |

## Pipeline

```text
normalize all fields (NFKC, strip zero-width, map confusables)
  -> regex screen  (positive-only: may BLOCK or flag REVIEW, never ALLOWS)
       block            -> BLOCK_PO_CMRA            (terminal; no provider call)
       non-US country   -> REVIEW_UNVERIFIED        (US-only gate; no provider call)
       otherwise        -> Smarty US Street Address (every candidate, up to 10)
            provider untrusted        -> REVIEW_UNVERIFIED   (fail closed)
            verified + clean physical -> ALLOW_PHYSICAL
            any PO/CMRA/PBSA indicator -> BLOCK_PO_CMRA
            ambiguous / insufficient   -> REVIEW_*
  multiple candidates must collapse to one canonical delivery point to ALLOW,
    else REVIEW_AMBIGUOUS
  a clean ALLOW is downgraded to REVIEW if the input was freeform-only, or if a
    soft regex hit conflicts with it
```

A street suffix is **not** evidence of a physical address: CMRAs and USPS PO Box
Street Addressing deliberately use street-style formats (e.g. `500 Main Street
#59` that still delivers to a PO Box). The old "street suffix ⇒ not a PO Box"
shortcut has been removed.

### Smarty indicators checked

Block: `record_type=P`, `dpv_cmra=Y`, `dpv_footnotes` contains `PB` (PO Box
street-style) or `RR` (confirmed PMB), `components.pmb_designator`/`pmb_number`
present, `carrier_route` in `C770–C779`, `zip_type=POBox`.

Review (cannot clear): `record_type` not in the allowed physical set (`S/H/F` by
default — blank, `G` General Delivery and `R` Rural Route fall here),
`dpv_cmra=""` (CMRA not evaluated), `dpv_match_code != Y` (secondary dropped or
missing), `dpv_vacant=Y`, `dpv_no_stat=Y`, `ews_match` (street not yet
deliverable), footnotes `P1/P3/G1/R1`. With multiple candidates, ALLOW also
requires they share one canonical delivery point (`delivery_point_barcode` /
`delivery_line_1` + `last_line`); distinct candidates → `REVIEW_AMBIGUOUS`.

> Note: Smarty marks PO Boxes "Residential" in RDI, so `rdi` is **not** used as
> proof of a physical residence.

## Use

```python
from pobox_detector import evaluate_address, AddressInput, AddressDecision, Config

cfg = Config(smarty_auth_id=settings.SMARTY_ID, smarty_auth_token=settings.SMARTY_TOKEN)

# Prefer structured fields — the provider can then isolate the secondary / PMB
# designator, and there is no brittle comma-parsing.
d = evaluate_address(
    AddressInput(line1="3214 N University Ave", line2="#409", city="Provo", state="UT"),
    config=cfg,
)
if d.decision is AddressDecision.ALLOW_PHYSICAL:
    ...
elif d.decision is AddressDecision.BLOCK_PO_CMRA:
    ...
else:  # REVIEW_UNVERIFIED / REVIEW_AMBIGUOUS
    ...   # route to manual review; never auto-accept

# A single freeform string also works, but can only block/review — never
# auto-allow (the provider reads just the first 50 chars of a freeform street,
# so a late secondary/PMB can be dropped). Use structured fields to clear.
evaluate_address("PO Box 5", config=cfg)   # -> BLOCK_PO_CMRA (regex, no network)
```

`Decision` carries `decision`, a short `reason`, and an `evidence` dict
(record_type, footnotes, carrier route, candidate count, …) for the audit trail.

### Deprecated boolean shim

`check_po_box(...) -> Result` is kept for backward compatibility but returns a
bool **only** for the definite states (`BLOCK_PO_CMRA → is_po_box=True`,
`ALLOW_PHYSICAL → is_po_box=False`). A REVIEW outcome **raises
`IndeterminateAddress`** rather than returning `is_po_box=False`, so the classic
fail-open mistake `if not check_po_box(addr).is_po_box: allow(addr)` cannot
silently pass an unverified address. Gate new code on
`evaluate_address(...).decision`.

## Config

| Field / env var | Purpose |
|---|---|
| `smarty_auth_id` / `SMARTY_AUTH_ID` | Smarty server-side Auth ID |
| `smarty_auth_token` / `SMARTY_AUTH_TOKEN` | Smarty server-side Auth Token |
| `dry_run` / `POBOX_DRY_RUN=1` | Skip Smarty; un-blocked input becomes `REVIEW_UNVERIFIED` (still fail-closed) |
| `candidates` | Candidates to request for ambiguous input (default 10; clamped to `[1, 10]`) |
| `allowed_record_types` | `record_type`s eligible for ALLOW (default `{S,H,F}`) |
| `require_dpv_match_y` | Require `dpv_match_code == "Y"` to allow (default True) |
| `require_structured_for_allow` | Freeform input may block/review but never auto-ALLOW (default True) |

Provider failure, quota exhaustion, SSL error, malformed JSON, or no credentials
all degrade to `REVIEW_UNVERIFIED` — never to ALLOW.

## Caller responsibilities (out of scope for this library)

This library decides one address. A production CIP/KYB gate still needs:

- **Audit trail** — persist normalized input, provider request ID, the
  `evidence` fields, decision, reason, and rules version. Never log Smarty auth
  tokens or full query URLs.
- **Manual review path** — don't hard-deny edge cases automatically; handle
  documented exceptions (e.g. state Address Confidentiality Program participants).
- **Separate mailing vs CIP addresses** — a PO Box may be fine as a *mailing*
  address while a physical address is still required for CIP.
- **Monitoring** — seed known CMRA/PBSA examples into daily tests; alert on
  spikes in blank/ambiguous/failed provider responses.
- **Second source for high-risk cases** — a second provider or maintained
  CMRA/PBSA dataset reduces vendor-specific blind spots.

## Install / test

```bash
pip install -e .[dev]
pytest -q
```

Zero runtime dependencies (stdlib only).
