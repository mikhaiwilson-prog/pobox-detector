"""Structured address input.

Prefer structured fields over one opaque string: it lets the provider isolate
the secondary unit / PMB designator (the thing that reveals a CMRA or PO Box
Street Address) and avoids brittle comma-splitting. `from_freeform` keeps
backward compatibility for callers that only have a single string.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AddressInput:
    line1: str = ""            # primary delivery line
    line2: str = ""            # secondary unit / box designator: "#409", "Apt 4"
    city: str = ""
    state: str = ""
    postal_code: str = ""
    country: str = "US"
    freeform: str = ""         # set when the caller only had one opaque string

    @classmethod
    def from_freeform(cls, s: str) -> AddressInput:
        return cls(freeform=s or "")

    @property
    def is_freeform(self) -> bool:
        return bool(self.freeform) and not (self.line1 or self.city or self.state)

    def combined_text(self) -> str:
        """All user-supplied text joined — used for regex screening."""
        if self.is_freeform:
            return self.freeform
        parts = (self.line1, self.line2, self.city, self.state, self.postal_code)
        return " ".join(p for p in parts if p)
