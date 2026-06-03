"""Deterministic PO Box classifier.

Two stages: a fast regex stage handles obvious input, and a Smarty US Street
Address API fallback handles ambiguous input. CMRA addresses (UPS-Store-style
mailboxes flagged by Smarty's DPV CMRA indicator) are folded into is_po_box=True
per product decision.

Public API:
    check_po_box(address, config=None) -> Result
    Config(smarty_auth_id, smarty_auth_token, dry_run)
    Result(is_po_box, confidence, method, reason)
"""
from .config import Config
from .core import Result, check_po_box

__all__ = ["check_po_box", "Result", "Config"]
__version__ = "0.1.0"
