"""
OC vs Odoo field comparison — Vanilla Steel.

Implements the OC Analysis Instructions v1.1:
  Part 1 — 13 parameter check per line item
  Part 2 — Commercial flags (incoterms, payment terms, VAT, pickup address)
"""

import re


# ── Helpers ──────────────────────────────────────────────────────────────────

def _norm(v):
    return str(v).strip() if v not in (None, "", False) else ""


def _to_float(v):
    if v is None:
        return None
    try:
        s = str(v).replace(",", "").replace(" ", "")
        return float(s)
    except (ValueError, TypeError):
        return None


def _pct_diff(a, b):
    if not a or not b:
        return None
    return abs(a - b) / b * 100


def _split_grade_coating(grade_str):
    """
    Split 'DX51D+Z275' into ('DX51D', 'Z275').
    Returns (grade, coating_suffix) or (grade_str, None).
    Coating prefixes: Z, ZM, ZF, ZA, AZ, AS, AL, GI
    """
    if not grade_str:
        return grade_str, None
    m = re.match(r'^(.+?)\+((ZM|ZF|ZA|AZ|ZE|AS|AL|GI|Z)\d*[A-Z]?\d*)\s*$',
                 grade_str.strip(), re.IGNORECASE)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return grade_str, None


# ── Line matching ─────────────────────────────────────────────────────────────

def _norm_article(v):
    return re.sub(r'[\s\-_]', '', _norm(v)).upper()


def _match_po_line(oc_line, po_lines):
    """Match OC line to PO line by supplier article number."""
    oc_sup = _norm_article(oc_line.get("supplier_article") or oc_line.get("vs_article") or "")
    if not oc_sup:
        return None
    for pl in po_lines:
        if _norm_article(pl.get("original_supplier_article") or "") == oc_sup:
            return pl
        if _norm_article(pl.get("vs_article") or "") == oc_sup:
            return pl
    return None


def _match_so_line(so_lines, vs_hint):
    """Match SO line by VS article ID hint from PO line."""
    if not so_lines or not vs_hint:
        return None
    hint = _norm_article(vs_hint)
    for sl in so_lines:
        if _norm_article(sl.get("vs_article") or "") == hint:
            return sl
    return None


# ── OC structure detection ────────────────────────────────────────────────────

def _detect_pattern(oc_lines, po_lines):
    """
    Pattern A: 1-to-1 match (normal)
    Pattern B: OC has fewer lines (supplier combined some)
    Pattern C: OC has 1 line representing total PO weight
    """
    oc_count = len(oc_lines)
    po_count = len(po_lines)

    if oc_count == 0 or po_count == 0:
        return "A"

    if oc_count >= po_count:
        return "A"

    # Check Pattern C: 1 OC line, weight ≈ sum of PO lines
    if oc_count == 1:
        oc_qty = _to_float(oc_lines[0].get("quantity"))
        po_total = sum(_to_float(pl.get("product_qty") or 0) or 0 for pl in po_lines)
        if oc_qty and po_total:
            diff_pct = abs(oc_qty - po_total) / po_total * 100 if po_total else 100
            if diff_pct <= 0.5:
                return "C"

    return "B"


# ── Individual field comparisons ──────────────────────────────────────────────

def _field(key, label, status, odoo_val, oc_val=None, note=None):
    return {
        "key":    key,
        "label":  label,
        "status": status,      # "match" | "mismatch" | "skip" | "na"
        "odoo":   str(odoo_val) if odoo_val not in (None, "", False) else "—",
        "oc":     str(oc_val)   if oc_val   not in (None, "", False) else "—",
        "note":   note or "",
    }


def _compare_numeric(key, label, odoo_val, oc_val, tolerance_pct=None, tolerance_abs=None):
    o = _to_float(odoo_val)
    c = _to_float(oc_val)
    if c is None:
        return _field(key, label, "skip", o, None)
    if o is None:
        return _field(key, label, "skip", None, c)
    if tolerance_abs is not None:
        ok = abs(o - c) <= tolerance_abs
    elif tolerance_pct is not None:
        ok = (_pct_diff(o, c) or 0) <= tolerance_pct
    else:
        ok = abs(o - c) < 1e-9
    return _field(key, label, "match" if ok else "mismatch", o, c)


def _compare_text(key, label, odoo_val, oc_val):
    o = _norm(odoo_val)
    c = _norm(oc_val)
    if not c:
        return _field(key, label, "skip", o or "—", None)
    if not o:
        return _field(key, label, "skip", "—", c)
    ok = o.lower() == c.lower()
    return _field(key, label, "match" if ok else "mismatch", o, c)


# ── Per-line comparison ───────────────────────────────────────────────────────

def _compare_line(oc_line, po_line, so_line, cfg):
    comp = cfg.get("comparison", {})
    results = []

    # Resolve values: SO fields take precedence for spec fields; PO for price/qty
    def so(field):
        return so_line.get(field) if so_line else None

    # 1. FORM
    oc_form = _norm(oc_line.get("form"))
    odoo_form = _norm(so("form"))
    if not oc_form:
        results.append(_field("form", "Form", "skip", odoo_form or "—", None))
    else:
        ok = oc_form.lower() == odoo_form.lower() if odoo_form else False
        results.append(_field("form", "Form", "match" if ok else "mismatch", odoo_form or "—", oc_form))

    # 2. QUALITY CHOICE
    oc_q = _norm(oc_line.get("quality_choice"))
    odoo_q = _norm(so("choice"))
    if not oc_q:
        results.append(_field("quality_choice", "Quality Choice", "skip", odoo_q or "—", None))
    else:
        ok = oc_q.lower() == odoo_q.lower() if odoo_q else False
        results.append(_field("quality_choice", "Quality Choice", "match" if ok else "mismatch", odoo_q or "—", oc_q))

    # 3. GRADE (handle combined grade+coating strings like DX51D+Z275)
    oc_grade_raw = _norm(oc_line.get("grade"))
    oc_grade, oc_coating_from_grade = _split_grade_coating(oc_grade_raw)
    odoo_grade = _norm(so("grade") or (po_line.get("name","") if po_line else ""))
    note = f"[OC: {oc_grade_raw} — coating suffix stripped]" if oc_coating_from_grade else ""
    if not oc_grade:
        results.append(_field("grade", "Grade", "skip", odoo_grade or "—", None))
    else:
        ok = oc_grade.lower() == odoo_grade.lower() if odoo_grade else False
        results.append(_field("grade", "Grade", "match" if ok else "mismatch", odoo_grade or "—", oc_grade, note))

    # 4. FINISH
    oc_finish = _norm(oc_line.get("finish"))
    odoo_finish = _norm(so("finish"))
    if not oc_finish:
        results.append(_field("finish", "Finish", "skip", odoo_finish or "—", None))
    else:
        ok = oc_finish.lower() == odoo_finish.lower() if odoo_finish else False
        results.append(_field("finish", "Finish", "match" if ok else "mismatch", odoo_finish or "—", oc_finish))

    # 5. COATING (use extracted coating OR coating suffix from grade string)
    oc_coating = _norm(oc_line.get("coating")) or oc_coating_from_grade or ""
    odoo_coating = _norm(so("coating"))
    if not oc_coating:
        results.append(_field("coating", "Coating", "skip", odoo_coating or "—", None))
    else:
        ok = oc_coating.lower() == odoo_coating.lower() if odoo_coating else False
        results.append(_field("coating", "Coating", "match" if ok else "mismatch", odoo_coating or "—", oc_coating))

    # 6. QUANTITY
    odoo_qty = po_line.get("product_qty") if po_line else None
    oc_qty = oc_line.get("quantity")
    results.append(_compare_numeric("qty", "Quantity", odoo_qty, oc_qty,
                                    tolerance_pct=comp.get("quantity_tolerance_pct", 0.5)))

    # 7. NUMBER OF ITEMS
    odoo_items = so("no_of_items")
    oc_items = oc_line.get("no_of_items")
    if oc_items is None:
        results.append(_field("no_of_items", "# of Items", "skip", odoo_items or "—", None))
    else:
        ok = int(_to_float(odoo_items) or 0) == int(_to_float(oc_items) or 0) if odoo_items else False
        results.append(_field("no_of_items", "# of Items", "match" if ok else "mismatch",
                               odoo_items or "—", oc_items))

    # 8. UNIT PRICE (from PO line)
    odoo_price = po_line.get("price_unit") if po_line else None
    oc_price = oc_line.get("unit_price")
    results.append(_compare_numeric("price", "Unit Price", odoo_price, oc_price,
                                    tolerance_pct=comp.get("price_tolerance_pct", 1.0)))

    # 9. THICKNESS
    odoo_thick = so("thickness")
    oc_thick = oc_line.get("thickness")
    results.append(_compare_numeric("thickness", "Thickness", odoo_thick, oc_thick,
                                    tolerance_abs=comp.get("thickness_tolerance_mm", 0.05)))

    # 10. WIDTH
    odoo_width = so("width")
    oc_width = oc_line.get("width")
    results.append(_compare_numeric("width", "Width", odoo_width, oc_width,
                                    tolerance_abs=comp.get("width_tolerance_mm", 5.0)))

    # 11. LENGTH (N/A for coils)
    oc_form_lower = (oc_form or _norm(so("form") or "")).lower()
    is_coil = any(w in oc_form_lower for w in ["coil","bund","coils","spule","rolle","bobine","breitband","vzc","spaltband"])
    if is_coil:
        results.append(_field("length", "Length", "na", "N/A (coil)", "N/A (coil)"))
    else:
        odoo_len = so("length")
        oc_len = oc_line.get("length")
        results.append(_compare_numeric("length", "Length", odoo_len, oc_len,
                                        tolerance_abs=comp.get("length_tolerance_mm", 10.0)))

    # 12. TENSILE STRENGTH
    odoo_ts = so("tensile_strength")
    oc_ts = oc_line.get("tensile_strength")
    if oc_ts is None:
        results.append(_field("tensile_strength", "Tensile Strength", "skip", odoo_ts or "—", None))
    else:
        results.append(_compare_numeric("tensile_strength", "Tensile Strength", odoo_ts, oc_ts,
                                        tolerance_abs=comp.get("tensile_strength_tolerance", 0.0)))

    # Sort: mismatches first, then matches, then skip, then na
    order = {"mismatch": 0, "match": 1, "skip": 2, "na": 3}
    results.sort(key=lambda f: order.get(f["status"], 9))

    mismatches = sum(1 for f in results if f["status"] == "mismatch")
    verified = [f for f in results if f["status"] not in ("skip", "na")]
    score = sum(1 for f in verified if f["status"] == "match")

    return {
        "fields":    results,
        "mismatches": mismatches,
        "score":     score,
        "total":     len(verified),
    }


# ── Part 2: Commercial flags ──────────────────────────────────────────────────

def _build_flags(oc_data, po_data, so_data, odoo_shipping_address):
    flags = []

    # Flag A — Pickup address
    oc_addr = _norm(oc_data.get("pickup_address"))
    if oc_addr:
        odoo_addr = _norm(odoo_shipping_address or "")
        same = oc_addr.lower() == odoo_addr.lower() if odoo_addr else False
        flags.append({
            "type":    "pickup_address",
            "icon":    "📍",
            "label":   "Pickup Address",
            "oc":      oc_addr,
            "odoo":    odoo_addr or "—",
            "warning": not same,
        })

    # Flag C — Incoterms (only if mismatch)
    oc_inco = _norm(oc_data.get("incoterm"))
    po_inco = ""
    if po_data and po_data.get("incoterm_id"):
        po_inco = po_data["incoterm_id"][1] if isinstance(po_data["incoterm_id"], (list, tuple)) else str(po_data["incoterm_id"])
    if oc_inco and po_inco:
        # Extract just the code (first word) for comparison
        oc_code = oc_inco.split()[0].upper()
        po_code = po_inco.split()[0].upper()
        if oc_code != po_code:
            flags.append({
                "type":    "incoterms",
                "icon":    "⚠️",
                "label":   "Incoterms MISMATCH",
                "oc":      oc_inco,
                "odoo":    po_inco,
                "warning": True,
            })

    # Flag D — Payment terms (only if mismatch)
    oc_pay = _norm(oc_data.get("payment_terms"))
    po_pay = ""
    if po_data and po_data.get("payment_term_id"):
        po_pay = po_data["payment_term_id"][1] if isinstance(po_data["payment_term_id"], (list, tuple)) else str(po_data["payment_term_id"])
    if oc_pay and po_pay:
        if oc_pay.lower() != po_pay.lower():
            flags.append({
                "type":    "payment_terms",
                "icon":    "⚠️",
                "label":   "Payment Terms MISMATCH",
                "oc":      oc_pay,
                "odoo":    po_pay,
                "warning": True,
            })

    # Flag F — VAT (always show if present)
    vat_pct = _norm(oc_data.get("vat_pct"))
    net = _to_float(oc_data.get("total_amount"))
    gross = _to_float(oc_data.get("gross_amount"))
    if vat_pct and (net or gross):
        flags.append({
            "type":  "vat",
            "icon":  "🧾",
            "label": "VAT",
            "vat_pct": vat_pct,
            "net":   net,
            "gross": gross,
            "warning": False,
        })

    return flags


# ── Main compare entry point ──────────────────────────────────────────────────

def compare(oc_data, po_data, po_lines, so_data, so_lines, config,
            odoo_shipping_address=None):
    """
    Compare OC data against Odoo PO/SO.
    Returns result dict consumed by post_slack.post_oc_result().
    """
    oc_lines = oc_data.get("lines") or oc_data.get("line_items", [])
    pattern  = _detect_pattern(oc_lines, po_lines)

    line_results = []
    total_mismatches = 0

    if pattern in ("B", "C"):
        # Cannot do per-line spec comparison — just record pattern
        line_results = []
    else:
        for ol in oc_lines:
            pl = _match_po_line(ol, po_lines)
            pl_vs = pl.get("vs_article", "") if pl else ""
            sl = _match_so_line(so_lines, pl_vs) if so_lines else None

            vs_id = pl_vs or _norm(ol.get("vs_article") or ol.get("supplier_article") or "?")
            lr = _compare_line(ol, pl, sl, config)
            lr["vs_id"] = vs_id
            lr["oc_line"] = ol
            total_mismatches += lr["mismatches"]
            line_results.append(lr)

    # Part 2 flags
    flags = _build_flags(oc_data, po_data, so_data, odoo_shipping_address)

    is_match = (total_mismatches == 0 and pattern == "A")

    return {
        "po_name":        po_data.get("name", "?") if po_data else "?",
        "so_name":        so_data.get("name", "—") if so_data else "—",
        "supplier":       (po_data["partner_id"][1] if po_data and po_data.get("partner_id") else
                           oc_data.get("supplier_name", "?")),
        "buyer":          (so_data["partner_id"][1] if so_data and so_data.get("partner_id") else "—"),
        "oc_ref":         oc_data.get("supplier_order_num", "—"),
        "confirmation_date": oc_data.get("confirmation_date", "—"),
        "is_match":       is_match,
        "total_mismatches": total_mismatches,
        "pattern":        pattern,
        "line_results":   line_results,
        "flags":          flags,
        "oc_data":        oc_data,
    }
