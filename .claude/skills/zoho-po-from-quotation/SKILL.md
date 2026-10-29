---
name: zoho-po-from-quotation
description: Create a Zoho Books purchase order from a supplier quotation PDF, attach the PDF and submit it for approval. Use when Khuder sends a quotation and asks to make/add a PO in Zoho (e.g. "اعمل PO على زوهو", "ضيف PO لهالكوتيشن").
---

# Zoho Books PO from a quotation

Tool: `zoho_po/zoho_po.py` (setup in `zoho_po/README.md`).

1. Read the quotation PDF (text with `pdftotext -layout`, and look at the rendered page:
   the supplier name is often only in the logo/header image).
2. Write `quotations/<reference>.json` in the format of `zoho_po/example_spec.json`:
   - `vendor_name`: supplier name as on the quotation (it is already registered in Zoho).
   - `reference_number`: the quotation number. `date`: quotation date, YYYY-MM-DD.
   - one line item per quoted line: `description`, `quantity`, `rate` (before VAT),
     `tax_percentage` (5 for UAE VAT, 0 if none). Add `account_name` only if it differs
     from `default_account_name` in `zoho_po/config.json`.
   - `expected_total`: the quotation grand total including VAT.
   Check the arithmetic (lines, VAT, total) and tell Khuder about any mismatch.
3. Copy the PDF to `quotations/` and run the dry run:
   `python zoho_po/zoho_po.py create quotations/<ref>.json quotations/<file>.pdf`
   If a vendor/account/tax lookup fails, fix the spec from the candidates it prints.
4. Show Khuder the dry-run summary (vendor, reference, lines, total) and wait for his OK.
5. Run again with `--execute`. Report the PO number it prints and whether it was submitted.

`quotations/` is git-ignored: never commit quotations (they contain bank details).
