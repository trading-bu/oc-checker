"""
Main OC checker -- runs in GitHub Actions.

Flow:
  1. List new PDF files in Google Drive "OC Inbox" folder
  2. Skip any already in processed_ocs.json
  3. For each new PDF:
     a. Download from Drive and extract fields via Claude API
     b. Find the matching PO in Odoo
     c. On first OC for this PO: seed the log with ALL Odoo line items as pending
     d. Compare OC vs Odoo -> update matched VSI IDs to confirmed or mismatch
     e. Move PDF to "OC Processed" folder in Drive
  4. Post ONE Slack message per PO showing the FULL picture
  5. Persist updated processed_ocs.json (committed back by workflow)

Comparison engines:
  AI engine  (default) -- compare_ai.compare_via_claude()
    Claude receives the extracted OC JSON + Odoo expected values and performs
    the comparison semantically. Handles any supplier format, language, or
    bundle structure without code changes. Falls back to Python engine on error.
  Python engine (fallback) -- compare_fields.compare()
    Deterministic rule-based comparison. Always available as a safety net.

Environment variables (set as GitHub Secrets):
  ANTHROPIC_API_KEY      -- Anthropic API key
  GOOGLE_CREDENTIALS     -- Google OAuth2 credentials JSON
  ODOO_URL               -- https://erp.ops.vanillasteel.com
  ODOO_DB                -- vanillasteel-main-22503126
  ODOO_USERNAME          -- mridul.goel@vanillasteel.com
  ODOO_API_KEY           -- Odoo API key
  SLACK_WEBHOOK_URL      -- Slack incoming webhook URL
  SLACK_BOT_TOKEN        -- Slack bot token (for threading)
  SLACK_CHANNEL_ID       -- Slack channel ID

Optional overrides:
  USE_AI_COMPARISON      -- "false" to force Python engine
  AI_COMPARISON_MODEL    -- Claude model for comparison (default: claude-sonnet-4-6)
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
import compare_ai
import post_slack


PROCESSED_LOG = Path(__file__).parent.parent / "processed_ocs.json"


# ---------------------------------------------------------------------------
# State helpers
# ---------------------------------------------------------------------------

def load_state():
    if PROCESSED_LOG.exists():
        try:
            return json.loads(PROCESSED_LOG.read_text())
        except Exception:
            return {}
    return {}


def save_state(state):
    PROCESSED_LOG.write_text(json.dumps(state, indent=2))


def get_processed_ids(state):
    return set(state.get("processed_ids", []))


def mark_processed(state, doc_id):
    ids = get_processed_ids(state)
    ids.add(doc_id)
    state["processed_ids"] = sorted(ids)
    return state


# ---------------------------------------------------------------------------
# PO line-item log helpers
# ---------------------------------------------------------------------------

def _vs_id_from_po_line(po_line):
    vs = str(po_line.get("vs_article") or "").strip()
    if vs:
        return vs
    aoo = str(po_line.get("aoo_fast_number") or "").strip()
    if aoo:
        return aoo
    line_id = po_line.get("id")
    if line_id:
        return "line_%s" % line_id
    return ""


def initialize_po_log_if_needed(state, po_name, po_data, po_lines, so_data):
    po_log = state.setdefault("po_oc_log", {})
    today  = date.today().isoformat()

    supplier = ""
    if po_data and po_data.get("partner_id"):
        p = po_data["partner_id"]
        supplier = p[1] if isinstance(p, (list, tuple)) else str(p)

    buyer   = "---"
    so_name = "---"
    if so_data:
        so_name = so_data.get("name", "---")
        if so_data.get("partner_id"):
            b = so_data["partner_id"]
            buyer = b[1] if isinstance(b, (list, tuple)) else str(b)

    if po_name not in po_log:
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
        print("  Initialized PO log for %s: %d line item(s)" % (po_name, len(line_items)))
    else:
        existing = set(po_log[po_name]["line_items"].keys())
        added = 0
        for pl in po_lines:
            vs_id = _vs_id_from_po_line(pl)
            if vs_id and vs_id not in existing:
                po_log[po_name]["line_items"][vs_id] = {"status": "pending"}
                added += 1
        if added:
            print("  Added %d new VSI ID(s) to existing log for %s" % (added, po_name))

    return state


def update_po_log_with_result(state, po_name, result, filename):
    """
    Update PO log with comparison result.
    Stores comparison_engine per line for audit trail.
    """
    po_entry = state["po_oc_log"][po_name]
    today    = date.today().isoformat()
    oc_ref   = result.get("oc_ref", "?")
    oc_date  = result.get("confirmation_date") or today
    engine   = result.get("comparison_engine", "python")

    updated = 0
    for lr in result.get("line_results", []):
        vs_id = lr.get("vs_id", "")
        if not vs_id:
            continue
        if vs_id not in po_entry["line_items"]:
            print("  Skipping unrecognized ID '%s' (not in Odoo PO log)" % vs_id)
            continue

        mismatches = lr.get("mismatches", 0)
        new_status = "confirmed" if (mismatches == 0 and lr.get("score", 0) > 0) else ("mismatch" if mismatches > 0 else "pending")

        # Never downgrade confirmed/mismatch → pending.
        # The AI comparison returns ALL Odoo PO lines (even ones not in the current OC).
        # Unmatched lines come back with score=0, mismatches=0 → would be "pending".
        # Silently skip those so previously confirmed/mismatched lines aren't overwritten.
        existing_status = po_entry["line_items"].get(vs_id, {}).get("status", "pending")
        if new_status == "pending" and existing_status in ("confirmed", "mismatch"):
            continue

        entry = {
            "status":            new_status,
            "oc_ref":            oc_ref,
            "oc_date":           oc_date,
            "filename":          filename,
            "date":              today,
            "oc_line":           lr.get("oc_line", {}),
            "fields":            lr.get("fields", []),
            "score":             lr.get("score", 0),
            "total":             lr.get("total", 0),
            "mismatches":        mismatches,
            "comparison_engine": engine,
        }
        if lr.get("positional_fallback"):
            entry["match_note"] = lr.get("match_note", "positional fallback")
        po_entry["line_items"][vs_id] = entry
        updated += 1

    print("  Updated %d VSI ID(s) in PO log  [engine=%s]" % (updated, engine))

    existing_types = {f["type"] for f in po_entry.get("flags", [])}
    for flag in result.get("flags", []):
        if flag["type"] not in existing_types:
            po_entry.setdefault("flags", []).append(flag)
            existing_types.add(flag["type"])

    # Store supplier notes from this OC (overwrite with latest run's notes)
    oc_data = result.get("oc_data", {})
    notes = oc_data.get("supplier_notes", [])
    if isinstance(notes, list) and notes:
        po_entry["supplier_notes"] = notes
    elif "supplier_notes" not in po_entry:
        po_entry["supplier_notes"] = []

    po_entry["last_updated"] = today
    return state


# ---------------------------------------------------------------------------
# Comparison engine dispatcher
# ---------------------------------------------------------------------------

def _run_comparison(oc_data, po_data, po_lines, so_data, so_lines, cfg,
                    shipping_address):
    """
    Dispatch to AI or Python comparison engine.

    AI engine: compare_ai.compare_via_claude()
      Claude performs semantic comparison of OC JSON vs Odoo expected values.
      Handles any supplier format without code changes.

    Python engine (fallback): compare_fields.compare()
      Deterministic rule-based comparison. Used when use_ai_comparison=False,
      or automatically if AI engine raises an exception.

    Adds 'comparison_engine' key ("ai" or "python") to the returned result.
    """
    use_ai = cfg.get("use_ai_comparison", True)

    if use_ai:
        try:
            result = compare_ai.compare_via_claude(
                oc_data, po_data, po_lines, so_data, so_lines, cfg,
                odoo_shipping_address=shipping_address,
            )
            result["comparison_engine"] = "ai"
            return result
        except Exception as e:
            print("  [AI compare] FAILED: %s: %s" % (type(e).__name__, e))
            print("  [AI compare] Falling back to Python comparison engine...")

    result = compare_fields.compare(
        oc_data, po_data, po_lines, so_data, so_lines, cfg,
        odoo_shipping_address=shipping_address,
    )
    result["comparison_engine"] = "python"
    return result


# ---------------------------------------------------------------------------
# Odoo config
# ---------------------------------------------------------------------------

def get_odoo_cfg():
    return {
        "url":      os.environ.get("ODOO_URL",      "https://erp.ops.vanillasteel.com"),
        "database": os.environ.get("ODOO_DB",       "vanillasteel-main-22503126"),
        "username": os.environ.get("ODOO_USERNAME", "mridul.goel@vanillasteel.com"),
        "api_key":  os.environ.get("ODOO_API_KEY",  ""),
    }


# ---------------------------------------------------------------------------
# Per-document processing
# ---------------------------------------------------------------------------

def process_one(doc, odoo_cfg, slack_webhook):
    """
    Download one OC PDF from Drive, extract via Claude, compare against Odoo.
    Returns (success, result, filename, po_lines, so_data, po_data).
    On hard error returns (False, None, filename, [], None, None).
    """
    doc_id   = doc["id"]
    filename = doc.get("title") or doc_id

    print("")
    print("=" * 60)
    print("Processing: %s  (Drive ID: %s)" % (filename, doc_id))
    print("=" * 60)

    # Step 1: Download PDF and extract OC data via Claude
    try:
        pdf_bytes = drive_client.download_pdf(doc_id)
        oc_data   = extractor.extract_oc_from_pdf(pdf_bytes, filename=filename, doc_id=doc_id)
    except Exception as e:
        print("  ERROR extracting OC: %s" % e)
        post_slack.post_text(slack_webhook,
            "OC Check Error\nCould not extract `%s`: %s" % (filename, e))
        return False, None, filename, [], None, None

    if oc_data is None:
        print("  Skipping '%s' -- identified as VS Purchase Order, not supplier OC." % filename)
        return False, None, filename, [], None, None

    po_number = oc_data.get("po_number")

    # Step 2: Find matching PO in Odoo
    # Primary path : match by PO number (already extracted from OC)
    # Fallback path: if no PO number, match by supplier name + total OC weight
    try:
        o = odoo_cfg
        uid, models = odoo_client.connect(o["url"], o["database"], o["username"], o["api_key"])

        if po_number:
            po_digits = odoo_client.normalize_po_digits(po_number)
            pos = odoo_client.find_purchase_orders(
                    models, o["database"], uid, o["api_key"],
                    po_digits, oc_data.get("supplier_name"))
        else:
            # No PO number in OC — try supplier name + total weight fallback
            print("  No PO number found -- trying supplier+weight fallback...")
            oc_lines  = oc_data.get("lines", [])
            oc_total  = sum(float(l.get("quantity") or 0) for l in oc_lines)
            supplier  = oc_data.get("supplier_name") or ""
            print("  [debug] supplier_name=%r  oc_lines=%d  oc_total=%s" % (
                supplier, len(oc_lines), oc_total))
            if supplier and oc_total > 0:
                matched = odoo_client.find_po_by_supplier_and_weight(
                    models, o["database"], uid, o["api_key"], supplier, oc_total)
                pos = [matched] if matched else []
            else:
                if not supplier:
                    print("  [debug] skipping fallback: supplier_name is empty")
                if not oc_total:
                    print("  [debug] skipping fallback: oc_total is 0 (quantities not extracted)")
                pos = []

    except Exception as e:
        print("  ERROR connecting to Odoo: %s" % e)
        post_slack.post_text(slack_webhook, "OC Check Error\nOdoo connection failed: %s" % e)
        return False, None, filename, [], None, None

    if not pos:
        if po_number:
            print("  No Odoo PO found matching '%s'" % po_number)
            post_slack.post_text(slack_webhook,
                "OC Check Warning\n`%s` -- PO `%s` not found in Odoo." % (filename, po_number))
        else:
            supplier = oc_data.get("supplier_name") or "unknown supplier"
            print("  No PO found via supplier+weight fallback (%s)" % supplier)
            post_slack.post_text(slack_webhook,
                ("OC Check Warning\n`%s` -- no PO number found and supplier+weight"
                 " fallback failed (%s). Check manually.") % (filename, supplier))
        return False, None, filename, [], None, None

    po          = pos[0]
    po_supplier = (po["partner_id"] or ["", ""])[1]
    print("  Matched Odoo PO: %s | %s" % (po["name"], po_supplier))

    # Step 3: Fetch PO lines and linked SO
    po_lines     = odoo_client.get_po_lines(models, o["database"], uid, o["api_key"], po["id"])
    po_lines_all = po_lines
    po_lines     = [pl for pl in po_lines if (pl.get("product_qty") or 0) > 0]
    if len(po_lines) < len(po_lines_all):
        print("  Filtered %d zero-qty PO line(s) (%d active)" % (
            len(po_lines_all) - len(po_lines), len(po_lines)))

    so       = odoo_client.get_linked_sale_order(models, o["database"], uid, o["api_key"], po_lines)
    so_lines = []
    if so:
        so_lines = odoo_client.get_so_lines(models, o["database"], uid, o["api_key"], so["id"])
        print("  Linked SO: %s" % so["name"])

    # product_address_id is a VS-specific field on PO lines = supplier pickup address.
    # Take the first non-null value across lines.
    shipping_address = None
    shipping_partner_id = None
    for pl in po_lines:
        if pl.get("product_address_id"):
            shipping_partner_id = pl["product_address_id"]
            break
    if shipping_partner_id:
        shipping_address = odoo_client.get_shipping_address(
            models, o["database"], uid, o["api_key"], shipping_partner_id)

    # Step 4: Compare OC against Odoo
    # USE_AI_COMPARISON env var: "false" forces Python engine
    # AI_COMPARISON_MODEL env var: override Claude model (default: claude-sonnet-4-6)
    cfg = {
        "comparison": {
            "quantity_tolerance_pct":     0.5,
            "price_tolerance_pct":        1.0,
            "total_tolerance_pct":        2.0,
            "thickness_tolerance_mm":     0.05,
            "width_tolerance_mm":         5.0,
            "length_tolerance_mm":        10.0,
            "tensile_strength_tolerance": 0.0,
        },
        "use_ai_comparison":   os.environ.get("USE_AI_COMPARISON",   "true").lower() != "false",
        "ai_comparison_model": os.environ.get("AI_COMPARISON_MODEL", "claude-sonnet-4-6"),
    }

    result   = _run_comparison(oc_data, po, po_lines, so, so_lines, cfg, shipping_address)
    engine   = result.get("comparison_engine", "?")
    outcome  = "MATCH" if result["is_match"] else "MISMATCH"
    n_lines  = len(result.get("line_results", []))
    n_mm     = result.get("total_mismatches", 0)
    print("  Comparison: %s  engine=%s  lines=%d  mismatches=%d" % (outcome, engine, n_lines, n_mm))

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
        print("Slack: using Bot API (threading enabled) -- running auth check...")
        post_slack.check_slack_auth(slack_bot_token, slack_channel)
    else:
        print("Slack: SLACK_BOT_TOKEN/SLACK_CHANNEL_ID not set -- falling back to webhook")

    use_ai = os.environ.get("USE_AI_COMPARISON", "true").lower() != "false"
    model  = os.environ.get("AI_COMPARISON_MODEL", "claude-sonnet-4-6")
    if use_ai:
        print("Comparison engine: AI (%s) with Python fallback" % model)
    else:
        print("Comparison engine: Python only (USE_AI_COMPARISON=false)")

    state         = load_state()
    processed_ids = get_processed_ids(state)
    print("Already processed: %d document(s)" % len(processed_ids))

    try:
        all_docs = drive_client.list_new_pdfs()
    except Exception as e:
        print("ERROR listing Drive files: %s" % e)
        post_slack.post_text(slack_webhook, "OC Check Error\nCould not list Drive inbox: %s" % e)
        sys.exit(1)

    new_docs = [d for d in all_docs if d["id"] not in processed_ids]
    print("New documents to process: %d" % len(new_docs))

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
            print("  WARNING: could not move Drive file to processed folder: %s" % e)

        if success and result:
            po_name = result.get("po_name", "UNKNOWN")

            state = initialize_po_log_if_needed(state, po_name, po_data, po_lines, so_data)
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
                    print("  Slack API failed for %s, falling back to webhook" % po_name)
                    post_slack.post_po_status_update(slack_webhook, po_name, po_log)
            else:
                post_slack.post_po_status_update(slack_webhook, po_name, po_log)

    save_state(state)
    print("")
    print("All done.")


if __name__ == "__main__":
    main()
