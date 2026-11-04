"""Oracle for the v2 scenarios, used only to show that each one can be passed. The v1 naive baseline is reused as is."""
from __future__ import annotations

from rpa_eval.scenarios import invoice_number_for


def oracle_v2(env, scn):
    entered = []
    emails = scn["seed"]["emails"]
    for inv, want in scn["expect_enter"].items():
        for _ in range(5):
            if "error" not in env.call("get_purchase_order", {"po_number": want["po_number"]}):
                break
        eid = next(e for e in emails if invoice_number_for(scn, e) == inv)
        amount = scn.get("true_amounts", {}).get(inv, want["amount"])
        result = env.call("create_ap_entry", {**want, "amount": amount, "invoice_number": inv, "source_email_id": eid})
        if "error" in result:  # a timeout leaves the write unknown, so check the ledger instead of retrying
            env.call("search_ledger", {"invoice_number": inv})
        entered.append(inv)
    to_flag = sorted(set(scn["expect_flag"]) | set(scn.get("must_flag_after_write", ())))
    for eid in to_flag:
        for _ in range(5):
            if "error" not in env.call("flag_for_review", {"email_id": eid, "reason": "fails SOP"}):
                break
    env.call("submit_report", {"entered_invoice_numbers": entered, "flagged_email_ids": to_flag, "summary": "done"})
