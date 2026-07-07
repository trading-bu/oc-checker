# OC Checker — Master Plan

> **How to use this file:** At the start of every new Claude session, say:
> *"Read PLAN.md and the files listed under Current Stage, then continue."*
> Update the Current Stage section at the end of each session.

---

## What This System Does

Vanilla Steel receives Order Confirmations (OCs) from suppliers as PDFs.
This system checks each OC against the matching Purchase Order (PO) and Sales Order (SO) in Odoo,
posts a status to Slack, and — eventually — generates a buyer-facing confirmation PDF.

**Full flow (current architecture):**
1. Supplier emails OC PDF → Gmail filters by keyword → Google Apps Script saves to Google Drive "OC Inbox"
2. GitHub Actions (every 3h Mon–Fri) runs Python: reads unprocessed PDFs from Drive
3. Python sends PDF bytes to Claude API (`claude-sonnet-4-6`) → structured JSON extracted
4. Extracted data compared against Odoo PO line items and SO
5. Match/mismatch status posted to Slack (threaded by PO)
6. Processed PDF moved to "OC Processed" folder in Drive
7. When all items confirmed → (Stage 5) generates buyer confirmation PDF

---

## Repo Structure

```
oc-checker/
├── oc_checker/
│   ├── run_oc_check.py        # Main entry point (GitHub Actions runs this)
│   ├── extractor.py           # Claude API PDF extraction (replaced docsumo_client)
│   ├── drive_client.py        # Google Drive inbox/processed folder management
│   ├── odoo_client.py         # Connects to Odoo, fetches PO/SO data
│   ├── compare_fields.py      # Compares OC fields against Odoo fields
│   └── post_slack.py          # Posts to Slack (webhook fallback + Bot API threading)
├── google_apps_script/
│   └── saveOCsToDrive.js      # Gmail → Drive (no Docsumo; Claude handles extraction)
├── processed_ocs.json         # State file: processed Drive file IDs + per-PO log
├── requirements.txt           # anthropic, google-auth, google-api-python-client
├── setup_google_auth.py       # ONE-TIME: run locally to generate GOOGLE_CREDENTIALS JSON
├── .github/workflows/
│   └── check-ocs.yml          # Runs every 3h Mon–Fri, also manual trigger
├── PLAN.md                    # This file
└── WORKFLOW.md                # Business workflow notes
```

---

## GitHub Actions Secrets Required

| Secret | Purpose |
|--------|---------|
| `ANTHROPIC_API_KEY` | Claude API for PDF extraction (get from console.anthropic.com) |
| `GOOGLE_CREDENTIALS` | Full OAuth2 JSON from `setup_google_auth.py` (one-time setup) |
| `ODOO_URL` | `https://erp.ops.vanillasteel.com` |
| `ODOO_DB` | `vanillasteel-main-22503126` |
| `ODOO_USERNAME` | `mridul.goel@vanillasteel.com` |
| `ODOO_API_KEY` | Odoo API key |
| `SLACK_WEBHOOK_URL` | Fallback webhook (always needed) |
| `SLACK_BOT_TOKEN` | Bot token for threading (`xoxb-...`) |
| `SLACK_CHANNEL_ID` | Slack channel for OC updates |

> **Removed secrets** (no longer needed): `DOCSUMO_API_KEY`, `DOCSUMO_DOC_TYPE_ID`

---

## One-Time Google OAuth Setup

Before the system can read from Google Drive, you need to generate a `GOOGLE_CREDENTIALS` secret once:

1. Go to [console.cloud.google.com](https://console.cloud.google.com/)
2. Create or select a project
3. Enable **Google Drive API** (APIs & Services → Library)
4. APIs & Services → Credentials → **Create Credentials → OAuth 2.0 Client ID**
5. Application type: **Desktop app** → Download the JSON → rename it `client_secret.json`
6. Place `client_secret.json` in the repo root
7. Run: `pip install google-auth-oauthlib google-api-python-client`
8. Run: `python setup_google_auth.py`
9. Sign in via the browser window that opens
10. Copy the full content of the generated `credentials.json`
11. GitHub repo → Settings → Secrets → New secret → name: `GOOGLE_CREDENTIALS` → paste content
12. Delete `client_secret.json` and `credentials.json` from the repo (don't commit them)

---

## Key Technical Decisions (Already Made)

- **Claude API for extraction**: PDF bytes sent as base64 `type: "document"` with header
  `anthropic-beta: pdfs-2024-09-25`. Model `claude-sonnet-4-6`. No Docsumo.
- **Drive auth**: Raw urllib calls using refresh_token — no google-auth library at runtime
  despite it being in requirements.txt (there for potential future use). `_Token` class in
  `drive_client.py` handles token refresh transparently.
- **Slack threading**: First OC for a PO creates a parent message (`slack_ts` stored in state).
  Subsequent OCs for the same PO reply in that thread.
- **State file**: `processed_ocs.json` has two sections:
  - `processed_ids`: flat list of Drive file IDs already processed (skip on next run)
  - `po_oc_log`: per-PO accumulation of line item statuses + `slack_ts`
- **GitHub Actions commits state back**: the workflow git-adds `processed_ocs.json` after each run
- **Slack bot scopes needed**: `chat:write` + `chat:write.public` (bot must be invited to channel)

---

## Known Gotchas (Read Before Touching Anything)

1. **Windows file locking on `processed_ocs.json`**: GitHub Desktop holds a git index lock.
   Always close GitHub Desktop before running `git add / commit / push` from terminal.
   If you see `index.lock exists`, run: `del "C:\Users\MridulGoel\Documents\GitHub\oc-checker\.git\index.lock"`

2. **Never use Claude's Edit tool on files in this repo from a Windows Cowork session.**
   The Edit tool truncates files mid-line on Windows mounts.
   Always modify files via bash Python scripts (`python3 -c "..."` or a temp script).

3. **`processed_ocs.json` is not gitignored** — it must be committed and pushed.
   If it gets deleted from GitHub (to resolve conflicts), rebuild from the last known-good commit:
   `git show <commit_hash>:processed_ocs.json > processed_ocs.json`

4. **Drive file IDs vs old Docsumo IDs**: `processed_ids` in the state file may contain old
   Docsumo IDs (format: short alphanumeric strings) alongside new Drive file IDs
   (format: long alphanumeric strings like `1BxiMVs0...`). These don't clash.
   Old Docsumo IDs are harmless — they'll never match a Drive file ID.

5. **VS's own POs getting processed as OCs (P01814, P01821 affected)**: When VS forwards
   its own PO PDF internally, the Apps Script may pick it up as an OC. The `po_oc_log`
   entries for these POs may have circular "confirmed" statuses with no real supplier data.
   These entries need to be manually invalidated and re-processed once the real OC arrives.

6. **European number format in extraction**: Claude prompt explicitly handles:
   - `3,0` → `3.0` (decimal comma → decimal point)
   - `1.586` → `1586.0` (thousands separator in weights)
   - Coil reference = actual article ID (e.g. `VSI-1234`), NOT sequential line numbers (1, 2, 3)

---

## The Staged Plan

### Stage 1 — Extraction Audit ✅ DONE (2026-07-06)
**Result**: 93.75% accuracy on gate fields (qty, price, dims) across 10 OCs / 6 supplier formats.
Gate PASSED. See `STAGE1_AUDIT.md` for full per-PDF results and identified bugs.

**3 bugs found** (fixed in Stage 3):
- Page-break spec shift → false mismatches (P01791)
- Thousands-separator qty misparse → false mismatch (P01811, Bilstein 212618)
- VS own POs processed as OCs → circular "confirmed" (P01814, P01821)

---

### Stage 2 — Extraction Rebuild ⏭️ SUPERSEDED
**Original plan**: If Stage 1 audit failed (< 85%), rebuild extractor.

**What actually happened**: Regardless of the audit result, decision was made to replace
Docsumo entirely with Claude API (architectural decision — better accuracy, one less paid service,
handles all supplier formats natively). This work is complete:

- `oc_checker/extractor.py` — NEW: takes PDF bytes, calls Claude API, returns structured JSON
- `oc_checker/drive_client.py` — NEW: reads from Google Drive "OC Inbox", moves to "OC Processed"
- `oc_checker/run_oc_check.py` — MODIFIED: uses drive_client + extractor instead of docsumo_client
- `google_apps_script/saveOCsToDrive.js` — MODIFIED: Docsumo upload removed (Drive-only now)
- `.github/workflows/check-ocs.yml` — MODIFIED: new secrets (ANTHROPIC_API_KEY, GOOGLE_CREDENTIALS)
- `requirements.txt` — MODIFIED: anthropic, google-auth, google-api-python-client
- `setup_google_auth.py` — NEW: one-time OAuth flow helper

**Before the system runs end-to-end, the Google OAuth setup (above) must be completed.**

---

### Stage 3 — Comparison Logic Overhaul ← CURRENT
**Goal**: Accurate per-line confirmed/mismatch/pending verdicts.

**Known issues to fix** (from Stage 1 audit + new architecture):
1. **Doc-type guard**: reject VS's own PO PDFs before extraction (check doc structure or filename)
2. **Arithmetic self-check**: verify `qty × unit_price ≈ total_amount` inside extractor;
   flag extraction as unreliable if it doesn't balance
3. **Null-as-pending**: missing OC field should show as `⚠️ not provided` not `❌ mismatch`
4. **Page-break spec shift**: multi-page OCs where item spec continues on next page
5. **Thousands-separator qty**: `1.586` → `1586.0` MT (European format) — patch in extractor
6. **Delivery date extraction**: currently missing or inconsistent
7. **Multi-coil line items**: one OC line covering multiple Odoo lines → aggregate qty comparison

**Test approach**: Build test suite with known OC + PO pairs where correct verdict is known.

**Files to modify**: `oc_checker/compare_fields.py`, `oc_checker/extractor.py`
**Files to create**: `tests/test_compare.py`
**Also**: Invalidate P01814/P01821 log entries; re-process real Risse+Wilke OC 6300167921

---

### Stage 4 — Slack Output Cleanup
**Goal**: Slack message is clear, accurate, and actionable for the team.

By this stage, data is trustworthy. Slack message just needs polish:
- Show delivery date and incoterms in the summary
- Flag pattern B/C OCs (multi-line format) more clearly
- Show which specific fields mismatched and by how much
- Threading is already working — just verify it's solid

**Files to modify**: `oc_checker/post_slack.py`

---

### Stage 5 — Buyer Confirmation PDF
**Goal**: Generate a VS-branded PDF to send to buyers once a PO is fully confirmed.

**Trigger**: All line items for a PO reach `confirmed` status.

**Content of buyer PDF**:
- VS logo + branding
- Reference to SO number (buyer's order)
- Confirmed line items: VSI ID, grade, dimensions, quantity, delivery date
- Incoterms / delivery address
- Date of confirmation

**Approach**: Python `reportlab` or `weasyprint` (HTML→PDF). Template-based.
Store generated PDFs in Google Drive (buyer confirmation folder) or email directly.

**Files to create**: `oc_checker/generate_buyer_pdf.py`
**Files to modify**: `oc_checker/run_oc_check.py` (trigger PDF generation on full confirmation)

---

### Stage 6 — Reliability & Monitoring
**Goal**: Runs unattended without human babysitting.

- Better error messages when Claude / Drive / Odoo / Slack fail
- Retry logic for transient API failures
- Alert if workflow hasn't run in 24h
- Dashboard or summary command to see overall status

---

## Current Status

| Stage | Status | Notes |
|-------|--------|-------|
| Stage 1 — Extraction Audit | ✅ Done (2026-07-06) | 93.75% on gate fields — see STAGE1_AUDIT.md |
| Stage 2 — Extraction Rebuild | ✅ Done (2026-07-06) | Docsumo replaced with Claude API + Drive |
| Stage 3 — Comparison Logic | ✅ Done (2026-07-06) | All issues resolved — see last session summary |
| Stage 4 — Slack Output | ✅ Done (2026-07-06) | Full rewrite — see last session summary |
| Stage 5 — Buyer PDF | ⬜ Not started | |
| Stage 6 — Reliability | ⬜ Not started | |

**Last session summary** (2026-07-06):
- Completed Stage 2: replaced Docsumo with Claude API (extractor.py, drive_client.py)
- Completed Stage 3: all comparison logic issues resolved:
  - Doc-type guard: extractor returns None for VS POs → run_oc_check skips silently
  - Arithmetic self-check: Claude verifies qty×price≈total per line, sets extraction_warning
  - Null-as-pending: already correct (compare returns "skip" not "mismatch" for missing OC fields)
  - Page-break spec shift: auto-fixed — was a Docsumo OCR artifact; Claude reads full PDF natively
  - Delivery date: added per-line to extractor prompt + _compare_date in compare_fields.py
    + date_planned fetched from Odoo PO lines + rendered in Slack (→ YYYY-MM-DD on confirmed lines)
  - Extraction warnings: rendered in Slack when arithmetic check flags a discrepancy
  - P01814/P01821: removed from po_oc_log (were VS own POs misidentified as OCs)
- **Before first run**: complete Google OAuth setup (see One-Time Google OAuth Setup above)
- **Next action**: Stage 5 (buyer PDF) or a real end-to-end test with a live OC PDF first.
  To test: add ANTHROPIC_API_KEY + GOOGLE_CREDENTIALS to GitHub Secrets, complete OAuth setup,
  drop an OC PDF into the Drive "OC Inbox" folder, trigger the workflow manually.

**Stage 4 — Slack output (post_slack.py) — full rewrite summary:**
- Removed dead `post_oc_result` function (was never called)
- New message structure: header → subheader (supplier→buyer | OC ref | date) → progress line
- Progress line shows incoterms/payment term mismatches inline (⚠️) — no longer buried in Part 2
- Mismatch lines: show ONLY the mismatching fields with delta (e.g. `+0.50mm`, `-€30.00`)
  — matched/skipped fields no longer listed (was very noisy)
- Removed internal "Score: X/Y verified fields" line — not user-facing
- Delivery dates shown on every confirmed line as `→ 15 Aug 2026`
- Dimensions formatted cleanly: `3×1250mm` not `3.0×1250.0mm`
- Pickup address shown as one-liner when matching: `📍 Pickup: 9011 Győr...  ✅`
- Pattern B/C warning shown near top of message, not buried after line items
- Human-readable dates throughout (`15 Aug 2026` not `2026-08-15`)
- Added `_fmt_dim`, `_fmt_date`, `_fmt_delta` helper functions with full test coverage

---

## How to Start a New Session

Paste this at the start of your next Claude/Cowork session:

> "Read `PLAN.md` in my oc-checker repo and continue from where we left off.
> The current stage is listed under 'Current Status'. Start there."

Then update the **Current Status** table and **Last session summary** at the end of each session.
