# pobox-detector

Deterministic Python library that classifies whether an address is a PO Box.

Two-stage pipeline:
1. **Regex stage** — pure-function, zero network. Catches obviously-labeled PO Boxes (`PO Box`, `P.O. Box`, `PMB`, `Postal Box`, `PO Drawer`, `Lock Box`) and obviously-street addresses (leading number + recognized suffix).
2. **Smarty US Street Address fallback** — only called when the regex stage is uncertain. Uses `metadata.record_type == "P"` or `analysis.dpv_cmra == "Y"` to flag PO Boxes and CMRA mailboxes (UPS Store, iPostal1, etc.) the same way.

## Install

```bash
pip install -e .
```

## Use

```python
from pobox_detector import check_po_box, Config

# Read SMARTY_AUTH_ID / SMARTY_AUTH_TOKEN from env:
result = check_po_box("PO Box 5")
# Result(is_po_box=True, confidence='high', method='regex', reason="matched:'PO Box'")

# Or pass an explicit config (the backend-integration path):
cfg = Config(smarty_auth_id=settings.SMARTY_ID, smarty_auth_token=settings.SMARTY_TOKEN)
result = check_po_box("Ste 400, Reno, NV 89501", config=cfg)
# Result(is_po_box=..., confidence='high', method='smarty', reason='smarty:record_type=...')
```

## Result

```python
@dataclass(frozen=True)
class Result:
    is_po_box: bool
    confidence: Literal["high", "low"]   # high = signal trusted, low = degraded path
    method: Literal["regex", "smarty"]
    reason: str                          # short trace for logging
```

CMRA addresses (e.g. UPS Store) are folded into `is_po_box=True`.

## Config

| Field / env var | Purpose |
|---|---|
| `smarty_auth_id` / `SMARTY_AUTH_ID` | Smarty server-side Auth ID |
| `smarty_auth_token` / `SMARTY_AUTH_TOKEN` | Smarty server-side Auth Token |
| `dry_run` / `POBOX_DRY_RUN=1` | Skip Smarty calls; return regex best-guess |


## Test

```bash
pip install -e .[dev]
pytest -q
```
