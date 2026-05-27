"""
Post OC check results to Slack via Incoming Webhook.
Implements the 2-part format from OC Analysis Instructions v1.1.
"""

import json
import sys
import urllib.request


def post(webhook_url, payload):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        webhook_url, data=data,
        headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = resp.read().decode()
            return resp.status == 200 and body == "ok"
    except Exception as e:
        print("Slack post failed: %s" % e, file=sys.stderr)
        return False


def post_text(webhook_url, text):
    return post(webhook_url, {"text": text})


def _fmt_num(v, decimals=2):
    if v is None:
        return "---"
    try:
        return "{:,.{}f}".format(float(v), decimals)
    except Exception:
        return str(v)


def post_oc_result(webhook_url, result, filename):
    po        = result.get("po_name", "?")
    so        = result.get("so_name", "---")
    supplier  = result.get("supplier", "?")
    buyer     = result.get("buyer", "---")
    oc_ref    = result.get("oc_ref", "---")
    conf_date = result.get("confirmation_date", "---")
    is_match  = result.get("is_match", False)
    mismatches = result.get("total_mismatches", 0)
    pattern   = result.get("pattern", "A")
    line_results = result.get("line_results", [])
    flags     = result.get("flags", [])

    SEP = "=" * 34

    lines = []

    # Header
    if is_match:
        lines.append(":white_check_mark:  *OC CONFIRMED -- %s %s*" % (po, so))
    else:
        issues = mismatches if pattern == "A" else "?"
        lines.append(":x:  *OC MISMATCH -- %s -- %s issue(s)*" % (po, issues))

    lines.append("")
    lines.append("PO: `%s`   SO: `%s`   Supplier: %s   Buyer: %s" % (po, so, supplier, buyer))
    lines.append("OC Ref: %s   Confirmed: %s" % (oc_ref, conf_date))
    lines.append("File: _%s_" % filename)
    lines.append("")
    lines.append(SEP)
    lines.append("*PART 1 -- PARAMETER CHECK*")
    lines.append(SEP)

    # Pattern B/C warning
    if pattern == "C":
        oc_lines_data = result.get("oc_data", {}).get("lines", [])
        total_wt = oc_lines_data[0].get("quantity", "?") if oc_lines_data else "?"
        lines.append("")
        lines.append(":warning: *Pattern C -- Combined OC*: %s confirmed the entire PO as a single weight of %st." % (supplier, total_wt))
        lines.append("   Individual spec fields cannot be auto-verified. Please check each PO line manually.")
    elif pattern == "B":
        lines.append("")
        lines.append(":warning: *Pattern B -- Combined OC*: %s aggregated multiple PO lines into fewer OC lines." % supplier)
        lines.append("   Individual spec fields cannot be auto-verified. Please check each PO line manually.")

    # Per-line results
    for lr in line_results:
        vs_id = lr.get("vs_id", "?")
        ol    = lr.get("oc_line", {})
        grade = ol.get("grade", "")
        thick = ol.get("thickness", "")
        width = ol.get("width", "")
        qty   = ol.get("quantity", "")

        dim_str = (" -- %sx%smm" % (thick, width)) if thick and width else ""
        qty_str = (" -- %st" % qty) if qty else ""
        grade_str = (" -- " + grade) if grade else ""
        lines.append("")
        lines.append("*%s*%s%s%s" % (vs_id, grade_str, dim_str, qty_str))

        for f in lr.get("fields", []):
            label  = f["label"]
            status = f["status"]
            odoo_v = f["odoo"]
            oc_v   = f["oc"]
            note   = f.get("note", "")

            if status == "match":
                note_str = ("  " + note) if note else ""
                lines.append("   :white_check_mark: %s: %s%s" % (label, odoo_v, note_str))
            elif status == "mismatch":
                lines.append("   :x: *%s*: Odoo `%s`  !=  OC `%s`" % (label, odoo_v, oc_v))
            elif status == "na":
                lines.append("   N/A %s: not applicable (coil)" % label)
            else:
                lines.append("   -- %s: %s  _(not stated in OC)_" % (label, odoo_v))

        score = lr.get("score", 0)
        total = lr.get("total", 0)
        lines.append("   _Score: %d/%d verified fields_" % (score, total))

    # Part 2 flags
    if flags:
        lines.append("")
        lines.append(SEP)
        lines.append("*PART 2 -- FLAGS BEFORE SENDING SO*")
        lines.append(SEP)

        for flag in flags:
            ftype = flag["type"]

            if ftype == "pickup_address":
                lines.append("")
                lines.append(":round_pushpin: *Pickup Address:*")
                lines.append("   OC: %s" % flag["oc"])
                lines.append("   Odoo: %s" % flag["odoo"])
                if flag["warning"]:
                    lines.append("   -> :warning: *DIFFERENT -- verify before shipping*")

            elif ftype == "incoterms":
                lines.append("")
                lines.append(":warning: *Incoterms MISMATCH:*")
                lines.append("   OC: `%s`  |  PO has: `%s` -- confirm with supplier" % (flag["oc"], flag["odoo"]))

            elif ftype == "payment_terms":
                lines.append("")
                lines.append(":warning: *Payment Terms MISMATCH:*")
                lines.append("   OC: `%s`  |  PO has: `%s` -- confirm with supplier" % (flag["oc"], flag["odoo"]))

            elif ftype == "vat":
                net_str   = ("EUR " + _fmt_num(flag["net"]))   if flag.get("net")   else "---"
                gross_str = ("EUR " + _fmt_num(flag["gross"])) if flag.get("gross") else "---"
                lines.append("")
                lines.append(":receipt: VAT: %s  |  Net: %s  |  Gross (incl. VAT): %s" % (flag["vat_pct"], net_str, gross_str))

    # Footer
    lines.append("")
    lines.append(SEP)
    if is_match:
        lines.append(":white_check_mark: All parameters confirmed -> Open SO `%s` in Odoo and click Send." % so)
    else:
        lines.append(":x: Fix %d mismatch(es) in Odoo before sending SO `%s`." % (mismatches, so))

    text = "\n".join(lines).strip()
    return post(webhook_url, {"text": text})


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python post_slack.py <webhook_url> <message_text>")
        sys.exit(1)
    ok = post_text(sys.argv[1], sys.argv[2])
    sys.exit(0 if ok else 1)
