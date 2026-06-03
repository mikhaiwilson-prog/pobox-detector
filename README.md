# pobox-detector

The question this answers is **not** "is this string a PO Box?" 

It is: 

*"Do we have high-confidence evidence this is a usable physical address. Not a PO Box,
CMRA, PBSA, General Delivery, or unverified address?"* 

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



## Config

| Field / env var | Purpose |
|---|---|
| `smarty_auth_id` / `SMARTY_AUTH_ID` | Smarty server-side Auth ID |
| `smarty_auth_token` / `SMARTY_AUTH_TOKEN` | Smarty server-side Auth Token |
| `dry_run` / `POBOX_DRY_RUN=1` | Skip Smarty; un-blocked input becomes `REVIEW_UNVERIFIED` (still fail-closed) |

## Install / test

```bash
pip install -e .[dev]
pytest -q
```

Zero runtime dependencies (stdlib only).
