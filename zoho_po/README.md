# Zoho Books PO from quotation

Send Claude a supplier quotation PDF. Claude reads it and fills a spec JSON, then
`zoho_po.py` creates the purchase order in Zoho Books, attaches the PDF, checks the
total against the quotation and submits the PO for approval.

## One-time setup

1. **Self Client**: on https://api-console.zoho.com choose *Add Client → Self Client*.
   Note the Client ID and Client Secret.
2. **Grant code**: in the Self Client, open *Generate Code* and enter this scope:

   ```
   ZohoBooks.purchaseorders.ALL,ZohoBooks.contacts.READ,ZohoBooks.settings.READ,ZohoBooks.accountants.READ
   ```

   Pick the longest time duration (10 minutes) and copy the code.
3. **Refresh token**: before the code expires, run this in PowerShell on your own PC
   (replace the three values). It prints `refresh_token`. Do not paste it into chat.

   ```powershell
   Invoke-RestMethod -Method Post "https://accounts.zoho.com/oauth/v2/token?grant_type=authorization_code&client_id=CLIENT_ID&client_secret=CLIENT_SECRET&code=GRANT_CODE"
   ```

4. **Organization ID**: Zoho Books → Settings → Organization Profile.
5. Add these as secrets / environment variables in the Claude cloud environment
   (environment menu → Edit), then start a new session:

   | Variable | Value |
   |---|---|
   | `ZOHO_CLIENT_ID` | Client ID |
   | `ZOHO_CLIENT_SECRET` | Client Secret |
   | `ZOHO_REFRESH_TOKEN` | refresh_token from step 3 |
   | `ZOHO_ORG_ID` | Organization ID |

   If the Zoho account is not on zoho.com, also set `ZOHO_ACCOUNTS_URL` and
   `ZOHO_API_DOMAIN` (the token response in step 3 shows `api_domain`).

6. Run `python zoho_po/zoho_po.py lookup` and set `default_account_name` in
   `config.json` to the expense account used for these POs.

## Usage

```bash
python zoho_po/zoho_po.py create spec.json quotation.pdf            # dry run, writes nothing
python zoho_po/zoho_po.py create spec.json quotation.pdf --execute  # create + attach + submit
```

`--no-submit` leaves the PO as a draft. If the PO total differs from `expected_total`
in the spec, the PO stays a draft and is not submitted. See `example_spec.json` for the spec format.
