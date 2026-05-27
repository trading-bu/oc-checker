# OC Checker — End-to-End Workflow

## What it does
Automatically checks supplier Order Confirmation (OC) PDFs against Vanilla Steel's purchase orders in Odoo, and posts a match/mismatch result to Slack.

---

## Systems involved

| System | Purpose | Cost |
|---|---|---|
| Gmail | Where OC emails arrive | Free |
| Google Apps Script | Monitors Gmail, uploads PDFs to Docsumo | Free |
| Docsumo | Extracts structured data from OC PDFs | Paid |
| GitHub Actions | Runs the checker on a schedule | Free |
| Odoo | Source of truth for POs and SOs | Existing ERP |
| Slack | Delivers the match/mismatch result | Free |

---

## Step-by-step flow

### 1. Email arrives
A supplier sends an OC PDF to mridul.goel@vanillasteel.com.
Two scenarios:
- **Direct from supplier** — caught automatically by keyword filter in Apps Script
- **Forwarded from a colleague** — Mridul manually applies the Gmail label `OC-Upload`

### 2. Google Apps Script (runs every hour)
File: `google_apps_script/saveOCsToDrive.js`

Does two searches in Gmail:
- AUTO: emails with OC keywords in subject (Auftragsbestätigung, Order Confirmation, etc.) that have a PDF attachment and are not already labelled `OC-Saved`
- MANUAL: emails labelled `OC-Upload` regardless of sender or subject

For each matching email:
- Skips emails sent from `@vanillasteel.com` (auto path only) to avoid catching VS's own outgoing orders
- Skips PDFs whose filename suggests it's not an OC (invoices, delivery notes, etc.)
- Saves the PDF to Google Drive folder `OC Inbox` (backup copy)
- Uploads the PDF to Docsumo via API (`POST /api/v1/eevee/apikey/upload/` with field `type=others__vNgOt`)
- Labels the thread `OC-Saved` so it is not processed again

### 3. Docsumo processes the PDF
Docsumo extracts structured fields from the OC:
- VS Order Number (PO number, e.g. P01775)
- Supplier Order Number
- Supplier company name
- Line items: article ID, quantity, unit price, total, grade, thickness, width, length, coating

Document starts with status `new`, moves to `reviewing` within a few minutes. It stays in `reviewing` permanently (nobody approves OCs in Docsumo).

### 4. GitHub Actions (runs every 3 hours on weekdays)
Schedule: 8:30, 11:30, 14:30, 17:30 CET/CEST (Mon–Fri)
File: `.github/workflows/check-ocs.yml`
Can also be triggered manually from GitHub Actions UI.

Steps:
- Checks out the repo
- Installs Python dependencies
- Runs `oc_checker/run_oc_check.py`
- Commits updated `processed_ocs.json` back to the repo

### 5. run_oc_check.py
File: `oc_checker/run_oc_check.py`

- Loads `processed_ocs.json` — list of Docsumo doc IDs already processed
- Calls Docsumo API to list the 20 most recent documents with `status=reviewing`
- Skips any already in `processed_ocs.json`
- For each new document:
  1. Fetches extracted data from Docsumo
  2. Finds the matching PO in Odoo using the VS Order Number
  3. Fetches PO lines from Odoo
  4. Finds the linked Sale Order (SO) and its lines
  5. Compares OC fields against PO/SO fields
  6. Posts result to Slack
  7. Adds doc ID to `processed_ocs.json`
- Saves updated `processed_ocs.json`

### 6. Field comparison
File: `oc_checker/compare_fields.py`

Matches each OC line to a PO line using the supplier article number (`original_supplier_article` field in Odoo). Then uses the matched PO line's VS article ID to find the corresponding SO line.

Fields compared per line:
- Quantity (tolerance: ±0.5%)
- Unit price (tolerance: ±1.0%)
- Thickness (tolerance: ±0.05mm)
- Width (tolerance: ±5mm)
- Length (tolerance: ±10mm)
- Grade, coating, form, finish, quality, no. of items, tensile strength, description

Fields not extracted by Docsumo are marked `skip` (not mismatch). Score is calculated only over fields that were actually verified.

### 7. Slack message
File: `oc_checker/post_slack.py`

One message per OC. Format:
- ✅ MATCH or ❌ MISMATCH header with PO number, SO number, supplier name, buyer
- Per line item: article ID, score (e.g. 8/9 fields match)
- Per field: ✅ field: value (if match) or ❌ field: Odoo value vs OC value (if mismatch)

---

## Deduplication
`processed_ocs.json` (committed to the GitHub repo) stores all Docsumo doc IDs that have been processed. Since OCs stay in `reviewing` status permanently in Docsumo, this log is the only mechanism that prevents the same OC from being processed twice.

---

## Credentials
All secrets are stored as GitHub Actions Secrets:
- `DOCSUMO_API_KEY`
- `DOCSUMO_DOC_TYPE_ID` — `others__vNgOt`
- `ODOO_URL` — `https://erp.ops.vanillasteel.com`
- `ODOO_DB` — `vanillasteel-main-22503126`
- `ODOO_USERNAME` — `mridul.goel@vanillasteel.com`
- `ODOO_API_KEY`
- `SLACK_WEBHOOK_URL`

Docsumo API key and doc type ID are also stored as Google Apps Script Properties for the upload script.

Odoo connection uses XML-RPC (`/xmlrpc/2/`). JSON-RPC returns 503 on this instance.

---

## File structure
```
oc-checker/
├── .github/workflows/
│   └── check-ocs.yml          # GitHub Actions workflow
├── oc_checker/
│   ├── run_oc_check.py        # Main entry point
│   ├── docsumo_client.py      # Docsumo API: list + fetch + parse
│   ├── odoo_client.py         # Odoo XML-RPC: find PO, SO, lines
│   ├── compare_fields.py      # Field comparison logic
│   └── post_slack.py          # Slack message formatter + sender
├── google_apps_script/
│   └── saveOCsToDrive.js      # Gmail monitor + Docsumo uploader
├── processed_ocs.json         # Tracks already-processed Docsumo doc IDs
└── requirements.txt
```
