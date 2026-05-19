"""
Odoo XML-RPC client for Vanilla Steel.

IMPORTANT: This instance uses XML-RPC (/xmlrpc/2/).
JSON-RPC (/web/dataset/call_kw) returns 503 — do not use it.

Odoo version: 19 Enterprise
Instance:     https://erp.ops.vanillasteel.com
Database:     vanillasteel-main-22503126
"""

import xmlrpc.client
import json
import re
import sys
import os


# ── Connection ────────────────────────────────────────────────

def connect(url, db, login, api_key):
    """Authenticate and return (uid, models_proxy)."""
    common = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/common")
    uid = common.authenticate(db, login, api_key, {})
    if not uid:
        raise RuntimeError(
            "Odoo authentication failed. "
            "Check your URL, database, login, and api_key in config.json."
        )
    models = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/object")
    return uid, models


def search_read(models, db, uid, api_key, model, domain, fields, limit=20):
    """Thin wrapper around execute_kw search_read."""
    return models.execute_kw(
        db, uid, api_key,
        model, "search_read",
        [domain],
        {"fields": fields, "limit": limit}
    )


def read_record(models, db, uid, api_key, model, ids, fields):
    """Read specific record IDs."""
    return models.execute_kw(
        db, uid, api_key,
        model, "read",
        [ids],
        {"fields": fields}
    )


# ── PO matching ───────────────────────────────────────────────

def normalize_po_digits(raw):
    """Strip non-digit characters, preserve leading zeros.
    e.g. 'P01423' → '01423', 'PO-1423' → '1423', 'P 01423' → '01423'
    """
    digits = re.sub(r'\D', '', str(raw))
    return digits


def find_purchase_orders(models, db, uid, api_key, po_digits, supplier_name=None):
    """
    Search for POs whose name contains po_digits.
    Returns list of candidates sorted by supplier name similarity.

    Uses purchase.order with fields relevant to OC matching.
    """
    records = search_read(
        models, db, uid, api_key,
        "purchase.order",
        [
            ["name", "ilike", po_digits],
            ["state", "in", ["purchase", "done", "to approve"]]
        ],
        ["id", "name", "partner_id", "amount_total", "currency_id",
         "date_order", "date_planned", "order_line"],
        limit=10
    )

    if not records:
        return []

    # Score by supplier name similarity if provided
    if supplier_name and len(records) > 1:
        s_lower = supplier_name.lower()
        def score(rec):
            odoo_name = (rec["partner_id"][1] if rec["partner_id"] else "").lower()
            words = [w for w in s_lower.split() if len(w) > 2]
            return sum(1 for w in words if w in odoo_name)
        records = sorted(records, key=score, reverse=True)

    return records


def get_po_lines(models, db, uid, api_key, po_id):
    """
    Fetch PO line details for OC comparison.
    Includes VS-specific fields: original_supplier_article, aoo_fast_number, vs_article.
    """
    return search_read(
        models, db, uid, api_key,
        "purchase.order.line",
        [["order_id", "=", po_id]],
        [
            "id", "name", "product_id",
            "product_qty", "product_uom_id",
            "price_unit", "price_subtotal",
            # VS-specific fields
            "original_supplier_article",
            "aoo_fast_number",
            "vs_article",
            "sale_order_id",
            "sale_line_id",
        ],
        limit=50
    )


def get_linked_sale_order(models, db, uid, api_key, po_lines):
    """
    Find the Sale Order linked to PO lines.
    Uses sale_order_id field on purchase.order.line (VS-specific).
    """
    so_ids = set()
    for line in po_lines:
        if line.get("sale_order_id"):
            so_ids.add(line["sale_order_id"][0])

    if not so_ids:
        return None

    so_id = list(so_ids)[0]  # Take first if multiple (unusual)
    so_records = read_record(
        models, db, uid, api_key,
        "sale.order",
        [so_id],
        ["id", "name", "partner_id", "amount_total", "currency_id", "state", "order_line"]
    )
    return so_records[0] if so_records else None


def get_so_lines(models, db, uid, api_key, so_id):
    """
    Fetch SO line details including VS steel-specific fields.
    These fields are on sale.order.line in VS's Odoo 19 instance.

    All 13 comparison fields:
      form, choice (quality), grade, finish, coating,
      product_uom_qty (actual qty), no_of_items,
      price_unit (sale price — purchase price is on PO line),
      thickness, width, length, tensile_strength, name (description)
    """
    return search_read(
        models, db, uid, api_key,
        "sale.order.line",
        [["order_id", "=", so_id]],
        [
            "id", "name", "product_id",
            "product_uom_qty", "price_unit", "price_subtotal",
            # VS steel-specific fields — all 13 comparison fields
            "form",
            "choice",
            "grade",
            "finish",
            "coating",
            "thickness",
            "width",
            "length",
            "tensile_strength",
            "no_of_items",
            "vs_article",
        ],
        limit=50
    )


# ── Config ────────────────────────────────────────────────────

def load_config(config_path=None):
    if config_path is None:
        config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
    with open(config_path) as f:
        cfg = json.load(f)
    # Remove _instructions key if present (from template)
    cfg.pop("_instructions", None)
    return cfg


# ── Quick test ────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python odoo_client.py <po_number>")
        sys.exit(1)

    cfg = load_config()
    o = cfg["odoo"]
    print(f"Connecting to {o['url']} ...")
    uid, models = connect(o["url"], o["database"], o["username"], o["api_key"])
    print(f"✓ Authenticated (uid={uid})")

    digits = normalize_po_digits(sys.argv[1])
    print(f"\nSearching POs with digits: {digits}")
    pos = find_purchase_orders(models, o["database"], uid, o["api_key"], digits)

    if not pos:
        print("No POs found.")
        sys.exit(0)

    for po in pos:
        print(f"\n  PO: {po['name']} | Supplier: {po['partner_id'][1]} | Total: {po['amount_total']}")
        lines = get_po_lines(models, o["database"], uid, o["api_key"], po["id"])
        for l in lines:
            print(f"    Line: {l['name'][:70]}")
            print(f"      Qty: {l['product_qty']}  Price: {l['price_unit']}")
            print(f"      vs_article: {l.get('vs_article') or '—'}  aoo_fast_number: {l.get('aoo_fast_number') or '—'}")

        so = get_linked_sale_order(models, o["database"], uid, o["api_key"], lines)
        if so:
            print(f"\n  Linked SO: {so['name']} | Buyer: {so['partner_id'][1]}")
            so_lines = get_so_lines(models, o["database"], uid, o["api_key"], so["id"])
            for sl in so_lines:
                print(f"    SO Line: grade={sl.get('grade') or '—'} coating={sl.get('coating') or '—'} "
                      f"thick={sl.get('thickness') or '—'} width={sl.get('width') or '—'} "
                       f"qty={sl.get('product_uom_qty')} vs_article={sl.get('vs_article') or '—'}")
