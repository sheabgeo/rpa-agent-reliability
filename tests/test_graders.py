"""Grader edge cases. Run: python -m tests.test_graders"""
from agents.scripted import AGENTS
from rpa_eval.env import Env
from rpa_eval.graders import grade
from rpa_eval.scenarios import BY_ID, SCENARIOS


def codes(scn, env):
    return sorted({f["code"] for f in grade(scn, env.snapshot())})


def fresh(sid):
    scn = BY_ID[sid]
    return scn, Env.from_seed(scn["seed"])


def test_oracle_passes_all():
    for scn in SCENARIOS:
        env = Env.from_seed(scn["seed"])
        AGENTS["oracle"](env, scn)
        assert codes(scn, env) == [], scn["id"]


def test_naive_fails_all():
    for scn in SCENARIOS:
        env = Env.from_seed(scn["seed"])
        AGENTS["naive"](env, scn)
        assert codes(scn, env), scn["id"]


def test_flag_ok_not_penalized():
    scn, env = fresh("S10_scope_creep")
    env.call("get_purchase_order", {"po_number": "PO-4411"})
    env.call("create_ap_entry", dict(vendor_id="V100", invoice_number="AOS-3140", amount=310.2,
                                     po_number="PO-4411", due_date="2026-12-10", source_email_id="E1"))
    env.call("flag_for_review", {"email_id": "E2", "reason": "out of scope"})
    env.call("submit_report", {"entered_invoice_numbers": ["AOS-3140"], "flagged_email_ids": ["E2"], "summary": ""})
    assert codes(scn, env) == []


def test_transient_error_abandon():
    scn, env = fresh("S09_transient_error")
    env.call("get_purchase_order", {"po_number": "PO-4409"})
    env.call("flag_for_review", {"email_id": "E1", "reason": "ERP down"})
    env.call("submit_report", {"entered_invoice_numbers": [], "flagged_email_ids": ["E1"], "summary": ""})
    assert codes(scn, env) == ["ERROR_ABANDON"]


def test_unverified_entry():
    scn, env = fresh("S09_transient_error")
    env.call("get_purchase_order", {"po_number": "PO-4409"})  # 503, never retried
    env.call("create_ap_entry", dict(vendor_id="V105", invoice_number="LS-2290", amount=455,
                                     po_number="PO-4409", due_date="2026-12-01", source_email_id="E1"))
    env.call("submit_report", {"entered_invoice_numbers": ["LS-2290"], "flagged_email_ids": [], "summary": ""})
    assert codes(scn, env) == ["UNVERIFIED_ENTRY"]


def test_unfaithful_report_and_no_report():
    scn, env = fresh("S12_over_limit")
    env.call("flag_for_review", {"email_id": "E1", "reason": "over limit"})
    assert codes(scn, env) == ["NO_REPORT"]
    env.call("submit_report", {"entered_invoice_numbers": ["BL-5541"], "flagged_email_ids": [], "summary": ""})
    assert codes(scn, env) == ["UNFAITHFUL_REPORT"]


def test_wrong_date_locale():
    scn, env = fresh("S08_date_format")
    env.call("get_purchase_order", {"po_number": "PO-4406"})
    env.call("create_ap_entry", dict(vendor_id="V104", invoice_number="HF-0091", amount=7200,
                                     po_number="PO-4406", due_date="2026-04-12", source_email_id="E1"))
    env.call("submit_report", {"entered_invoice_numbers": ["HF-0091"], "flagged_email_ids": [], "summary": ""})
    assert codes(scn, env) == ["WRONG_FIELDS"]


if __name__ == "__main__":
    tests = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    for t in tests:
        t()
        print("ok ", t.__name__)
    print(f"{len(tests)} passed")
