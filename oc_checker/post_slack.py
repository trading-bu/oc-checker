"""
Post OC check results to a Slack channel via Incoming Webhook.
"""

import json
import sys
import urllib.request


def post(webhook_url, payload):
    """Post a dict payload to Slack webhook. Returns True on success."""
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        webhook_url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = resp.read().decode()
            return resp.status == 200 and body == "ok"
    except Exception as e:
        print("Slack post failed: %s" % e, file=sys.stderr)
        return False


def post_text(webhook_url, text):
    """Post plain text to Slack."""
    return post(webhook_url, {"text": text})


def post_oc_result(webhook_url, result, filename):
    """
    Format a compare_fields result dict as a Slack message and post it.
    One message per PO with line-by-line field results.
    """
    po_name  = result.get("po_name", "?")
    so_name  = result.get("so_name", "—")
    supplier = result.get("supplier", "?")
    buyer    = result.get("buyer", "—")
    is_match = result.get("is_match", False)

    icon = ":white_check_mark:" if is_match else ":x:"
    status_text = "MATCH" if is_match else "MISMATCH"

    lines = []
    lines.append("%s *%s* | PO: `%s` | SO: `%s`" % (icon, status_text, po_name, so_name))
    lines.append("Supplier: %s  →  Buyer: %s" % (supplier, buyer))
    lines.append("File: _%s_" % filename)
    lines.append("")

    for lr in result.get("line_results", []):
        vs_id = lr.get("vs_id", "?")
        score = lr.get("score", 0)
        total = lr.get("total", 13)
        lines.append("*Article %s* — %d/%d fields match" % (vs_id, score, total))

        for f in lr.get("fields", []):
            key   = f.get("key", "")
            # Only show the key fields in the summary
            if key not in ("qty", "price", "thickness", "width", "grade", "quality_choice",
                           "coating", "length", "form", "finish", "no_of_items",
                           "tensile_strength", "description"):
                continue
            tick   = ":white_check_mark:" if f["status"] == "match" else ":x:"
            label  = f["label"]
            odoo_v = f.get("odoo", "—")
            oc_v   = f.get("oc", "—")
            if f["status"] == "match":
                lines.append("  %s %s: %s" % (tick, label, odoo_v))
            else:
                lines.append("  %s %s: Odoo `%s`  vs  OC `%s`" % (tick, label, odoo_v, oc_v))

        lines.append("")

    text = "\n".join(lines).strip()
    return post(webhook_url, {"text": text})


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python post_slack.py <webhook_url> <message_text>")
        sys.exit(1)
    ok = post_text(sys.argv[1], sys.argv[2])
    sys.exit(0 if ok else 1)
