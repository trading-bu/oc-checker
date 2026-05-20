"""
Main OC checker — runs in GitHub Actions.

Flow:
  1. Ask Docsumo for recently processed OC documents
  2. Skip any already in processed_ocs.json
  3. For each new document: fetch extracted data, find PO in Odoo,
     compare fields, post result to Slack
  4. Save updated processed_ocs.json (committed back to repo by workflow)

Environment variables (set as GitHub Secrets):
  DOCSUMO_API_KEY       — Docsumo API key
  DOCSUMO_DOC_TYPE_ID   — others__vNgOt
  ODOO_URL              — https://erp.ops.vanillasteel.com
  ODOO_DB               — vanillasteel-main-22503126
  ODOO_USERNAME         — mridul.goel@vanillasteel.com
  ODOO_API_KEY          — Odoo API key
  SLACK_WEBHOOK_URL     — Slack incoming webhook URL
"""

import os
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import docsumo_client
import odoo_client
import compare_fields
import post_slack


PROCESSED_LOG = Path(__file__).parent.parent / "processed_ocs.json"


def load_processed() -> set:
    if PROCESSED_LOG.exists():
        return set(json.loads(PROCESSED_LOG.read_text()).get("processed_ids", []))
    return set()


def save_processed(ids: set):
    PROCESSED_LOG.write_text(json.dumps({"processed_ids": sorted(ids)}, indent=2))


def get_odoo_cfg() -> dict:
    return {
        "url":      os.environ.get("ODOO_URL",      "https://erp.ops.vanillasteel.com"),
        "database": os.environ.get("ODOO_DB",       "vanillasteel-main-22503126"),
        "username": os.environ.get("ODOO_USERNAME", "mridul.goel@vanillasteel.com"),
        "api_key":  os.environ.get("ODOO_API_KEY",  ""),
    }


def process_one(doc: dict, odoo_cfg: dict, slack_webhook: str) -> bool:
    doc_id   = doc["id"]
    filename = doc.get("title") or doc_id

    print(f"\n{'='*60}")
    print(f"Processing: {filename}  (Docsumo ID: {doc_id})")
    print(f"{'='*60}")

    # 1. Fetch extracted data from Docsumo
    try:
        raw     = docsumo_client.fetch_document_data(doc_id)
        oc_data = docsumo_client.parse_oc_data(raw, doc_id)
    except Exception as e:
        print(f"  ERROR fetching from Docsumo: {e}")
        post_slack.post_text(slack_webhook,
            f"❌ *OC Check Error*\nCould not fetch `{filename}` from Docsumo: {e}")
        return False

    po_number = oc_data.get("po_number")
    if not po_number:
        print("  WARNING: No PO number extracted. Skipping.")
        post_slack.post_text(slack_webhook,
            f"⚠️ *OC Check Warning*\n`{filename}` — could not extract VS PO number. Check manually.")
        return False

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
        post_slack.post_text(slack_webhook, f"❌ *OC Check Error*\nOdoo connection failed: {e}")
        return False

    if not pos:
        print(f"  No Odoo PO found matching '{po_number}'")
        post_slack.post_text(slack_webhook,
            f"⚠️ *OC Check Warning*\n`{filename}` — PO `{po_number}` not found in Odoo.")
        return False

    po = pos[0]
    print(f"  Matched Odoo PO: {po['name']} | {(po['partner_id'] or ['',''])[1]}")

    # 3. Fetch PO lines + linked SO
    po_lines = odoo_client.get_po_lines(models, o["database"], uid, o["api_key"], po["id"])
    so       = odoo_client.get_linked_sale_order(models, o["database"], uid, o["api_key"], po_lines)
    so_lines = []
    if so:
        so_lines = odoo_client.get_so_lines(models, o["database"], uid, o["api_key"], so["id"])
        print(f"  Linked SO: {so['name']}")

    # 4. Compare and post to Slack
    default_cfg = {"comparison": {
            "quantity_tolerance_pct": 0.5, "price_tolerance_pct": 1.0,
            "total_tolerance_pct": 2.0, "thickness_tolerance_mm": 0.05,
            "width_tolerance_mm": 5.0, "length_tolerance_mm": 10.0,
            "tensile_strength_tolerance": 0.0,
        }}
    result = compare_fields.compare(oc_data, po, po_lines, so, so_lines, default_cfg)
    post_slack.post_oc_result(slack_webhook, result, filename)
    print(f"  Slack: {'✅ MATCH' if result['is_match'] else '❌ MISMATCH'}")
    return True


def main():
    print("OC Checker starting...")

    odoo_cfg      = get_odoo_cfg()
    slack_webhook = os.environ.get("SLACK_WEBHOOK_URL", "")

    if not odoo_cfg["api_key"]:
        print("ERROR: ODOO_API_KEY not set.")
        sys.exit(1)
    if not slack_webhook:
        print("ERROR: SLACK_WEBHOOK_URL not set.")
        sys.exit(1)

    processed_ids = load_processed()
    print(f"Already processed: {len(processed_ids)} document(s)")

    # Get recent documents from Docsumo
    try:
        all_docs = docsumo_client.list_recent_documents(limit=50)
    except Exception as e:
        print(f"ERROR listing Docsumo documents: {e}")
        post_slack.post_text(slack_webhook, f"❌ *OC Check Error*\nCould not list Docsumo documents: {e}")
        sys.exit(1)

    new_docs = [d for d in all_docs if d["id"] not in processed_ids]
    print(f"New documents to process: {len(new_docs)}")

    if not new_docs:
        print("Nothing new. Done.")
        sys.exit(0)

    any_error = False
    for doc in new_docs:
        ok = process_one(doc, odoo_cfg, slack_webhook)
        processed_ids.add(doc["id"])
        if not ok:
            any_error = True

    save_processed(processed_ids)
    print(f"\nDone. Processed {len(new_docs)} document(s).")

    if any_error:
        sys.exit(1)


if __name__ == "__main__":
    main()
