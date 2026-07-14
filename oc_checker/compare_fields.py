"""
OC vs Odoo field comparison — Vanilla Steel.

Part 1 — per-line spec matching (12 fields, delivery date excluded)
Part 2 — commercial flags (incoterms, payment terms, VAT, pickup address)

Line matching — four strategies tried in order for each OC line:
  1. Code match     — supplier_article / vs_article / coil_number → Odoo codes
  2. Qty match      — OC weight ≈ PO product_qty within tolerance (order-independent)
  3. Spec-group     — OC grade+thickness+width matches a group of PO lines whose
                      combined qty ≈ OC qty; handles suppliers that bundle same-spec
                      coils into one OC position (e.g. TK Accelis)
  4. Positional     — take the next unassigned PO line in order (last resort; always
                      produces a result so the user sees mismatches rather than silence)
  → Truly unmatched — only if there are more OC lines than unassigned PO lines remain

Match count rules:
  - Both sides empty              → excluded from count entirely
  - One side has value, other not → counted in denominator only
  - Both have values, match       → numerator + denominator
  - Both have values, differ      → denominator only
"""

import re


# ── Helpers ───────────────────────────────────────────────────────────────────

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
    if not grade_str:
        return grade_str, None
    m = re.match(r'^(.+?)\+((ZM|ZF|ZA|AZ|ZE|AS|AL|GI|Z)[\d/A-Za-z]*)\s*$',
                 grade_str.strip(), re.IGNORECASE)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return grade_str, None


# ── Incoterm helpers ──────────────────────────────────────────────────────────

def _extract_inco_code(s):
    if not s:
        return ""
    s = s.strip()
    m = re.search(r'\[([A-Z]{3})\]', s, re.IGNORECASE)
    if m:
        return m.group(1).upper()
    words = s.split()
    if words and re.match(r'^[A-Z]{3}$', words[0], re.IGNORECASE):
        return words[0].upper()
    _ALIASES = {
        "FREE CARRIER": "FCA", "FREI FRACHTFÜHRER": "FCA", "FRANCO VETTORE": "FCA",
        "DELIVERED AT PLACE": "DAP", "GELIEFERT BENANNTER ORT": "DAP",
        "DELIVERED DUTY PAID": "DDP", "FREI HAUS": "DDP", "GELIEFERT VERZOLLT": "DDP",
        "COST INSURANCE AND FREIGHT": "CIF", "COST, INSURANCE AND FREIGHT": "CIF",
        "CARRIAGE PAID TO": "CPT", "FRACHTFREI": "CPT",
        "EX WORKS": "EXW", "AB WERK": "EXW", "EX USINE": "EXW",
        "FREE ON BOARD": "FOB", "COST AND FREIGHT": "CFR",
        "CARRIAGE AND INSURANCE PAID TO": "CIP", "DELIVERED AT PLACE UNLOADED": "DPU",
    }
    key = re.sub(r'[^A-Z ]', '', s.upper()).strip()
    if key in _ALIASES:
        return _ALIASES[key]
    for w in words:
        w_clean = re.sub(r'[^A-Za-z]', '', w)
        if re.match(r'^[A-Z]{3}$', w_clean, re.IGNORECASE):
            return w_clean.upper()
    return words[0].upper() if words else ""


def _extract_days(s):
    if not s:
        return None
    if re.search(r'\b(sofort|immediate|immediately|sofortfällig)\b', s, re.IGNORECASE):
        return 0
    m = re.search(r'\b(\d+)\s*(?:tage[n]?|days?|giorni|jours?|dagen|días?)\b', s, re.IGNORECASE)
    if m:
        return int(m.group(1))
    m = re.search(r'\b(?:tage[n]?|days?|giorni|jours?|dagen)\s*(\d+)\b', s, re.IGNORECASE)
    if m:
        return int(m.group(1))
    m = re.search(r'\b(\d+)\b', s)
    if m:
        return int(m.group(1))
    return None


# ── Article code matching ─────────────────────────────────────────────────────

def _norm_article(v):
    return re.sub(r'[\s\-_]', '', _norm(v)).upper()


def _match_po_line(oc_line, po_lines):
    """Match OC line to PO line by article code (most-specific first)."""
    oc_sup  = _norm_article(oc_line.get("supplier_article") or oc_line.get("vs_article") or "")
    oc_coil = _norm_article(oc_line.get("coil_number") or "")
    if not oc_sup and not oc_coil:
        return None
    for pl in po_lines:
        pl_orig = _norm_article(pl.get("original_supplier_article") or "")
        pl_vs   = _norm_article(pl.get("vs_article") or "")
        pl_aoo  = _norm_article(pl.get("aoo_fast_number") or "")
        if oc_sup and (pl_orig == oc_sup or pl_vs == oc_sup or pl_aoo == oc_sup):
            return pl
        if oc_coil and (pl_orig == oc_coil or pl_vs == oc_coil):
            return pl
    return None


_COIL_REF_RE = re.compile(r'\b([A-Z]\d{2}[A-Z]\d{6}|F\d{9})\b', re.IGNORECASE)


def _extract_coil_refs(oc_line):
    """Extract all coil references from vs_article, supplier_article, coil_number, description."""
    seen, refs = set(), []
    def _add(v):
        n = _norm_article(v)
        if n and n not in seen:
            seen.add(n)
            refs.append(n)
    for field in ("vs_article", "supplier_article", "coil_number"):
        val = oc_line.get(field) or ""
        if _COIL_REF_RE.fullmatch(val.strip()):
            _add(val)
    for m in _COIL_REF_RE.finditer(oc_line.get("description") or ""):
        _add(m.group(1))
    return refs


# ── Qty-based matching (Strategy 2) ──────────────────────────────────────────

def _match_po_line_by_qty(oc_line, po_lines, assigned_ids, tol_pct=0.5):
    """
    Match an OC line to the closest unassigned PO line by weight.
    Order-independent — handles suppliers whose OC line order differs from Odoo.
    Returns the best-matching PO line, or None.
    """
    oc_qty = _to_float(oc_line.get("quantity"))
    if oc_qty is None:
        return None
    best, best_diff = None, float("inf")
    for pl in po_lines:
        if pl.get("id") in assigned_ids:
            continue
        po_qty = _to_float(pl.get("product_qty"))
        if po_qty is None:
            continue
        diff = abs(oc_qty - po_qty) / po_qty * 100 if po_qty else 100
        if diff <= tol_pct and diff < best_diff:
            best, best_diff = pl, diff
    return best


# ── Spec-group matching (Strategy 3) ─────────────────────────────────────────

def _match_po_lines_by_spec(oc_line, po_lines, so_lines, assigned_ids,
                             thick_tol=0.05, width_tol=5.0, qty_tol_pct=2.0):
    """
    Match one OC line to a GROUP of PO lines that share the same spec.

    Used when a supplier bundles multiple coils of identical grade/thickness/width
    into a single OC position (e.g. TK Accelis: one line for 9 slit coils).

    Steps:
      1. Find all unassigned PO lines whose linked SO line spec matches the OC line
         (grade, thickness, width — within tolerances)
      2. Check that the OC line's qty ≈ the group's combined qty (within qty_tol_pct)
      3. Only return the group if both spec AND total qty match

    Returns (matched_po_lines, qty_matched: bool)
    """
    oc_grade_raw = _norm(oc_line.get("grade") or "")
    oc_grade, _  = _split_grade_coating(oc_grade_raw)
    oc_thick     = _to_float(oc_line.get("thickness"))
    oc_width     = _to_float(oc_line.get("width"))
    oc_qty       = _to_float(oc_line.get("quantity"))

    # Need at least grade or a dimension to match on
    if not oc_grade and oc_thick is None and oc_width is None:
        return [], False

    # Build SO line lookup: normalised vs_article → so_line
    so_by_vs = {}
    for sl in (so_lines or []):
        key = _norm_article(sl.get("vs_article") or "")
        if key:
            so_by_vs[key] = sl

    candidates = []
    for pl in po_lines:
        if pl.get("id") in assigned_ids:
            continue
        sl = so_by_vs.get(_norm_article(pl.get("vs_article") or ""))
        if sl is None:
            continue

        sl_grade_raw = _norm(sl.get("grade") or "")
        sl_grade, _  = _split_grade_coating(sl_grade_raw)
        sl_thick     = _to_float(sl.get("thickness"))
        sl_width     = _to_float(sl.get("width"))

        # Grade must match (if both present)
        if oc_grade and sl_grade:
            if oc_grade.upper() != sl_grade.upper():
                continue

        # Thickness must match within tolerance (if both present)
        if oc_thick is not None and sl_thick is not None:
            if abs(oc_thick - sl_thick) > thick_tol:
                continue

        # Width must match within tolerance (if both present)
        if oc_width is not None and sl_width is not None:
            if abs(oc_width - sl_width) > width_tol:
                continue

        candidates.append(pl)

    if not candidates:
        return [], False

    # Only useful for groups of 2+ (1-line case is already handled by qty-match)
    if len(candidates) < 2:
        return [], False

    # Check combined qty matches OC qty
    if oc_qty is None:
        return [], False
    group_total = sum(_to_float(pl.get("product_qty") or 0) or 0 for pl in candidates)
    if group_total <= 0:
        return [], False
    diff_pct = abs(oc_qty - group_total) / group_total * 100
    if diff_pct > qty_tol_pct:
        return [], False

    return candidates, True


# ── SO line lookup ────────────────────────────────────────────────────────────

def _match_so_line(so_lines, vs_hint):
    if not so_lines or not vs_hint:
        return None
    hint = _norm_article(vs_hint)
    for sl in so_lines:
        if _norm_article(sl.get("vs_article") or "") == hint:
            return sl
    return None


# ── Individual field comparisons ──────────────────────────────────────────────

def _field(key, label, status, odoo_val, oc_val=None, note=None):
    return {
        "key":    key,
        "label":  label,
        "status": status,
        "odoo":   str(odoo_val) if odoo_val not in (None, "", False) else "—",
        "oc":     str(oc_val)   if oc_val   not in (None, "", False) else "—",
        "note":   note or "",
    }


def _compare_numeric(key, label, odoo_val, oc_val, tolerance_pct=None, tolerance_abs=None):
    o, c = _to_float(odoo_val), _to_float(oc_val)
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


# ── Per-line comparison (12 fields) ──────────────────────────────────────────

def _compare_line(oc_line, po_line, so_line, cfg, skip_qty=False, group_note=None,
                  positional_fallback=False):
    """
    Compare one OC line against the matched Odoo PO/SO line.
    skip_qty=True when the OC qty is a group total (spec-group match).
    positional_fallback=True adds a note indicating no smart strategy matched.
    """
    comp    = cfg.get("comparison", {})
    results = []

    def so(field):
        return so_line.get(field) if so_line else None

    # 1. FORM
    oc_form   = _norm(oc_line.get("form"))
    odoo_form = _norm(so("form"))
    if not oc_form:
        results.append(_field("form", "Form", "skip", odoo_form or "—", None))
    else:
        ok = oc_form.lower() == odoo_form.lower() if odoo_form else False
        results.append(_field("form", "Form", "match" if ok else "mismatch", odoo_form or "—", oc_form))

    # 2–3, 5. GRADE / QUALITY CHOICE / COATING — cross-field aware
    oc_grade_raw             = _norm(oc_line.get("grade"))
    oc_grade, oc_coat_split  = _split_grade_coating(oc_grade_raw)
    oc_coating               = _norm(oc_line.get("coating")) or oc_coat_split or ""
    oc_q                     = _norm(oc_line.get("quality_choice"))
    odoo_grade               = _norm(so("grade") or (po_line.get("name","") if po_line else ""))
    odoo_coating             = _norm(so("coating"))
    odoo_q                   = _norm(so("choice"))

    _oc_spec = {}
    for _fn, _fv in [("grade", oc_grade), ("coating", oc_coating), ("quality_choice", oc_q)]:
        if _fv:
            _oc_spec.setdefault(_fv.lower(), _fn)

    def _spec_field(key, label, odoo_val, oc_primary, primary_name, extra_note=""):
        if not odoo_val:
            return _field(key, label, "skip", "—", oc_primary or None)
        if not _oc_spec:
            return _field(key, label, "skip", odoo_val, None)
        odoo_norm = odoo_val.lower()
        if not oc_primary:
            if odoo_norm in _oc_spec:
                return _field(key, label, "match", odoo_val, odoo_val,
                               ("cross-field: found in OC " + _oc_spec[odoo_norm] +
                                ("; " + extra_note if extra_note else "")))
            return _field(key, label, "skip", odoo_val, None)
        if oc_primary.lower() == odoo_norm:
            return _field(key, label, "match", odoo_val, oc_primary, extra_note)
        if odoo_norm in _oc_spec:
            return _field(key, label, "match", odoo_val, odoo_val,
                           ("cross-field: found in OC " + _oc_spec[odoo_norm] +
                            " (OC " + primary_name + ": " + oc_primary + ")" +
                            ("; " + extra_note if extra_note else "")))
        return _field(key, label, "mismatch", odoo_val, oc_primary, extra_note)

    strip_note = ("OC grade field: '%s' — coating suffix stripped" % oc_grade_raw
                  if oc_coat_split else "")
    results.append(_spec_field("grade",          "Grade",          odoo_grade,   oc_grade,   "grade",          strip_note))
    results.append(_spec_field("quality_choice", "Quality Choice", odoo_q,       oc_q,       "quality_choice"))
    results.append(_spec_field("coating",        "Coating",        odoo_coating, oc_coating, "coating"))

    # 4. FINISH
    oc_finish   = _norm(oc_line.get("finish"))
    odoo_finish = _norm(so("finish"))
    if not oc_finish:
        results.append(_field("finish", "Finish", "skip", odoo_finish or "—", None))
    else:
        ok = oc_finish.lower() == odoo_finish.lower() if odoo_finish else False
        results.append(_field("finish", "Finish", "match" if ok else "mismatch", odoo_finish or "—", oc_finish))

    # 6. QUANTITY
    odoo_qty = po_line.get("product_qty") if po_line else None
    oc_qty   = oc_line.get("quantity")
    if skip_qty:
        results.append(_field("qty", "Quantity", "skip", odoo_qty or "—", oc_qty,
                               group_note or "qty is group total — checked at group level"))
    else:
        results.append(_compare_numeric("qty", "Quantity", odoo_qty, oc_qty,
                                        tolerance_pct=comp.get("quantity_tolerance_pct", 0.5)))

    # 7. NUMBER OF ITEMS
    odoo_items = so("no_of_items")
    oc_items   = oc_line.get("no_of_items")
    if oc_items is None:
        results.append(_field("no_of_items", "# of Items", "skip", odoo_items or "—", None))
    else:
        ok = int(_to_float(odoo_items) or 0) == int(_to_float(oc_items) or 0) if odoo_items else False
        results.append(_field("no_of_items", "# of Items", "match" if ok else "mismatch",
                               odoo_items or "—", oc_items))

    # 8. UNIT PRICE
    odoo_price = po_line.get("price_unit") if po_line else None
    oc_price   = oc_line.get("unit_price")
    results.append(_compare_numeric("price", "Unit Price", odoo_price, oc_price,
                                    tolerance_pct=comp.get("price_tolerance_pct", 1.0)))

    # 9. THICKNESS
    results.append(_compare_numeric("thickness", "Thickness", so("thickness"), oc_line.get("thickness"),
                                    tolerance_abs=comp.get("thickness_tolerance_mm", 0.05)))

    # 10. WIDTH
    results.append(_compare_numeric("width", "Width", so("width"), oc_line.get("width"),
                                    tolerance_abs=comp.get("width_tolerance_mm", 5.0)))

    # 11. LENGTH (N/A for coils)
    oc_form_lower = (oc_form or _norm(so("form") or "")).lower()
    is_coil = any(w in oc_form_lower for w in
                  ["coil","bund","coils","spule","rolle","bobine","breitband","vzc","spaltband"])
    if is_coil:
        results.append(_field("length", "Length", "na", "N/A (coil)", "N/A (coil)"))
    else:
        results.append(_compare_numeric("length", "Length", so("length"), oc_line.get("length"),
                                        tolerance_abs=comp.get("length_tolerance_mm", 10.0)))

    # 12. TENSILE STRENGTH
    odoo_ts = so("tensile_strength")
    oc_ts   = oc_line.get("tensile_strength")
    if oc_ts is None:
        results.append(_field("tensile_strength", "Tensile Strength", "skip", odoo_ts or "—", None))
    else:
        results.append(_compare_numeric("tensile_strength", "Tensile Strength", odoo_ts, oc_ts,
                                        tolerance_abs=comp.get("tensile_strength_tolerance", 0.0)))

    order = {"mismatch": 0, "match": 1, "skip": 2, "na": 3}
    results.sort(key=lambda f: order.get(f["status"], 9))

    def _effective(f):
        if f["status"] == "na":
            return False
        if f["status"] == "skip" and "group" in (f.get("note") or "").lower():
            return False
        return not (f.get("odoo","—") in ("—","",None) and f.get("oc","—") in ("—","",None))

    effective  = [f for f in results if _effective(f)]
    mismatches = sum(1 for f in effective if f["status"] != "match")
    score      = sum(1 for f in effective if f["status"] == "match")

    extra_note = "positional fallback — no code/qty/spec match found" if positional_fallback else ""

    return {
        "fields":              results,
        "mismatches":          mismatches,
        "score":               score,
        "total":               len(effective),
        "positional_fallback": positional_fallback,
        "match_note":          extra_note,
    }


# ── Commercial flags ──────────────────────────────────────────────────────────

def _build_flags(oc_data, po_data, so_data, odoo_shipping_address):
    flags = []

    oc_addr = _norm(oc_data.get("pickup_address"))
    if oc_addr:
        odoo_addr = _norm(odoo_shipping_address or "")
        # Token overlap match: split both addresses into meaningful tokens and
        # check if enough of them appear in both (handles "FCA Woippy 57140 France"
        # vs "Chem Des Romains 20, 57140, Woippy, France" — city + zip overlap).
        def _addr_tokens(s):
            noise = {"fca","fob","exw","cpt","cip","dat","dap","ddp","free","carrier",
                     "address","delivery","street","str","road"}
            return {t for t in re.split(r'[\s,./]+', s.lower()) if len(t) >= 3 and t not in noise}
        if odoo_addr:
            oc_tok   = _addr_tokens(oc_addr)
            odoo_tok = _addr_tokens(odoo_addr)
            overlap  = oc_tok & odoo_tok
            same     = len(overlap) >= 2 or (len(overlap) == 1 and any(t.isdigit() for t in overlap))
        else:
            same = False
        flags.append({"type": "pickup_address", "icon": "📍", "label": "Pickup Address",
                       "oc": oc_addr, "odoo": odoo_addr or "—", "warning": not same})

    oc_inco, po_inco = _norm(oc_data.get("incoterm")), ""
    if po_data and po_data.get("incoterm_id"):
        po_inco = (po_data["incoterm_id"][1] if isinstance(po_data["incoterm_id"], (list,tuple))
                   else str(po_data["incoterm_id"]))
    if oc_inco and po_inco and _extract_inco_code(oc_inco) != _extract_inco_code(po_inco):
        flags.append({"type": "incoterms", "icon": "⚠️", "label": "Incoterms MISMATCH",
                       "oc": oc_inco, "odoo": po_inco, "warning": True})

    oc_pay, po_pay = _norm(oc_data.get("payment_terms")), ""
    if po_data and po_data.get("payment_term_id"):
        po_pay = (po_data["payment_term_id"][1] if isinstance(po_data["payment_term_id"], (list,tuple))
                  else str(po_data["payment_term_id"]))
    if oc_pay and po_pay:
        oc_days, po_days = _extract_days(oc_pay), _extract_days(po_pay)
        days_match = (oc_days == po_days) if (oc_days is not None and po_days is not None) \
                     else (oc_pay.lower() == po_pay.lower())
        if not days_match:
            flags.append({"type": "payment_terms", "icon": "⚠️", "label": "Payment Terms MISMATCH",
                           "oc": oc_pay, "odoo": po_pay, "warning": True})

    vat_pct = _norm(oc_data.get("vat_pct"))
    net     = _to_float(oc_data.get("total_amount"))
    gross   = _to_float(oc_data.get("gross_amount"))
    if vat_pct and (net or gross):
        flags.append({"type": "vat", "icon": "🧾", "label": "VAT",
                       "vat_pct": vat_pct, "net": net, "gross": gross, "warning": False})

    return flags


# ── Main compare entry point ──────────────────────────────────────────────────

def compare(oc_data, po_data, po_lines, so_data, so_lines, config,
            odoo_shipping_address=None):
    """
    Compare OC data against Odoo PO/SO.

    For each OC line, tries code → qty → spec-group → positional matching in order.
    Every OC line always gets a result (worst case: positional fallback shows mismatches).
    Returns result dict consumed by post_slack.build_po_status_text().
    """
    oc_lines        = oc_data.get("lines") or oc_data.get("line_items", [])
    comp            = config.get("comparison", {})
    qty_tol         = comp.get("quantity_tolerance_pct", 0.5)

    line_results     = []
    total_mismatches = 0
    assigned_po_ids  = set()

    # Ordered list of PO lines for Strategy 4 positional fallback
    unassigned_po_lines = list(po_lines)

    for oc_idx, ol in enumerate(oc_lines):
        matched_po_lines = []
        match_type       = None

        # ── Strategy 1: article code / coil ref matching ──────────────────────
        coil_refs = _extract_coil_refs(ol)
        for ref in coil_refs:
            apl = _match_po_line({"vs_article": ref, "supplier_article": ref}, po_lines)
            if apl and apl.get("id") not in assigned_po_ids:
                matched_po_lines.append(apl)
                assigned_po_ids.add(apl["id"])

        if not matched_po_lines:
            pl = _match_po_line(ol, po_lines)
            if pl and pl.get("id") not in assigned_po_ids:
                matched_po_lines = [pl]
                assigned_po_ids.add(pl["id"])

        if matched_po_lines:
            match_type = "code"
            for pl in matched_po_lines:
                if pl in unassigned_po_lines:
                    unassigned_po_lines.remove(pl)

        # ── Strategy 2: quantity (weight) matching ────────────────────────────
        if not matched_po_lines:
            pl = _match_po_line_by_qty(ol, po_lines, assigned_po_ids, tol_pct=qty_tol)
            if pl:
                matched_po_lines = [pl]
                assigned_po_ids.add(pl["id"])
                match_type = "qty"
                if pl in unassigned_po_lines:
                    unassigned_po_lines.remove(pl)

        # ── Strategy 3: spec-group matching ───────────────────────────────────
        if not matched_po_lines:
            group, qty_ok = _match_po_lines_by_spec(
                ol, po_lines, so_lines, assigned_po_ids,
                thick_tol=comp.get("thickness_tolerance_mm", 0.05),
                width_tol=comp.get("width_tolerance_mm", 5.0),
                qty_tol_pct=2.0,
            )
            if group:
                matched_po_lines = group
                for pl in group:
                    assigned_po_ids.add(pl["id"])
                    if pl in unassigned_po_lines:
                        unassigned_po_lines.remove(pl)
                match_type = "spec_group"

        # ── Strategy 4: positional fallback ───────────────────────────────────
        # Always produces a result — worst case the user sees field-level mismatches
        # rather than silence.
        if not matched_po_lines:
            remaining = [pl for pl in unassigned_po_lines
                         if pl.get("id") not in assigned_po_ids]
            if remaining:
                pl = remaining[0]
                matched_po_lines = [pl]
                assigned_po_ids.add(pl["id"])
                if pl in unassigned_po_lines:
                    unassigned_po_lines.remove(pl)
                match_type = "positional"
                print("  WARNING: OC line %d (qty=%s grade=%s) matched by position — "
                      "no code/qty/spec match found" % (
                          oc_idx + 1, ol.get("quantity"), ol.get("grade")))
            else:
                # More OC lines than PO lines — genuinely no line to compare against
                print("  WARNING: OC line %d (qty=%s) has no remaining PO line — "
                      "OC has more lines than the Odoo PO" % (
                          oc_idx + 1, ol.get("quantity")))
                continue

        # ── Build per-line comparison results ─────────────────────────────────
        is_group      = (match_type == "spec_group") or (len(matched_po_lines) > 1)
        is_positional = (match_type == "positional")
        group_note    = None
        if is_group:
            group_note = "Spec-group confirmed · OC total %s MT" % (
                str(ol.get("quantity")) if ol.get("quantity") is not None else "?")

        for match_pl in matched_po_lines:
            pl_vs = (match_pl.get("vs_article") or "") if match_pl else ""
            sl    = _match_so_line(so_lines, pl_vs) if so_lines else None
            vs_id = pl_vs or _norm(ol.get("vs_article") or ol.get("supplier_article") or "?")

            lr = _compare_line(ol, match_pl, sl, config,
                               skip_qty=is_group,
                               group_note=group_note,
                               positional_fallback=is_positional)
            lr["vs_id"]      = vs_id
            lr["oc_line"]    = ol
            lr["match_type"] = match_type
            total_mismatches += lr["mismatches"]
            line_results.append(lr)

    flags = _build_flags(oc_data, po_data, so_data, odoo_shipping_address)

    return {
        "po_name":           po_data.get("name", "?") if po_data else "?",
        "so_name":           so_data.get("name", "—") if so_data else "—",
        "supplier":          (po_data["partner_id"][1] if po_data and po_data.get("partner_id")
                              else oc_data.get("supplier_name", "?")),
        "buyer":             (so_data["partner_id"][1] if so_data and so_data.get("partner_id")
                              else "—"),
        "oc_ref":            oc_data.get("supplier_order_num", "—"),
        "confirmation_date": oc_data.get("confirmation_date", "—"),
        "is_match":          (total_mismatches == 0),
        "total_mismatches":  total_mismatches,
        "line_results":      line_results,
        "flags":             flags,
        "oc_data":           oc_data,
    }
