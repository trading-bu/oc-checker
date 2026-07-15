"""
AI-powered OC vs Odoo comparison — Vanilla Steel.

Drop-in replacement for compare_fields.compare().
Returns the identical result structure so post_slack.py works unchanged.

Enabled via:  config["use_ai_comparison"] = true   (in run_oc_check.py)
Fallback:     compare_fields.compare()              (when disabled or on error)

Flow:
  1. Build a concise Odoo context string (PO lines + SO spec per VSI ID)
  2. Send: Odoo context + extracted OC JSON → Claude
  3. Claude outputs per-line comparison JSON
  4. _build_result() converts that to the same shape as compare_fields output
"""

import json
import os
import re

import anthropic

# Reuse the commercial flags logic from compare_fields — no point duplicating it
from compare_fields import _build_flags


# ── Field definitions — order matches Slack display ───────────────────────────

FIELD_DEFS = [
    ("grade",            "Grade"),
    ("quality_choice",   "Quality Choice"),
    ("coating",          "Coating"),
    ("finish",           "Finish"),
    ("form",             "Form"),
    ("quantity",         "Quantity"),
    ("no_of_items",      "# of Items"),
    ("price",            "Unit Price"),
    ("thickness",        "Thickness"),
    ("width",            "Width"),
    ("length",           "Length"),
    ("tensile_strength", "Tensile Strength"),
]


# ── Odoo context builder ──────────────────────────────────────────────────────

def _build_odoo_context(po_data, po_lines, so_data, so_lines):
    """
    Build a compact, human-readable Odoo context string to pass to Claude.
    One line per VSI ID with all 12 comparison fields.
    """
    po_name  = po_data.get("name", "?") if po_data else "?"
    so_name  = so_data.get("name", "—") if so_data else "—"

    supplier = ""
    if po_data and po_data.get("partner_id"):
        p = po_data["partner_id"]
        supplier = p[1] if isinstance(p, (list, tuple)) else str(p)

    buyer = ""
    if so_data and so_data.get("partner_id"):
        b = so_data["partner_id"]
        buyer = b[1] if isinstance(b, (list, tuple)) else str(b)

    incoterm = ""
    if po_data and po_data.get("incoterm_id"):
        inc = po_data["incoterm_id"]
        incoterm = inc[1] if isinstance(inc, (list, tuple)) else str(inc)

    payment = ""
    if po_data and po_data.get("payment_term_id"):
        pay = po_data["payment_term_id"]
        payment = pay[1] if isinstance(pay, (list, tuple)) else str(pay)

    # SO line lookup by vs_article
    so_by_vs = {}
    for sl in (so_lines or []):
        vs = str(sl.get("vs_article") or "").strip()
        if vs:
            so_by_vs[vs] = sl

    out = []
    out.append("PO: %s  |  SO: %s" % (po_name, so_name))
    out.append("Supplier: %s  |  Buyer: %s" % (supplier, buyer))
    if incoterm:
        out.append("Incoterm: %s" % incoterm)
    if payment:
        out.append("Payment terms: %s" % payment)
    out.append("")
    out.append("Line items (each = one VSI coil to confirm):")

    for pl in po_lines:
        vs  = str(pl.get("vs_article")              or "").strip()
        sup = str(pl.get("original_supplier_article") or "").strip()
        aoo = str(pl.get("aoo_fast_number")          or "").strip()
        sl  = so_by_vs.get(vs, {})

        parts = ["  VSI %s" % (vs or "?")]

        for fld, lbl in [("grade",   "grade"),
                         ("choice",  "quality"),
                         ("coating", "coating"),
                         ("finish",  "finish"),
                         ("form",    "form")]:
            v = sl.get(fld)
            if v:
                parts.append("%s=%s" % (lbl, v))

        for fld, lbl, unit in [("thickness", "thick", "mm"),
                                ("width",     "width", "mm"),
                                ("length",    "length","mm"),
                                ("tensile_strength", "UTS", "MPa"),
                                ("no_of_items", "items", "")]:
            v = sl.get(fld)
            if v is not None:
                parts.append("%s=%s%s" % (lbl, v, unit))

        qty = pl.get("product_qty")
        if qty is not None:
            parts.append("qty=%st" % qty)

        price = pl.get("price_unit")
        if price is not None:
            parts.append("price=%s€/t" % price)

        if sup:
            parts.append("supplier_article=%s" % sup)
        if aoo:
            parts.append("aoo=%s" % aoo)

        out.append("  " + "  ".join(parts))

    return "\n".join(out)


# ── Claude call ───────────────────────────────────────────────────────────────

SYSTEM_PROMPT = (
    "You are an operations assistant for Vanilla Steel, a steel trading company. "
    "Your job is to verify supplier Order Confirmations against Vanilla Steel's "
    "purchase orders in Odoo. Output only valid JSON — no prose, no markdown fences."
)

def _build_user_prompt(odoo_ctx, oc_json, comp_cfg):
    qty_tol   = comp_cfg.get("quantity_tolerance_pct",   0.5)
    price_tol = comp_cfg.get("price_tolerance_pct",      1.0)
    thick_tol = comp_cfg.get("thickness_tolerance_mm",   0.05)
    width_tol = comp_cfg.get("width_tolerance_mm",       5.0)

    return """=== ODOO PURCHASE ORDER ===
{odoo_ctx}

=== EXTRACTED OC DATA ===
{oc_json}

=== YOUR TASK ===
For each Odoo line item above, find the matching line in the OC and verify the fields.

MATCHING — try these strategies in order for each Odoo line:
1. Code match: OC supplier_article / vs_article / coil_number matches Odoo supplier_article / vs_article / aoo
2. Quantity match: OC quantity ≈ Odoo qty within {qty_tol}%
3. Spec-group match: one OC line covers multiple Odoo lines of the SAME grade+thickness+width
   (bundle format — e.g. TK sends 9 coils as 1 OC position). Mark all covered lines,
   set skip_qty=true since the OC only shows the group total.
4. Positional: if none of the above work, match by position (first unmatched OC line → first unmatched Odoo line)

FIELD COMPARISON RULES:
- Quantity: match within {qty_tol}% (skip if spec_group)
- Price: match within {price_tol}%
- Thickness: match within {thick_tol}mm
- Width: match within {width_tol}mm
- Incoterm: compare ONLY the 3-letter code.
    "FCA Hagen" = "[FCA] FREE CARRIER" = "Free Carrier Győr" → all match "FCA"
- Payment terms: compare days as a NUMBER, ignore language.
    "Innerhalb 30 Tagen ohne Abzug" = "30 Days" → match
    "60 giorni data fattura" = "60 Days" → match
- Grade+coating split: if OC grade field contains a coating suffix (e.g. "HX260LAD+ZM100"),
    split it — treat as grade=HX260LAD and coating=ZM100 before comparing
- If Odoo has a value but OC doesn't mention it → match=null, note="not confirmed by OC"
- If OC has a value but Odoo field is empty → match=null, note="not in Odoo"
- If both are empty/null → match=null, note="" (excluded from score)
- For coil forms, set length match=null with note="N/A coil"

OUTPUT — valid JSON only, exactly this structure:
{{
  "line_results": [
    {{
      "vs_id": "F900249504",
      "match_type": "code",
      "skip_qty": false,
      "fields": {{
        "grade":            {{"odoo": "HX260LAD", "oc": "HX260LAD", "match": true,  "note": ""}},
        "quality_choice":   {{"odoo": "A",        "oc": null,       "match": null,  "note": "not confirmed by OC"}},
        "coating":          {{"odoo": "ZM100",     "oc": "ZM100",    "match": true,  "note": ""}},
        "finish":           {{"odoo": null,         "oc": null,       "match": null,  "note": ""}},
        "form":             {{"odoo": "Slit Coil",  "oc": "Slit Coil","match": true,  "note": ""}},
        "quantity":         {{"odoo": 1.376,         "oc": 1.376,      "match": true,  "note": ""}},
        "no_of_items":      {{"odoo": null,          "oc": null,       "match": null,  "note": ""}},
        "price":            {{"odoo": 820.0,          "oc": 820.0,      "match": true,  "note": ""}},
        "thickness":        {{"odoo": 1.5,            "oc": 1.5,        "match": true,  "note": ""}},
        "width":            {{"odoo": 143.0,           "oc": 143.0,      "match": true,  "note": ""}},
        "length":           {{"odoo": null,           "oc": null,       "match": null,  "note": "N/A coil"}},
        "tensile_strength": {{"odoo": null,           "oc": null,       "match": null,  "note": ""}}
      }}
    }}
  ]
}}

Include ALL Odoo line items in line_results, in the same order.
""".format(
        odoo_ctx=odoo_ctx,
        oc_json=oc_json,
        qty_tol=qty_tol,
        price_tol=price_tol,
        thick_tol=thick_tol,
        width_tol=width_tol,
    )


def _call_claude(prompt, model="claude-opus-4-5", max_tokens=8192):
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    client  = anthropic.Anthropic(api_key=api_key)
    resp    = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.content[0].text.strip()


def _parse_json(raw):
    """Parse Claude's response, tolerating markdown code fences and trailing commas."""
    text = raw.strip()
    # Strip ```json ... ``` or ``` ... ```
    text = re.sub(r'^```(?:json)?\s*', '', text)
    text = re.sub(r'\s*```$',         '', text)
    text = text.strip()
    # Extract just the outermost JSON object in case Claude adds prose before/after
    m = re.search(r'\{.*\}', text, re.DOTALL)
    if m:
        text = m.group(0)
    # Remove trailing commas before } or ] (common Claude output quirk)
    text = re.sub(r',\s*([}\]])', r'\1', text)
    return json.loads(text)


# ── Result builder ────────────────────────────────────────────────────────────

def _is_effective(f):
    """Mirror of post_slack._is_effective — same logic, kept local."""
    if f["status"] == "na":
        return False
    if f["status"] == "skip" and "group" in (f.get("note") or "").lower():
        return False
    odoo_empty = f.get("odoo", "—") in ("—", "", None)
    oc_empty   = f.get("oc",   "—") in ("—", "", None)
    return not (odoo_empty and oc_empty)


def _build_result(ai_result, oc_data, po_data, so_data, po_lines, so_lines,
                  config, odoo_shipping_address):
    """
    Convert Claude's comparison JSON to the same structure as compare_fields.compare().
    post_slack.py consumes this without any changes.
    """
    po_name  = po_data.get("name", "?") if po_data else "?"
    so_name  = so_data.get("name", "—") if so_data else "—"

    supplier = ""
    if po_data and po_data.get("partner_id"):
        p = po_data["partner_id"]
        supplier = p[1] if isinstance(p, (list, tuple)) else str(p)

    buyer = ""
    if so_data and so_data.get("partner_id"):
        b = so_data["partner_id"]
        buyer = b[1] if isinstance(b, (list, tuple)) else str(b)

    line_results     = []
    total_mismatches = 0

    for ai_lr in ai_result.get("line_results", []):
        vs_id    = ai_lr.get("vs_id", "?")
        skip_qty = ai_lr.get("skip_qty", False)
        mtype    = ai_lr.get("match_type", "ai")

        fields = []
        oc_line_reconstruct = {}   # rebuilt from Claude's per-field oc values

        for key, label in FIELD_DEFS:
            f      = (ai_lr.get("fields") or {}).get(key, {})
            odoo_v = f.get("odoo")
            oc_v   = f.get("oc")
            match  = f.get("match")   # True / False / None
            note   = f.get("note", "") or ""

            # Override: if skip_qty and this is quantity, force skip
            if key == "quantity" and skip_qty:
                match = None
                note  = note or "spec-group confirmed — qty is group total"

            # Determine status
            if match is True:
                status = "match"
            elif match is False:
                status = "mismatch"
            else:
                note_l = note.lower()
                if "n/a" in note_l or ("coil" in note_l and key == "length"):
                    status = "na"
                else:
                    status = "skip"

            fields.append({
                "key":    key,
                "label":  label,
                "status": status,
                "odoo":   str(odoo_v) if odoo_v not in (None, "")  else "—",
                "oc":     str(oc_v)   if oc_v   not in (None, "")  else "—",
                "note":   note,
            })

            # Reconstruct the OC line dict for Slack spec display
            if oc_v is not None:
                oc_line_reconstruct[key] = oc_v

        # Normalise oc_line keys to match what post_slack expects
        oc_line = {
            "grade":      oc_line_reconstruct.get("grade"),
            "thickness":  oc_line_reconstruct.get("thickness"),
            "width":      oc_line_reconstruct.get("width"),
            "quantity":   oc_line_reconstruct.get("quantity"),
            "unit_price": oc_line_reconstruct.get("price"),
            "form":       oc_line_reconstruct.get("form"),
            "coating":    oc_line_reconstruct.get("coating"),
        }

        effective  = [f for f in fields if _is_effective(f)]
        mismatches = sum(1 for f in effective if f["status"] == "mismatch")
        score      = sum(1 for f in effective if f["status"] == "match")
        total_eff  = len(effective)
        total_mismatches += mismatches

        is_positional = (mtype == "positional")

        line_results.append({
            "vs_id":              vs_id,
            "match_type":         mtype,
            "mismatches":         mismatches,
            "score":              score,
            "total":              total_eff,
            "fields":             fields,
            "oc_line":            oc_line,
            "positional_fallback": is_positional,
            "match_note":         "positional fallback" if is_positional else "",
        })

    flags = _build_flags(oc_data, po_data, so_data, odoo_shipping_address)

    return {
        "po_name":           po_name,
        "so_name":           so_name,
        "supplier":          supplier,
        "buyer":             buyer,
        "oc_ref":            oc_data.get("supplier_order_num", "—"),
        "confirmation_date": oc_data.get("confirmation_date", "—"),
        "is_match":          (total_mismatches == 0),
        "total_mismatches":  total_mismatches,
        "line_results":      line_results,
        "flags":             flags,
        "oc_data":           oc_data,
    }


# ── Public entry point ────────────────────────────────────────────────────────

def compare_via_claude(oc_data, po_data, po_lines, so_data, so_lines, config,
                       odoo_shipping_address=None):
    """
    AI-powered comparison of extracted OC JSON vs Odoo PO/SO data.

    Drop-in replacement for compare_fields.compare().
    Falls back gracefully — caller should catch exceptions and retry with
    compare_fields.compare() if needed.
    """
    comp_cfg    = config.get("comparison", {})
    odoo_ctx    = _build_odoo_context(po_data, po_lines, so_data, so_lines)
    oc_json_str = json.dumps(oc_data, indent=2, ensure_ascii=False)
    prompt      = _build_user_prompt(odoo_ctx, oc_json_str, comp_cfg)

    model = config.get("ai_comparison_model", "claude-opus-4-5")
    print("  [AI compare] Sending %d PO lines to Claude (%s)..." % (len(po_lines), model))

    # Scale max_tokens with PO size: ~700 tokens per line (12 fields × ~55 tokens each).
    # Floor at 8192; most models support up to 16384 for standard generation.
    max_tok   = max(8192, len(po_lines) * 700)
    raw       = _call_claude(prompt, model=model, max_tokens=max_tok)
    ai_result = _parse_json(raw)

    n_lines = len(ai_result.get("line_results", []))
    print("  [AI compare] Received %d line result(s)" % n_lines)

    return _build_result(ai_result, oc_data, po_data, so_data, po_lines, so_lines,
                         config, odoo_shipping_address)
