"""Configuration. A library caller can either construct Config explicitly or
let `Config.from_env()` read SMARTY_AUTH_ID / SMARTY_AUTH_TOKEN / POBOX_DRY_RUN."""
from __future__ import annotations
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    smarty_auth_id: str | None = None
    smarty_auth_token: str | None = None
    dry_run: bool = False

    @property
    def smarty_available(self) -> bool:
        return bool(self.smarty_auth_id and self.smarty_auth_token) and not self.dry_run

    @classmethod
    def from_env(cls) -> Config:
        return cls(
            smarty_auth_id=os.environ.get("SMARTY_AUTH_ID") or None,
            smarty_auth_token=os.environ.get("SMARTY_AUTH_TOKEN") or None,
            dry_run=os.environ.get("POBOX_DRY_RUN", "") == "1",
        )
