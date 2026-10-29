"""Create a Zoho Books purchase order from a supplier quotation.

Flow: resolve vendor / location / account / tax by name -> create the PO as a
draft with the quotation PDF attached -> check the total -> submit for approval.

Credentials come from environment variables (never from files in the repo):
  ZOHO_CLIENT_ID, ZOHO_CLIENT_SECRET, ZOHO_REFRESH_TOKEN, ZOHO_ORG_ID
  ZOHO_ACCOUNTS_URL (default https://accounts.zoho.com)
  ZOHO_API_DOMAIN   (default https://www.zohoapis.com)

Usage:
  python zoho_po/zoho_po.py lookup                      # list locations, taxes, expense accounts
  python zoho_po/zoho_po.py create SPEC.json PDF        # dry run: resolve everything, write nothing
  python zoho_po/zoho_po.py create SPEC.json PDF --execute [--no-submit]
"""
import argparse
import json
import os
import sys
from pathlib import Path

import requests

HERE = Path(__file__).resolve().parent
CONFIG = json.loads((HERE / "config.json").read_text())


def env(name, default=None):
    value = os.environ.get(name, default)
    if not value:
        sys.exit(f"Missing environment variable {name}")
    return value


class Zoho:
    def __init__(self):
        self.org_id = env("ZOHO_ORG_ID")
        self.base = env("ZOHO_API_DOMAIN", "https://www.zohoapis.com") + "/books/v3"
        r = requests.post(
            env("ZOHO_ACCOUNTS_URL", "https://accounts.zoho.com") + "/oauth/v2/token",
            params={
                "refresh_token": env("ZOHO_REFRESH_TOKEN"),
                "client_id": env("ZOHO_CLIENT_ID"),
                "client_secret": env("ZOHO_CLIENT_SECRET"),
                "grant_type": "refresh_token",
            },
            timeout=30,
        )
        token = r.json().get("access_token")
        if not token:
            sys.exit(f"Could not get Zoho access token: {r.text}")
        self.headers = {"Authorization": f"Zoho-oauthtoken {token}"}

    def call(self, method, path, **kwargs):
        params = {"organization_id": self.org_id, **kwargs.pop("params", {})}
        r = requests.request(method, self.base + path, headers=self.headers,
                             params=params, timeout=60, **kwargs)
        body = r.json()
        if body.get("code") != 0:
            sys.exit(f"Zoho error on {method} {path}: {body.get('message')} ({r.status_code})")
        return body


def norm(s):
    return " ".join((s or "").lower().replace(".", "").replace(",", "").split())


def pick(rows, name, key, what):
    """Return the row whose `key` matches `name` exactly (ignoring case/punctuation)."""
    matches = [r for r in rows if norm(r.get(key)) == norm(name)]
    if len(matches) != 1:
        options = ", ".join(sorted({r.get(key, "") for r in rows})[:30])
        sys.exit(f"{what} '{name}': {len(matches)} exact matches. Available: {options}")
    return matches[0]


def find_vendor(z, spec):
    if spec.get("vendor_id"):
        return spec["vendor_id"], spec.get("vendor_name", "")
    name = spec["vendor_name"]
    # Zoho's search_text is a "contains" search, so search on the first word and match exactly here.
    rows = z.call("GET", "/contacts", params={"search_text": name.split()[0]})["contacts"]
    rows = [r for r in rows if r.get("contact_type") == "vendor"]
    exact = [r for r in rows if norm(name) in (norm(r.get("contact_name")), norm(r.get("company_name")))]
    if len(exact) != 1:
        options = "; ".join(f"{r['contact_name']} [{r['contact_id']}]" for r in rows[:20])
        sys.exit(f"Vendor '{name}': {len(exact)} exact matches. Candidates: {options or 'none'}. "
                 "Put the right one in the spec as vendor_id.")
    return exact[0]["contact_id"], exact[0]["contact_name"]


def find_tax(taxes, line):
    if line.get("tax_name"):
        return pick(taxes, line["tax_name"], "tax_name", "Tax")["tax_id"]
    pct = line.get("tax_percentage", CONFIG["default_tax_percentage"])
    if not pct:
        return None
    matches = [t for t in taxes if float(t.get("tax_percentage", -1)) == float(pct)
               and t.get("tax_type") == "tax"]
    if len(matches) != 1:
        names = ", ".join(f"{t['tax_name']} ({t['tax_percentage']}%)" for t in taxes)
        sys.exit(f"{len(matches)} taxes at {pct}%. Set tax_name on the line. Available: {names}")
    return matches[0]["tax_id"]


def build_payload(z, spec):
    vendor_id, vendor_name = find_vendor(z, spec)
    locations = z.call("GET", "/locations")["locations"]
    location = pick(locations, spec.get("location_name", CONFIG["location_name"]), "location_name", "Location")
    accounts = z.call("GET", "/chartofaccounts", params={"filter_by": "AccountType.Active"})["chartofaccounts"]
    taxes = z.call("GET", "/settings/taxes")["taxes"]

    line_items = []
    for line in spec["line_items"]:
        account_name = line.get("account_name") or CONFIG["default_account_name"]
        if not account_name:
            sys.exit("No account_name on the line and no default_account_name in config.json")
        item = {
            "description": line["description"],
            "quantity": line.get("quantity", 1),
            "rate": line["rate"],
            "account_id": pick(accounts, account_name, "account_name", "Account")["account_id"],
        }
        tax_id = find_tax(taxes, line)
        if tax_id:
            item["tax_id"] = tax_id
        line_items.append(item)

    payload = {
        "vendor_id": vendor_id,
        "location_id": location["location_id"],
        "reference_number": spec["reference_number"],
        "date": spec["date"],
        "is_inclusive_tax": False,
        "line_items": line_items,
    }
    for key in ("notes", "expected_delivery_date"):
        if spec.get(key):
            payload[key] = spec[key]
    if CONFIG.get("delivery_org_address_id"):
        payload["delivery_org_address_id"] = CONFIG["delivery_org_address_id"]
    return payload, vendor_name, location["location_name"]


def cmd_lookup(z, _args):
    print("Locations:")
    for loc in z.call("GET", "/locations")["locations"]:
        print(f"  {loc['location_name']}  [{loc['location_id']}]")
    print("Taxes:")
    for t in z.call("GET", "/settings/taxes")["taxes"]:
        print(f"  {t['tax_name']}  {t.get('tax_percentage')}%  [{t['tax_id']}]")
    print("Expense accounts:")
    for a in z.call("GET", "/chartofaccounts", params={"filter_by": "AccountType.Expense"})["chartofaccounts"]:
        print(f"  {a['account_name']}  [{a['account_id']}]")


def cmd_create(z, args):
    spec = json.loads(Path(args.spec).read_text())
    pdf = Path(args.pdf)
    if not pdf.is_file():
        sys.exit(f"PDF not found: {pdf}")
    payload, vendor_name, location_name = build_payload(z, spec)

    print(f"Vendor:    {vendor_name}")
    print(f"Location:  {location_name}")
    print(f"Reference: {payload['reference_number']}   Date: {payload['date']}")
    for item in payload["line_items"]:
        print(f"  - {item['quantity']} x {item['rate']}  {item['description'][:80]}")
    print(f"Attachment: {pdf.name}")
    if not args.execute:
        print("\nDry run only. Re-run with --execute to create the PO in Zoho Books.")
        return

    po = z.call("POST", "/purchaseorders", data={"JSONString": json.dumps(payload)})["purchaseorder"]
    po_id, po_number = po["purchaseorder_id"], po["purchaseorder_number"]
    print(f"\nCreated draft {po_number} [{po_id}]  total {po['total']} {po.get('currency_code', '')}")

    with pdf.open("rb") as f:
        z.call("POST", f"/purchaseorders/{po_id}/attachment",
               files={"attachment": (pdf.name, f, "application/pdf")})
    print(f"Attached {pdf.name}")

    expected = spec.get("expected_total")
    if expected is not None and abs(float(po["total"]) - float(expected)) > 0.01:
        sys.exit(f"Total {po['total']} != quotation total {expected}. Left {po_number} as draft, not submitted.")

    if args.no_submit:
        print(f"{po_number} left as draft (--no-submit).")
        return
    z.call("POST", f"/purchaseorders/{po_id}/submit")
    print(f"Submitted {po_number} for approval.")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("lookup")
    create = sub.add_parser("create")
    create.add_argument("spec", help="JSON file with the PO details read from the quotation")
    create.add_argument("pdf", help="quotation PDF to attach")
    create.add_argument("--execute", action="store_true", help="actually create the PO (default: dry run)")
    create.add_argument("--no-submit", action="store_true", help="leave the PO as draft")
    args = parser.parse_args()
    z = Zoho()
    {"lookup": cmd_lookup, "create": cmd_create}[args.command](z, args)


if __name__ == "__main__":
    main()
