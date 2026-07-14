"""
Post OC check results to Slack via Incoming Webhook or Bot API.
"""

import json
import sys
import urllib.request
from datetime import datetime


# ── Low-level posting ─────────────────────────────────────────────────────────

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


# ── Formatting helpers ────────────────────────────────────────────────────────

def _fmt_num(v, decimals=2):
    if v is None:
        return "---"
    try:
        return "{:,.{}f}".format(float(v), decimals)
    except Exception:
        return str(v)


def _fmt_date(iso):
    """2026-08-15  →  15 Aug 2026.  Returns empty string if blank."""
    if not iso or iso in ("—", "---", "None"):
        return ""
    try:
        s = str(iso).strip()[:10]
        year, month, day = s.split("-")
        month_abbr = ["", "Jan","Feb","Mar","Apr","May","Jun",
                      "Jul","Aug","Sep","Oct","Nov","Dec"]
        return "%d %s %s" % (int(day), month_abbr[int(month)], year)
    except Exception:
        return str(iso)[:10]


def _fmt_dim(v):
    """Format a dimension: drop trailing .0 for whole numbers (1500.0 → 1500)."""
    if v is None:
        return ""
    try:
        f = float(v)
        return str(int(f)) if f == int(f) else str(f)
    except Exception:
        return str(v)


def _fmt_delta(label, odoo_v, oc_v):
    """Return a delta string for numeric mismatches, e.g. '+0.50mm', '-€30.00'."""
    try:
        o = float(str(odoo_v).replace(",", "").replace("€", "").strip())
        c = float(str(oc_v).replace(",", "").replace("€", "").strip())
        delta = c - o
        lbl   = label.lower()
        if "thickness" in lbl or "width" in lbl or "length" in lbl:
            return "  (%+.2fmm)" % delta
        elif "price" in lbl:
            sign = "+" if delta >= 0 else "-"
            return "  (%s€%.2f)" % (sign, abs(delta))
        elif "qty" in lbl or "quantity" in lbl:
            return "  (%+.3ft)" % delta
        else:
            return "  (%+.2f)" % delta
    except Exception:
        return ""


# ── Effective score helpers ───────────────────────────────────────────────────

def _is_effective(f):
    """
    True if this field should be included in the match count.

    Excluded:
      - "na" fields (not applicable — e.g. length for coils)
      - Multi-coil group quantity skips (can't verify individual weight)
      - Fields where BOTH sides are empty/missing (nothing to compare)

    Included (counts in denominator):
      - Both sides have values (match or mismatch)
      - One side has a value, other doesn't (unverified — in denominator, not numerator)
    """
    if f["status"] == "na":
        return False
    if f["status"] == "skip" and "group" in (f.get("note") or "").lower():
        return False
    odoo_empty = f.get("odoo", "—") in ("—", "", None)
    oc_empty   = f.get("oc",   "—") in ("—", "", None)
    return not (odoo_empty and oc_empty)


def _effective_score(field_res):
    """
    Compute score/total from stored fields.
    Returns (score, total) — total only counts effective fields.
    """
    effective = [f for f in field_res if _is_effective(f)]
    score = sum(1 for f in effective if f["status"] == "match")
    return score, len(effective)


# ── Main message builder ──────────────────────────────────────────────────────

def build_po_status_text(po_name, po_log):
    """
    Build the Slack message for a PO's current OC status.

    Confirmed line:
      ✅ *VSI-17918186*  CK75M2GKZ  1.18×105mm  0.924t  (OC 213136 · 7 Jul 2026)  4/4  ✅
    Mismatch line:
      ❌ *VSI-17918189*  C45E  2×635mm  3.175t  (OC 213135 · 7 Jul 2026)  3/4
         ❌ *Unit Price*   Odoo 450.00  ≠  OC 430.00  (-€20.00)
         ⚠️ *Coating*   Odoo Z275  (not confirmed by OC)
    Pending line:
      ⏳ *VSI-17919000*   OC not yet received
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

    # Pull commercial flags
    incoterm_str = ""
    net_str      = ""
    pay_str      = ""
    for flag in flags:
        if flag["type"] == "incoterms":
            incoterm_str = "⚠️ %s (PO: %s)" % (flag["oc"], flag["odoo"])
        elif flag["type"] == "vat" and flag.get("net"):
            net_str = "EUR %s net" % _fmt_num(flag["net"])
        elif flag["type"] == "payment_terms":
            pay_str = "⚠️ Payment: %s (PO: %s)" % (flag["oc"], flag["odoo"])

    DIV = "─" * 36

    lines = []

    # ── Header ────────────────────────────────────────────────────────────────
    if n_pending == 0 and n_mismatch == 0:
        lines.append(":white_check_mark:  *OC CONFIRMED — %s  %s*" % (po_name, so_name))
    elif n_mismatch > 0 and n_pending == 0:
        lines.append(":x:  *OC MISMATCH — %s  %s — %d issue(s)*" % (
            po_name, so_name, n_mismatch))
    else:
        lines.append(":hourglass_flowing_sand:  *OC IN PROGRESS — %s  %s — %d/%d confirmed*" % (
            po_name, so_name, n_conf + n_mismatch, total))

    # Subheader: supplier → buyer
    lines.append("%s  →  %s" % (supplier, buyer))

    # Progress line
    progress_parts = [
        "*%d/%d confirmed*%s%s" % (
            n_conf, total,
            "   |   %d mismatch(es)" % n_mismatch if n_mismatch else "",
            "   |   %d pending" % n_pending if n_pending else "",
        )
    ]
    if incoterm_str:
        progress_parts.append(incoterm_str)
    if net_str:
        progress_parts.append(net_str)
    if pay_str:
        progress_parts.append(pay_str)
    lines.append("   |   ".join(progress_parts))

    # (pattern_b_ocs kept for backward compat with old log entries — not generated by new code)

    # ── Per-line rows ─────────────────────────────────────────────────────────
    lines.append("")
    lines.append(DIV)

    def _sort_key(item):
        return {"mismatch": 0, "confirmed": 1, "pending": 2}.get(
            item[1].get("status", "pending"), 9)

    for vs_id, entry in sorted(line_items.items(), key=_sort_key):
        status    = entry.get("status", "pending")
        oc_line   = entry.get("oc_line", {})
        field_res = entry.get("fields", [])

        if status == "pending":
            lines.append(":hourglass_flowing_sand: *%s*   _OC not yet received_" % vs_id)
            continue

        # Compact spec from OC data
        grade    = oc_line.get("grade", "") or ""
        thick    = oc_line.get("thickness", "")
        width    = oc_line.get("width", "")
        qty      = oc_line.get("quantity", "")
        extr_warn = oc_line.get("extraction_warning") or ""

        dim_str = "%s×%smm" % (_fmt_dim(thick), _fmt_dim(width)) if thick and width else ""
        qty_str = "%st" % _fmt_dim(qty) if qty else ""

        # OC reference + issue date: (OC 213136 · 7 Jul 2026)
        oc_ref      = entry.get("oc_ref", "")
        oc_date     = entry.get("oc_date") or entry.get("date", "")
        oc_date_fmt = _fmt_date(oc_date)
        if oc_ref and oc_date_fmt:
            oc_info = "(OC %s · %s)" % (oc_ref, oc_date_fmt)
        elif oc_ref:
            oc_info = "(OC %s)" % oc_ref
        else:
            oc_info = ""

        # Effective match count
        score, total_eff = _effective_score(field_res)
        count_str = "%d/%d" % (score, total_eff) if total_eff else ""

        spec_parts   = [p for p in [grade, dim_str, qty_str] if p]
        spec_str     = ("  " + "  ".join(spec_parts)) if spec_parts else ""
        suffix_parts = [p for p in [oc_info, count_str] if p]
        suffix       = ("  " + "  ".join(suffix_parts)) if suffix_parts else ""

        match_note = entry.get("match_note", "")
        pos_warn   = "   :warning: _Matched by position (no code/qty/spec match)_" if match_note else ""

        if status == "confirmed":
            lines.append(":white_check_mark: *%s*%s%s  :white_check_mark:" % (
                vs_id, spec_str, suffix))
            if pos_warn:
                lines.append(pos_warn)
            # Show fields Odoo has but OC did not confirm
            for f in field_res:
                if not _is_effective(f):
                    continue
                if f["status"] != "skip":
                    continue
                odoo_has = f.get("odoo", "—") not in ("—", "")
                oc_has   = f.get("oc",   "—") not in ("—", "")
                if odoo_has and not oc_has:
                    lines.append("   :warning: *%s*   Odoo `%s`  _(not confirmed by OC)_" % (
                        f["label"], f["odoo"]))
                elif oc_has and not odoo_has:
                    lines.append("   :warning: *%s*   OC `%s`  _(not in Odoo)_" % (
                        f["label"], f["oc"]))
            if extr_warn:
                lines.append("   :warning: _Extraction warning: %s_" % extr_warn)

        else:  # mismatch
            lines.append(":x: *%s*%s%s" % (vs_id, spec_str, suffix))
            if pos_warn:
                lines.append(pos_warn)

            # Show only non-matching effective fields
            for f in field_res:
                if not _is_effective(f):
                    continue
                if f["status"] == "match":
                    continue

                if f["status"] == "mismatch":
                    delta = _fmt_delta(f["label"], f["odoo"], f["oc"])
                    lines.append("   :x: *%s*   Odoo `%s`  ≠  OC `%s`%s" % (
                        f["label"], f["odoo"], f["oc"], delta))

                elif f["status"] == "skip":
                    odoo_has = f.get("odoo", "—") not in ("—", "")
                    oc_has   = f.get("oc",   "—") not in ("—", "")
                    if odoo_has and not oc_has:
                        lines.append("   :warning: *%s*   Odoo `%s`  _(not confirmed by OC)_" % (
                            f["label"], f["odoo"]))
                    elif oc_has and not odoo_has:
                        lines.append("   :warning: *%s*   OC `%s`  _(not in Odoo)_" % (
                            f["label"], f["oc"]))

            if extr_warn:
                lines.append("   :warning: _Extraction warning: %s_" % extr_warn)

    lines.append(DIV)

    # ── Commercial flags ──────────────────────────────────────────────────────
    flag_lines = []
    for flag in flags:
        ftype = flag["type"]

        if ftype == "pickup_address":
            if flag["warning"]:
                flag_lines.append(":round_pushpin: *Pickup address DIFFERENT — verify before shipping*")
                flag_lines.append("   OC: %s" % flag["oc"])
                flag_lines.append("   Odoo: %s" % flag["odoo"])
            else:
                flag_lines.append(":round_pushpin: Pickup: %s  ✅" % flag["oc"])

        elif ftype in ("incoterms", "payment_terms") and flag.get("warning"):
            pass  # Already shown in progress line

        elif ftype == "vat":
            net_v   = ("EUR %s" % _fmt_num(flag["net"]))   if flag.get("net")   else ""
            gross_v = ("EUR %s" % _fmt_num(flag["gross"])) if flag.get("gross") else ""
            vat_parts = [p for p in ["VAT %s" % flag["vat_pct"], net_v, "gross %s" % gross_v] if p]
            flag_lines.append(":receipt: %s" % "  |  ".join(vat_parts))

    if flag_lines:
        lines.append("")
        for fl in flag_lines:
            lines.append(fl)

    # ── Footer ────────────────────────────────────────────────────────────────
    lines.append("")
    if n_pending == 0 and n_mismatch == 0:
        lines.append(":white_check_mark: All %d items confirmed — open SO `%s` in Odoo and click *Send*." % (
            total, so_name))
    elif n_pending > 0:
        lines.append(":hourglass_flowing_sand: %d/%d confirmed — waiting on OC for %d more item(s)." % (
            n_conf, total, n_pending))
    else:
        lines.append(":x: Fix %d mismatch(es) before sending SO `%s`." % (n_mismatch, so_name))

    return "\n".join(lines).strip()


# ── Slack Web API ─────────────────────────────────────────────────────────────

def _slack_api_call(token, endpoint, payload):
    body = json.dumps(payload).encode("utf-8")
    req  = urllib.request.Request(
        "https://slack.com/api/%s" % endpoint,
        data=body,
        headers={"Content-Type": "application/json",
                 "Authorization": "Bearer %s" % token},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode())


def check_slack_auth(token, channel):
    """Validate bot token + channel at startup. Returns True if OK."""
    try:
        body = _slack_api_call(token, "auth.test", {})
        if not body.get("ok"):
            print("SLACK AUTH FAILED: %s  (check SLACK_BOT_TOKEN starts with xoxb-)" %
                  body.get("error"))
            return False
        print("Slack auth OK: bot=%s workspace=%s" % (body.get("user"), body.get("team")))
    except Exception as e:
        print("SLACK AUTH ERROR: %s" % e)
        return False
    try:
        body2 = _slack_api_call(token, "conversations.info", {"channel": channel})
        if not body2.get("ok"):
            # conversations.info needs channels:read scope — not required for posting.
            # Only warn; don't fail startup if the bot only has chat:write.
            print("Slack channel check skipped: %s (bot may lack channels:read scope — posting still works)" %
                  body2.get("error"))
            return True
        ch   = body2.get("channel", {})
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
    Post via Slack Web API (chat.postMessage).
    Returns (ok: bool, ts: str|None).
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


def post_po_status_update(webhook_url, po_name, po_log):
    """Post PO status via webhook (no threading)."""
    text = build_po_status_text(po_name, po_log)
    return post(webhook_url, {"text": text})


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python post_slack.py <webhook_url> <message_text>")
        sys.exit(1)
    ok = post_text(sys.argv[1], sys.argv[2])
    sys.exit(0 if ok else 1)
