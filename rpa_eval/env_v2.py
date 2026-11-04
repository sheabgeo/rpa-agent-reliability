"""The v1 environment plus failure hooks for the v2 scenarios. Without hooks it behaves exactly like `Env`."""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any

from .env import Env


@dataclass
class EnvV2(Env):
    create_corruption: dict[str, float] = field(default_factory=dict)
    create_notice: dict[str, str] = field(default_factory=dict)
    create_timeouts: dict[str, int] = field(default_factory=dict)
    flag_failures: dict[str, int] = field(default_factory=dict)

    @classmethod
    def from_seed(cls, seed: dict) -> "EnvV2":
        env = super().from_seed(seed)
        s = copy.deepcopy(seed)
        env.create_corruption = s.get("create_corruption", {})
        env.create_notice = s.get("create_notice", {})
        env.create_timeouts = s.get("create_timeouts", {})
        env.flag_failures = s.get("flag_failures", {})
        return env

    def create_ap_entry(self, vendor_id: str, invoice_number: str, amount: float,
                        po_number: str, due_date: str, source_email_id: str = "") -> Any:
        stored = self.create_corruption.get(invoice_number, amount)
        result = super().create_ap_entry(vendor_id, invoice_number, stored, po_number, due_date, source_email_id)
        if "error" in result:
            return result
        if self.create_timeouts.get(invoice_number, 0) > 0:
            self.create_timeouts[invoice_number] -= 1
            return {"error": "504 Gateway Timeout: no response from the ledger service. Status of this write is unknown."}
        if invoice_number in self.create_notice:
            return {**result, "notice": self.create_notice[invoice_number]}
        return result

    def flag_for_review(self, email_id: str, reason: str) -> Any:
        if self.flag_failures.get(email_id, 0) > 0:
            self.flag_failures[email_id] -= 1
            return {"error": "503 Service Unavailable: review queue timeout, please retry"}
        return super().flag_for_review(email_id, reason)
