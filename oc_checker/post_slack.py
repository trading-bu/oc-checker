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

        coil_num  = ol.get("coil_number", "")
        dim_str   = (" -- %sx%smm" % (thick, width)) if thick and width else ""
        qty_str   = (" -- %st" % qty) if qty else ""
        grade_str = (" -- " + grade) if grade else ""
        coil_str  = ("  |  Coil: %s" % coil_num) if coil_num else ""
        lines.append("")
        lines.append("*%s*%s%s%s%s" % (vs_id, grade_str, dim_str, qty_str, coil_str))

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


def _slack_api_call(token, endpoint, payload):
    """Make a Slack Web API call. Returns the parsed JSON response body."""
    import urllib.request as _ur
    body = json.dumps(payload).encode("utf-8")
    req = _ur.Request(
        "https://slack.com/api/%s" % endpoint,
        data=body,
        headers={"Content-Type": "application/json", "Authorization": "Bearer %s" % token},
        method="POST",
    )
    with _ur.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode())


def check_slack_auth(token, channel):
    """
    Validate bot token + channel at startup.
    Prints a clear diagnostic line visible in CI logs.
    Returns True if OK.
    """
    try:
        body = _slack_api_call(token, "auth.test", {})
        if not body.get("ok"):
            print("SLACK AUTH FAILED: %s  (check SLACK_BOT_TOKEN starts with xoxb-)" % body.get("error"))
            return False
        print("Slack auth OK: bot=%s workspace=%s" % (body.get("user"), body.get("team")))
    except Exception as e:
        print("SLACK AUTH ERROR: %s" % e)
        return False
    try:
        body2 = _slack_api_call(token, "conversations.info", {"channel": channel})
        if not body2.get("ok"):
            print("SLACK CHANNEL ERROR: %s  (check SLACK_CHANNEL_ID='%s')" % (body2.get("error"), channel))
            return False
        ch = body2.get("channel", {})
        in_ch = ch.get("is_member", False)
        print("Slack channel OK: #%s  bot_is_member=%s" % (ch.get("name"), in_ch))
        if not in_ch:
            print("  ACTION NEEDED: run /invite @<botname> in the Slack channel")
    except Exception as e:
        print("SLACK CHANNEL CHECK ERROR: %s" % e)
        return False
    return True


def post_via_api(token, channel, text, thread_ts=None):
    """
    Post a message via the Slack Web API (chat.postMessage).

    Returns (ok: bool, ts: str|None) — ts is the message timestamp,
    which can be used as thread_ts for replies.
    """
    payload = {"channel": channel, "text": text}
    if thread_ts:
        payload["thread_ts"] = thread_ts
    try:
        body = _slack_api_call(token, "chat.postMessage", payload)
        if body.get("ok"):
            return True, body.get("ts")
        print("Slack API error: %s | channel=%s thread_ts=%s" % (
            body.get("error"), channel, thread_ts), file=sys.stderr)
        return False, None
    except Exception as e:
        print("Slack API post failed: %s" % e, file=sys.stderr)
        return False, None


def build_po_status_text(po_name, po_log):
    """
    Build the full PO status message text — same content as post_po_status_update
    but returns the string instead of posting it.
    """
    line_items    = po_log.get("line_items", {})
    so_name       = po_log.get("so_name", "—")
    supplier      = po_log.get("supplier", "?")
    buyer         = po_log.get("buyer", "—")
    flags         = po_log.get("flags", [])
    pattern_b_ocs = po_log.get("pattern_b_ocs", [])

    total      = len(line_items)
    n_conf     = sum(1 for v in line_items.values() if v["status"] == "confirmed")
    n_mismatch = sum(1 for v in line_items.values() if v["status"] == "mismatch")
    n_pending  = sum(1 for v in line_items.values() if v["status"] == "pending")

    SEP   = "=" * 34
    lines = []

    # ---- Header ----
    if n_pending == 0 and n_mismatch == 0:
        lines.append(":white_check_mark:  *OC CONFIRMED -- %s  %s*" % (po_name, so_name))
    elif n_mismatch > 0 and n_pending == 0:
        lines.append(":x:  *OC MISMATCH -- %s  %s -- %d issue(s)*" % (
            po_name, so_name, n_mismatch))
    else:
        lines.append(":hourglass_flowing_sand:  *OC IN PROGRESS -- %s  %s -- %d/%d items*" % (
            po_name, so_name, n_conf + n_mismatch, total))

    lines.append("")
    lines.append("PO: `%s`   SO: `%s`   Supplier: %s   Buyer: %s" % (
        po_name, so_name, supplier, buyer))

    progress = "*%d/%d items confirmed*" % (n_conf, total)
    if n_mismatch:
        progress += "   |   %d mismatch(es)" % n_mismatch
    if n_pending:
        progress += "   |   %d still pending" % n_pending
    lines.append(progress)

    # ---- Part 1: line items ----
    lines.append("")
    lines.append(SEP)
    lines.append("*PART 1 -- PARAMETER CHECK*")
    lines.append(SEP)

    def _sort_key(item):
        return {"mismatch": 0, "confirmed": 1, "pending": 2}.get(item[1].get("status", "pending"), 9)

    for vs_id, entry in sorted(line_items.items(), key=_sort_key):
        status = entry.get("status", "pending")

        if status == "pending":
            lines.append("")
            lines.append(":hourglass_flowing_sand: *%s*   _— OC not yet received_" % vs_id)
            continue

        oc_ref      = entry.get("oc_ref", "?")
        conf_date   = entry.get("date", "")
        oc_line     = entry.get("oc_line", {})
        field_res   = entry.get("fields", [])
        score       = entry.get("score", 0)
        total_flds  = entry.get("total", 0)
        mismatches  = entry.get("mismatches", 0)

        grade    = oc_line.get("grade", "")
        thick    = oc_line.get("thickness", "")
        width    = oc_line.get("width", "")
        qty      = oc_line.get("quantity", "")
        coil_num = oc_line.get("coil_number", "")

        grade_str = ("  " + grade)                 if grade             else ""
        dim_str   = ("  %sx%smm" % (thick, width)) if thick and width   else ""
        qty_str   = ("  %st" % qty)                if qty               else ""
        coil_str  = ("  |  Coil: %s" % coil_num)  if coil_num          else ""
        meta      = "  _(OC %s · %s)_" % (oc_ref, conf_date) if conf_date else "  _(OC %s)_" % oc_ref

        lines.append("")
        if mismatches == 0:
            lines.append(":white_check_mark: *%s*%s%s%s%s%s   %d/%d ✅" % (
                vs_id, grade_str, dim_str, qty_str, coil_str, meta, score, total_flds))
        else:
            lines.append(":x: *%s*%s%s%s%s%s" % (
                vs_id, grade_str, dim_str, qty_str, coil_str, meta))
            for f in field_res:
                label   = f["label"]
                fstatus = f["status"]
                odoo_v  = f["odoo"]
                oc_v    = f["oc"]
                note    = f.get("note", "")
                if fstatus == "mismatch":
                    lines.append("   :x: *%s*: Odoo `%s`  !=  OC `%s`" % (label, odoo_v, oc_v))
                elif fstatus == "match":
                    note_str = ("  " + note) if note else ""
                    lines.append("   :white_check_mark: %s: %s%s" % (label, odoo_v, note_str))
                elif fstatus == "na":
                    lines.append("   N/A %s" % label)
                else:
                    lines.append("   -- %s: %s  _(not in OC)_" % (label, odoo_v))
            lines.append("   _Score: %d/%d verified fields_" % (score, total_flds))

    # ---- Pattern B/C note ----
    if pattern_b_ocs:
        lines.append("")
        lines.append(":warning: Pattern B/C OC(s) received — individual lines cannot be auto-verified:")
        for pb in pattern_b_ocs:
            lines.append("   OC %s  (%s)  %s  — manual review required" % (
                pb["oc_ref"], pb["filename"], pb["date"]))

    # ---- Part 2: flags ----
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
                lines.append("   OC: `%s`  |  PO has: `%s` -- confirm with supplier" % (
                    flag["oc"], flag["odoo"]))

            elif ftype == "payment_terms":
                lines.append("")
                lines.append(":warning: *Payment Terms MISMATCH:*")
                lines.append("   OC: `%s`  |  PO has: `%s` -- confirm with supplier" % (
                    flag["oc"], flag["odoo"]))

            elif ftype == "vat":
                net_str   = ("EUR " + _fmt_num(flag["net"]))   if flag.get("net")   else "---"
                gross_str = ("EUR " + _fmt_num(flag["gross"])) if flag.get("gross") else "---"
                lines.append("")
                lines.append(":receipt: VAT: %s  |  Net: %s  |  Gross (incl. VAT): %s" % (
                    flag["vat_pct"], net_str, gross_str))

    # ---- Footer ----
    lines.append("")
    lines.append(SEP)
    if n_pending == 0 and n_mismatch == 0:
        lines.append(":white_check_mark: All %d items confirmed -> Open SO `%s` in Odoo and click Send." % (
            total, so_name))
    elif n_pending > 0:
        lines.append(":hourglass_flowing_sand: %d/%d items confirmed. Still waiting on OC for %d item(s)." % (
            n_conf, total, n_pending))
    else:
        lines.append(":x: Fix %d mismatch(es) in Odoo before sending SO `%s`." % (n_mismatch, so_name))
    return "\n".join(lines).strip()


def post_po_status_update(webhook_url, po_name, po_log):
    """
    Post the full status of a PO as a single Slack message.

    Reads from the persistent po_oc_log entry built up across runs:
      - confirmed items  \u2192 compact one-liner (full detail if any mismatches)
      - mismatch items   \u2192 full field detail so trader knows what to fix
      - pending items    \u2192 \u23f3 "OC not yet received"

    Message progresses naturally:
      Day 1: \u23f3 3/10 confirmed \u2014 7 still pending
      Day 2: \u23f3 6/10 confirmed \u2014 4 still pending
      Day 3: \u2705 All 10 confirmed \u2014 open SO and send

    Args:
        po_name  \u2014 e.g. "P01807"
        po_log   \u2014 the state["po_oc_log"][po_name] dict
    """
    text = build_po_status_text(po_name, po_log)
    return post(webhook_url, {"text": text})


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python post_slack.py <webhook_url> <message_text>")
        sys.exit(1)
    ok = post_text(sys.argv[1], sys.argv[2])
    sys.exit(0 if ok else 1)
