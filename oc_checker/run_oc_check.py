"""
Main OC checker — runs in GitHub Actions.

Flow:
  1. List new PDF files in Google Drive "OC Inbox" folder
  2. Skip any already in processed_ocs.json
  3. For each new PDF:
     a. Download from Drive and extract fields via Claude API
     b. Find the matching PO in Odoo
     c. On first OC for this PO: seed the log with ALL Odoo line items as 'pending'
     d. Compare OC vs Odoo → update matched VSI IDs to 'confirmed' or 'mismatch'
     e. Move PDF to "OC Processed" folder in Drive
  4. Post ONE Slack message per PO showing the FULL picture:
       ⏳ 3/10 confirmed — 7 still pending (Day 1)
       ⏳ 6/10 confirmed — 4 still pending (Day 2)
       ✅ All 10 confirmed (Day 3)
  5. Persist updated processed_ocs.json (committed back by workflow)

Environment variables (set as GitHub Secrets):
  ANTHROPIC_API_KEY     — Anthropic API key (for Claude PDF extraction)
  GOOGLE_CREDENTIALS    — Google OAuth2 credentials JSON (for Drive access)
  ODOO_URL              — https://erp.ops.vanillasteel.com
  ODOO_DB               — vanillasteel-main-22503126
  ODOO_USERNAME         — mridul.goel@vanillasteel.com
  ODOO_API_KEY          — Odoo API key
  SLACK_WEBHOOK_URL     — Slack incoming webhook URL
  SLACK_BOT_TOKEN       — Slack bot token (for threading)
  SLACK_CHANNEL_ID      — Slack channel ID
"""

import os
import sys
import json
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import drive_client
import extractor
import odoo_client
import compare_fields
import post_slack


PROCESSED_LOG = Path(__file__).parent.parent / "processed_ocs.json"


# ---------------------------------------------------------------------------
# State helpers — read-modify-write so processed_ids and po_oc_log
# never clobber each other.
# ---------------------------------------------------------------------------

def load_state() -> dict:
    """Load full state from processed_ocs.json. Returns {} if file missing."""
    if PROCESSED_LOG.exists():
        try:
            return json.loads(PROCESSED_LOG.read_text())
        except Exception:
            return {}
    return {}


def save_state(state: dict):
    """Write full state to processed_ocs.json."""
    PROCESSED_LOG.write_text(json.dumps(state, indent=2))


def get_processed_ids(state: dict) -> set:
    return set(state.get("processed_ids", []))


def mark_processed(state: dict, doc_id: str) -> dict:
    ids = get_processed_ids(state)
    ids.add(doc_id)
    state["processed_ids"] = sorted(ids)
    return state


# ---------------------------------------------------------------------------
# PO line-item log helpers
# ---------------------------------------------------------------------------

def _vs_id_from_po_line(po_line: dict) -> str:
    """
    Extract the best available VS identifier from a PO line.
    Priority: vs_article → aoo_fast_number → line_{id}
    """
    vs = str(po_line.get("vs_article") or "").strip()
    if vs:
        return vs
    aoo = str(po_line.get("aoo_fast_number") or "").strip()
    if aoo:
        return aoo
    line_id = po_line.get("id")
    if line_id:
        return f"line_{line_id}"
    return ""


def initialize_po_log_if_needed(state: dict, po_name: str, po_data: dict,
                                 po_lines: list, so_data) -> dict:
    """
    Ensure state["po_oc_log"][po_name] exists with ALL VSI IDs from Odoo as
    'pending'.  If the PO was already initialized (seen on a prior run), just
    adds any new line items that may have been added to the PO since then.
    """
    po_log = state.setdefault("po_oc_log", {})
    today  = date.today().isoformat()

    supplier = ""
    if po_data and po_data.get("partner_id"):
        p = po_data["partner_id"]
        supplier = p[1] if isinstance(p, (list, tuple)) else str(p)

    buyer   = "—"
    so_name = "—"
    if so_data:
        so_name = so_data.get("name", "—")
        if so_data.get("partner_id"):
            b = so_data["partner_id"]
            buyer = b[1] if isinstance(b, (list, tuple)) else str(b)

    if po_name not in po_log:
        # First OC for this PO — seed all lines as pending
        line_items = {}
        for pl in po_lines:
            vs_id = _vs_id_from_po_line(pl)
            if vs_id:
                line_items[vs_id] = {"status": "pending"}

        po_log[po_name] = {
            "so_name":      so_name,
            "supplier":     supplier,
            "buyer":        buyer,
            "initialized":  today,
            "last_updated": today,
            "line_items":   line_items,
            "flags":        [],
        }
        print(f"  Initialized PO log for {po_name}: {len(line_items)} line item(s)")
    else:
        # Already initialized — add any new lines that appeared since last run
        existing = set(po_log[po_name]["line_items"].keys())
        added = 0
        for pl in po_lines:
            vs_id = _vs_id_from_po_line(pl)
            if vs_id and vs_id not in existing:
                po_log[po_name]["line_items"][vs_id] = {"status": "pending"}
                added += 1
        if added:
            print(f"  Added {added} new VSI ID(s) to existing log for {po_name}")

    return state


def update_po_log_with_result(state: dict, po_name: str, result: dict,
                               filename: str) -> dict:
    """
    Update the PO log with the comparison result from one OC file.

    line_results always contains per-line data (code/qty/spec-group/positional match).
    Flags: merged into the PO-level flag list (first occurrence of each type wins).
    """
    po_entry = state["po_oc_log"][po_name]
    today    = date.today().isoformat()
    oc_ref   = result.get("oc_ref", "?")
    # The OC's own issue date (e.g. "2026-07-07"), distinct from today's processing date
    oc_date  = result.get("confirmation_date") or today

    updated = 0
    for lr in result.get("line_results", []):
        vs_id = lr.get("vs_id", "")
        if not vs_id:
            continue
        if vs_id not in po_entry["line_items"]:
            print(f"  Skipping unrecognized ID '{vs_id}' "
                  f"(not in Odoo PO log — likely a matching failure)")
            continue

        mismatches = lr.get("mismatches", 0)
        entry = {
            "status":     "confirmed" if mismatches == 0 else "mismatch",
            "oc_ref":     oc_ref,
            "oc_date":    oc_date,    # OC's own issue date (for Slack display)
            "filename":   filename,
            "date":       today,      # today's processing date
            "oc_line":    lr.get("oc_line", {}),
            "fields":     lr.get("fields", []),
            "score":      lr.get("score", 0),
            "total":      lr.get("total", 0),
            "mismatches": mismatches,
        }
        if lr.get("positional_fallback"):
            entry["match_note"] = lr.get("match_note", "positional fallback")
        po_entry["line_items"][vs_id] = entry
        updated += 1
    print(f"  Updated {updated} VSI ID(s) in PO log")

    # Merge flags — first occurrence of each type wins (dedup across OC files)
    existing_types = {f["type"] for f in po_entry.get("flags", [])}
    for flag in result.get("flags", []):
        if flag["type"] not in existing_types:
            po_entry.setdefault("flags", []).append(flag)
            existing_types.add(flag["type"])

    po_entry["last_updated"] = today
    return state


# ---------------------------------------------------------------------------
# Odoo config
# ---------------------------------------------------------------------------

def get_odoo_cfg() -> dict:
    return {
        "url":      os.environ.get("ODOO_URL",      "https://erp.ops.vanillasteel.com"),
        "database": os.environ.get("ODOO_DB",       "vanillasteel-main-22503126"),
        "username": os.environ.get("ODOO_USERNAME", "mridul.goel@vanillasteel.com"),
        "api_key":  os.environ.get("ODOO_API_KEY",  ""),
    }


# ---------------------------------------------------------------------------
# Per-document processing
# ---------------------------------------------------------------------------

def process_one(doc: dict, odoo_cfg: dict, slack_webhook: str):
    """
    Download one OC PDF from Drive, extract via Claude, compare against Odoo.

    Returns:
        (success, result, filename, po_lines, so_data, po_data)
        On hard error: (False, None, filename, [], None, None)
    """
    doc_id   = doc["id"]
    filename = doc.get("title") or doc_id

    print(f"\n{'='*60}")
    print(f"Processing: {filename}  (Drive ID: {doc_id})")
    print(f"{'='*60}")

    # 1. Download PDF from Drive and extract via Claude
    try:
        pdf_bytes = drive_client.download_pdf(doc_id)
        oc_data   = extractor.extract_oc_from_pdf(pdf_bytes, filename=filename, doc_id=doc_id)
    except Exception as e:
        print(f"  ERROR extracting OC: {e}")
        post_slack.post_text(slack_webhook,
            f"OC Check Error\nCould not extract `{filename}`: {e}")
        return False, None, filename, [], None, None

    if oc_data is None:
        print(f"  Skipping '{filename}' — identified as a VS Purchase Order, not a supplier OC.")
        return False, None, filename, [], None, None

    po_number = oc_data.get("po_number")
    if not po_number:
        print("  WARNING: No PO number extracted. Skipping.")
        post_slack.post_text(slack_webhook,
            f"OC Check Warning\n`{filename}` — could not extract VS PO number. Check manually.")
        return False, None, filename, [], None, None

    # 2. Find PO in Odoo
    try:
        o = odoo_cfg
        uid, models = odoo_client.connect(o["url"], o["database"], o["username"], o["api_key"])
        po_digits   = odoo_client.normalize_po_digits(po_number)
        pos         = odoo_client.find_purchase_orders(
                        models, o["database"], uid, o["api_key"],
                        po_digits, oc_data.get("supplier_name"))
    except Exception as e:
        print(f"  ERROR connecting to Odoo: {e}")
        post_slack.post_text(slack_webhook,
            f"OC Check Error\nOdoo connection failed: {e}")
        return False, None, filename, [], None, None

    if not pos:
        print(f"  No Odoo PO found matching '{po_number}'")
        post_slack.post_text(slack_webhook,
            f"OC Check Warning\n`{filename}` — PO `{po_number}` not found in Odoo.")
        return False, None, filename, [], None, None

    po = pos[0]
    print(f"  Matched Odoo PO: {po['name']} | {(po['partner_id'] or ['',''])[1]}")

    # 3. Fetch PO lines + linked SO
    po_lines = odoo_client.get_po_lines(models, o["database"], uid, o["api_key"], po["id"])
    # Filter out cancelled / zero-quantity lines so pattern detection and
    # positional matching only sees lines the buyer actually ordered.
    po_lines_all = po_lines
    po_lines = [pl for pl in po_lines if (pl.get("product_qty") or 0) > 0]
    if len(po_lines) < len(po_lines_all):
        print(f"  Filtered {len(po_lines_all) - len(po_lines)} zero-qty PO line(s) "
              f"({len(po_lines)} active)")
    so       = odoo_client.get_linked_sale_order(models, o["database"], uid, o["api_key"], po_lines)
    so_lines = []
    if so:
        so_lines = odoo_client.get_so_lines(models, o["database"], uid, o["api_key"], so["id"])
        print(f"  Linked SO: {so['name']}")

    shipping_address = None
    if so and so.get("partner_shipping_id"):
        shipping_address = odoo_client.get_shipping_address(
            models, o["database"], uid, o["api_key"],
            so["partner_shipping_id"]
        )

    # 4. Compare OC against Odoo
    default_cfg = {"comparison": {
            "quantity_tolerance_pct":     0.5,
            "price_tolerance_pct":        1.0,
            "total_tolerance_pct":        2.0,
            "thickness_tolerance_mm":     0.05,
            "width_tolerance_mm":         5.0,
            "length_tolerance_mm":        10.0,
            "tensile_strength_tolerance": 0.0,
        }}
    result = compare_fields.compare(
        oc_data, po, po_lines, so, so_lines, default_cfg,
        odoo_shipping_address=shipping_address
    )

    n_lines     = len(result.get("line_results", []))
    n_mismatches = result.get("total_mismatches", 0)
    print(f"  Comparison: {'MATCH' if result['is_match'] else 'MISMATCH'}  "
          f"lines={n_lines}  mismatches={n_mismatches}")

    return True, result, filename, po_lines, so, po


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("OC Checker starting...")

    odoo_cfg      = get_odoo_cfg()
    slack_webhook = os.environ.get("SLACK_WEBHOOK_URL", "")

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ERROR: ANTHROPIC_API_KEY not set.")
        sys.exit(1)
    if not os.environ.get("GOOGLE_CREDENTIALS"):
        print("ERROR: GOOGLE_CREDENTIALS not set.")
        sys.exit(1)
    if not odoo_cfg["api_key"]:
        print("ERROR: ODOO_API_KEY not set.")
        sys.exit(1)
    if not slack_webhook:
        print("ERROR: SLACK_WEBHOOK_URL not set.")
        sys.exit(1)

    slack_bot_token = os.environ.get("SLACK_BOT_TOKEN", "")
    slack_channel   = os.environ.get("SLACK_CHANNEL_ID", "")

    if slack_bot_token and slack_channel:
        print("Slack: using Bot API (threading enabled) — running auth check...")
        post_slack.check_slack_auth(slack_bot_token, slack_channel)
    else:
        print("Slack: SLACK_BOT_TOKEN/SLACK_CHANNEL_ID not set — falling back to webhook (no threading)")

    state         = load_state()
    processed_ids = get_processed_ids(state)
    print(f"Already processed: {len(processed_ids)} document(s)")

    try:
        all_docs = drive_client.list_new_pdfs()
    except Exception as e:
        print(f"ERROR listing Drive files: {e}")
        post_slack.post_text(slack_webhook,
            f"OC Check Error\nCould not list Drive inbox: {e}")
        sys.exit(1)

    new_docs = [d for d in all_docs if d["id"] not in processed_ids]
    print(f"New documents to process: {len(new_docs)}")

    if not new_docs:
        print("Nothing new. Done.")
        sys.exit(0)

    for doc in new_docs:
        success, result, filename, po_lines, so_data, po_data = process_one(
            doc, odoo_cfg, slack_webhook)

        state = mark_processed(state, doc["id"])
        save_state(state)

        try:
            drive_client.mark_processed(doc["id"])
        except Exception as e:
            print(f"  WARNING: could not move Drive file to processed folder: {e}")

        if success and result:
            po_name = result.get("po_name", "UNKNOWN")

            state = initialize_po_log_if_needed(
                state, po_name, po_data, po_lines, so_data)

            state = update_po_log_with_result(state, po_name, result, filename)
            save_state(state)

            po_log = state["po_oc_log"][po_name]
            text   = post_slack.build_po_status_text(po_name, po_log)

            if slack_bot_token and slack_channel:
                thread_ts = po_log.get("slack_ts")
                ok, ts = post_slack.post_via_api(
                    slack_bot_token, slack_channel, text, thread_ts=thread_ts)
                if ok:
                    if not thread_ts and ts:
                        state["po_oc_log"][po_name]["slack_ts"] = ts
                        save_state(state)
                else:
                    print(f"  Slack API failed for {po_name}, falling back to webhook")
                    post_slack.post_po_status_update(slack_webhook, po_name, po_log)
            else:
                post_slack.post_po_status_update(slack_webhook, po_name, po_log)

    save_state(state)
    print("\nAll done.")


if __name__ == "__main__":
    main()
