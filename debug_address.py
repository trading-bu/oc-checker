"""
One-off debug script: checks what product_address_id returns for a PO's lines.
Run from the repo root:  python debug_address.py P01848
"""
import sys, xmlrpc.client, json
from pathlib import Path

cfg = json.loads((Path(__file__).parent / "oc_checker" / "config.json").read_text())
o = cfg["odoo"]

common = xmlrpc.client.ServerProxy("%s/xmlrpc/2/common" % o["url"])
uid    = common.authenticate(o["database"], o["username"], o["api_key"], {})
models = xmlrpc.client.ServerProxy("%s/xmlrpc/2/object" % o["url"])

po_num = sys.argv[1] if len(sys.argv) > 1 else "P01848"
digits = "".join(c for c in po_num if c.isdigit())

pos = models.execute_kw(o["database"], uid, o["api_key"],
    "purchase.order", "search_read",
    [[["name", "ilike", digits]]],
    {"fields": ["id", "name", "partner_id"], "limit": 5})

if not pos:
    print("No PO found for", po_num)
    sys.exit(1)

po = pos[0]
print("PO: %s  Supplier: %s" % (po["name"], po.get("partner_id", ["","?"])[1]))

lines = models.execute_kw(o["database"], uid, o["api_key"],
    "purchase.order.line", "search_read",
    [[["order_id", "=", po["id"]]]],
    {"fields": ["id", "vs_article", "product_id", "product_address_id"], "limit": 20})

print("\nPO lines — product_address_id values:")
for l in lines:
    vs  = l.get("vs_article") or "?"
    pid = l.get("product_address_id")
    print("  VSI %-15s  product_address_id = %s" % (vs, pid))

    # If it returned a partner ID, fetch its details
    if pid and isinstance(pid, (list, tuple)):
        partner = models.execute_kw(o["database"], uid, o["api_key"],
            "res.partner", "read", [[pid[0]]],
            {"fields": ["name", "street", "city", "zip", "country_id", "type"]})[0]
        print("                       -> name=%s  type=%s  street=%s  city=%s  country=%s" % (
            partner.get("name"), partner.get("type"),
            partner.get("street"), partner.get("city"),
            (partner.get("country_id") or ["",""])[1]))
