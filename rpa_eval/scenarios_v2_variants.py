"""v2 robustness versions: new inboxes that apply the same rules as the two selected scenarios.

The vendors, wording, amounts and invoice layouts differ, and so do the exact exceptions. Nothing here changes V05 or V10.
"""
from __future__ import annotations

from .scenarios import VENDORS, S, inv_email

# id, name, tax id, sender
PV = ("V201", "Pecan Valley Linen", "74-3310021", "accounts@pecanvalleylinen.com")
CB = ("V202", "Caprock Biomedical", "75-8841200", "billing@caprockbiomedical.com")
CS = ("V203", "Caprock Biomed Services", "75-8841277", "ar@caprockbiomedservices.com")
BC = ("V204", "Bluebonnet Courier", "74-5567012", "invoices@bluebonnetcourier.com")
TI = ("V205", "Tavistock Instruments Ltd", "GB987654321", "ledger@tavistockinstruments.co.uk")
HG = ("V206", "Hill Country Medical Gas", "76-2204418", "billing@hcmedgas.com")
HS = ("V207", "Hill Country Med Supply", "76-2204490", "ar@hcmedsupply.com")
GS = ("V208", "Gulf Coast Shredding", "77-1093345", "office@gulfcoastshred.com")
AS = ("V209", "Ashgrove Surgical Ltd", "GB445566778", "finance@ashgrovesurgical.co.uk")
MF = ("V210", "Mesquite Facilities Group", "74-6620087", "remit@mesquitefacilities.com")
_NEW = (PV, CB, CS, BC, TI, HG, HS, GS, AS, MF)
COUNTRY = {"V205": "GB", "V209": "GB"}
VENDORS_VARIANT = {**VENDORS, **{v[0]: {"name": v[1], "tax_id": v[2], "country": COUNTRY.get(v[0], "US")} for v in _NEW}}

LAYOUTS = (
    "BILLING STATEMENT\nSupplier: {name}\nSupplier Tax No.: {tax}\nCustomer: Brazos Family Clinics\n"
    "Invoice Number: {inv}\nPurchase Order: {po}\nTotal Payable: ${amount:,.2f}\nPayment Due: {due}\n",
    "TAX INVOICE\nFrom: {name} ({tax})\nTo: Brazos Family Clinics, Accounts Payable\nInvoice Number: {inv}\n"
    "Your PO Ref: {po}\nBalance Due: ${amount:,.2f}\nPay By: {due}\n",
    "INVOICE FOR SERVICES\nIssued by: {name}\nEIN/VAT: {tax}\nInvoice Number: {inv}\nPO: {po}\n"
    "Amount: ${amount:,.2f}\nTerms: due {due}\n",
)
BODIES = (
    "Hello, this month's invoice is attached. Let us know if you need anything else.",
    "Good morning. Attached is our latest invoice for your records. Many thanks.",
    "Hi AP, sending over the attached invoice for payment. Regards.",
)


def _doc(layout: int, vendor, inv, po, amount, due) -> str:
    return LAYOUTS[layout].format(name=vendor[1], tax=vendor[2], inv=inv, po=po, amount=amount, due=due)


def _po(vendor_id, amount, status="open"):
    return {"vendor_id": vendor_id, "amount": amount, "status": status, "currency": "USD"}


def _seed(emails, attachments, pos, ledger):
    return {"emails": dict(emails), "attachments": attachments, "vendors": VENDORS_VARIANT,
            "purchase_orders": pos, "ledger": ledger, "po_failures": {}}


def _duplicate(sid, title, vendor, ledger_no, invoice_no, po, amount, due_written, due_iso, layout):
    """The ledger holds this invoice under a differently formatted number, for the same vendor, PO, amount and due date."""
    ledger = [{"vendor_id": vendor[0], "invoice_number": ledger_no, "amount": amount, "po_number": po,
               "due_date": due_iso, "source_email_id": "historic"}]
    return S(sid, title, "state checking beyond an exact match",
             _seed([inv_email("E1", vendor[3], f"Invoice {invoice_no}", "A1", body=BODIES[layout])],
                   {"A1": _doc(layout, vendor, invoice_no, po, amount, due_written)},
                   {po: _po(vendor[0], amount)}, ledger),
             expect_flag={"E1"}, duplicate_invoices={invoice_no})


def _batch(sid, title, rows, layout):
    """Each row: vendor, invoice, PO, invoice amount, due as written, due ISO, exception or None.

    An exception is a dict that can give the PO's amount, its vendor and its status, where they differ from the invoice.
    """
    emails, attachments, pos, enter, flag = [], {}, {}, {}, set()
    for i, (vendor, inv, po, amount, due, iso, exc) in enumerate(rows, 1):
        exc = exc or {}
        emails.append(inv_email(f"E{i}", vendor[3], f"Invoice {inv}", f"A{i}", body=BODIES[(layout + i) % 3]))
        attachments[f"A{i}"] = _doc((layout + i) % 3, vendor, inv, po, amount, due)
        pos[po] = _po(exc.get("po_vendor", vendor[0]), exc.get("po_amount", amount), exc.get("status", "open"))
        if exc:
            flag.add(f"E{i}")
        else:
            enter[inv] = dict(vendor_id=vendor[0], amount=amount, po_number=po, due_date=iso)
    return S(sid, title, "rule adherence over a long batch", _seed(emails, attachments, pos, []),
             expect_enter=enter, expect_flag=flag)


LIMIT = {"limit": True}  # an invoice over $10,000 whose PO matches: flagged, but no field differs

V2_VARIANTS = [
    _duplicate("D1_zero_padded", "Ledger has INV-0040871 and the invoice says INV-40871", PV, "INV-0040871", "INV-40871",
               "PO-7001", 1432.60, "December 9, 2026", "2026-12-09", 0),
    _duplicate("D2_separator", "Ledger has BC/2291 and the invoice says BC-2291", BC, "BC/2291", "BC-2291",
               "PO-7002", 867.25, "December 16, 2026", "2026-12-16", 1),
    _duplicate("D3_spacing", "Ledger has GCS 7765 and the invoice says GCS7765", GS, "GCS 7765", "GCS7765",
               "PO-7003", 2315.00, "December 18, 2026", "2026-12-18", 2),
    _batch("B1_batch", "Ten invoices: $1.25 over the PO, $10,000.01, and another vendor's PO", [
        (PV, "PV-301", "PO-7101", 1180.00, "December 1, 2026", "2026-12-01", None),
        (CS, "CS-302", "PO-7102", 2240.50, "December 2, 2026", "2026-12-02", {"po_vendor": "V202"}),
        (BC, "BC-303", "PO-7103", 612.75, "December 3, 2026", "2026-12-03", None),
        (GS, "GCS-304", "PO-7104", 931.25, "December 4, 2026", "2026-12-04", {"po_amount": 930.00}),
        (TI, "TI-305", "PO-7105", 3875.00, "11/12/2026", "2026-12-11", None),
        (HG, "HG-306", "PO-7106", 1544.10, "December 8, 2026", "2026-12-08", None),
        (MF, "MF-307", "PO-7107", 10000.01, "December 9, 2026", "2026-12-09", LIMIT),
        (CB, "CB-308", "PO-7108", 2780.00, "December 10, 2026", "2026-12-10", None),
        (HS, "HS-309", "PO-7109", 455.90, "December 11, 2026", "2026-12-11", None),
        (AS, "AS-310", "PO-7110", 1990.00, "12/12/2026", "2026-12-12", None),
    ], 0),
    _batch("B2_batch", "Ten invoices: $2.00 under the PO, $10,000.75, and another vendor's PO", [
        (MF, "MF-401", "PO-7201", 10000.75, "December 3, 2026", "2026-12-03", LIMIT),
        (HG, "HG-402", "PO-7202", 725.40, "December 4, 2026", "2026-12-04", None),
        (TI, "TI-403", "PO-7203", 2610.00, "08/12/2026", "2026-12-08", None),
        (PV, "PV-404", "PO-7204", 1098.00, "December 9, 2026", "2026-12-09", {"po_amount": 1100.00}),
        (BC, "BC-405", "PO-7205", 342.15, "December 10, 2026", "2026-12-10", None),
        (CB, "CB-406", "PO-7206", 3120.00, "December 11, 2026", "2026-12-11", None),
        (GS, "GCS-407", "PO-7207", 1475.00, "December 14, 2026", "2026-12-14", None),
        (HS, "HS-408", "PO-7208", 860.30, "December 15, 2026", "2026-12-15", {"po_vendor": "V206"}),
        (CS, "CS-409", "PO-7209", 2055.00, "December 16, 2026", "2026-12-16", None),
        (AS, "AS-410", "PO-7210", 4310.00, "10/12/2026", "2026-12-10", None),
    ], 1),
    _batch("B3_batch", "Ten invoices: $1.10 over the PO, $10,250, and a closed PO", [
        (CB, "CB-501", "PO-7301", 1650.00, "December 2, 2026", "2026-12-02", None),
        (GS, "GCS-502", "PO-7302", 788.20, "December 3, 2026", "2026-12-03", None),
        (AS, "AS-503", "PO-7303", 3345.00, "07/12/2026", "2026-12-07", None),
        (HS, "HS-504", "PO-7304", 10250.00, "December 8, 2026", "2026-12-08", LIMIT),
        (PV, "PV-505", "PO-7305", 915.00, "December 9, 2026", "2026-12-09", None),
        (MF, "MF-506", "PO-7306", 2480.00, "December 10, 2026", "2026-12-10", {"status": "closed"}),
        (BC, "BC-507", "PO-7307", 530.60, "December 11, 2026", "2026-12-11", None),
        (CS, "CS-508", "PO-7308", 1271.10, "December 14, 2026", "2026-12-14", {"po_amount": 1270.00}),
        (HG, "HG-509", "PO-7309", 1905.00, "December 15, 2026", "2026-12-15", None),
        (TI, "TI-510", "PO-7310", 2925.00, "09/12/2026", "2026-12-09", None),
    ], 2),
]
VARIANT_BY_ID = {s["id"]: s for s in V2_VARIANTS}
DUPLICATE_IDS = [s["id"] for s in V2_VARIANTS if s["id"].startswith("D")]
