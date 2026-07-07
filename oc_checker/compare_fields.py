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
    # Handle coatings like Z275, ZE75/75AO, AS120, ZM310, AZ150, GI50/50
    m = re.match(r'^(.+?)\+((ZM|ZF|ZA|AZ|ZE|AS|AL|GI|Z)[\d/A-Za-z]*)\s*$',
                 grade_str.strip(), re.IGNORECASE)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return grade_str, None


# ── Line matching ─────────────────────────────────────────────────────────────

def _norm_article(v):
    return re.sub(r'[\s\-_]', '', _norm(v)).upper()


def _match_po_line(oc_line, po_lines):
    """
    Match OC line to PO line.

    Lookup order (most-specific first):
      1. oc supplier_article / vs_article  →  Odoo original_supplier_article
      2. oc supplier_article / vs_article  →  Odoo vs_article
      3. oc supplier_article / vs_article  →  Odoo aoo_fast_number
      4. oc coil_number                    →  Odoo original_supplier_article
      5. oc coil_number                    →  Odoo vs_article

    The coil_number path handles cases where Docsumo extracts the position
    code (e.g. "52101848") as vs_article but the real coil ref is in the
    separate coil_number field (e.g. "F900258989").
    """
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


def _is_positional_id(oc_lines):
    """Return True if all OC line IDs are just sequential integers (1,2,3…) — no real article codes."""
    ids = [str(ol.get("supplier_article") or ol.get("vs_article") or "").strip() for ol in oc_lines]
    try:
        nums = [int(x) for x in ids if x]
        return nums == list(range(1, len(nums)+1))
    except (ValueError, TypeError):
        return False


def _match_so_line(so_lines, vs_hint):
    """Match SO line by VS article ID hint from PO line."""
    if not so_lines or not vs_hint:
        return None
    hint = _norm_article(vs_hint)
    for sl in so_lines:
        if _norm_article(sl.get("vs_article") or "") == hint:
            return sl
    return None


# Thyssenkrupp coil-reference patterns found in OC line descriptions:
#   R90R903740  Z90R903740  (letter + 2-digit + letter + 6-digit)
#   F900258989  F900186174  (F + 9 digits)
_COIL_REF_RE = re.compile(
    r'\b([A-Z]\d{2}[A-Z]\d{6}|F\d{9})\b',
    re.IGNORECASE
)


def _extract_coil_refs(oc_line):
    """
    Extract all coil references from an OC line's vs_article,
    supplier_article, coil_number, and description fields.

    Used to detect multi-coil OC lines where the supplier lists N coils
    under a single line item (all same spec, one line in the OC, N Odoo PO
    lines).  Returns a list of normalised refs in order, deduplicated.
    """
    seen = set()
    refs = []

    def _add(v):
        n = _norm_article(v)
        if n and n not in seen:
            seen.add(n)
            refs.append(n)

    # Explicit article fields first
    for field in ("vs_article", "supplier_article", "coil_number"):
        val = oc_line.get(field) or ""
        # Only add if it looks like a real coil ref, not a position code
        if _COIL_REF_RE.fullmatch(val.strip()):
            _add(val)

    # Scan description for embedded coil refs
    desc = oc_line.get("description") or ""
    for m in _COIL_REF_RE.finditer(desc):
        _add(m.group(1))

    return refs


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


def _parse_date(v):
    """Truncate a date or datetime string to YYYY-MM-DD for comparison."""
    if not v:
        return None
    return str(v).strip()[:10]  # "2026-08-15 00:00:00" → "2026-08-15"


def _compare_date(key, label, odoo_val, oc_val):
    """Compare date fields; missing OC date = skip (not mismatch)."""
    o = _parse_date(odoo_val)
    c = _parse_date(oc_val)
    if c is None:
        return _field(key, label, "skip", o or "—", None)
    if o is None:
        return _field(key, label, "skip", "—", c)
    return _field(key, label, "match" if o == c else "mismatch", o, c)


# ── Per-line comparison ───────────────────────────────────────────────────────

def _compare_line(oc_line, po_line, so_line, cfg, skip_qty=False, group_note=None):
    """
    Compare one OC line against the matched Odoo PO/SO line.

    skip_qty   — True for lines that belong to a multi-coil group: the OC
                 weight is a group total, not per-coil, so individual qty
                 comparison is meaningless.
    group_note — Human-readable note added to the qty field when skip_qty
                 is True (e.g. "Part of 4-coil group · OC total 4.354 MT").
    """
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

    # 2–3, 5. QUALITY CHOICE / GRADE / COATING — cross-field aware
    #
    # Odoo stores grade, coating, and choice as three separate fields.
    # Supplier OCs often put any of these values in any field — e.g. the
    # grade value might appear in the quality_choice column, the coating
    # might be embedded in the grade string (DX51D+Z275), or the choice
    # label might end up in the grade field.
    #
    # Strategy: build a pool of all non-empty OC spec values and, for each
    # Odoo value, first check the corresponding OC field (direct match), then
    # fall back to the pool (cross-field match).  A cross-field match is still
    # counted as confirmed — the supplier DID confirm the right value, just in
    # the wrong column.

    oc_grade_raw         = _norm(oc_line.get("grade"))
    oc_grade, oc_coating_from_grade = _split_grade_coating(oc_grade_raw)
    oc_coating           = _norm(oc_line.get("coating")) or oc_coating_from_grade or ""
    oc_q                 = _norm(oc_line.get("quality_choice"))

    odoo_grade   = _norm(so("grade") or (po_line.get("name","") if po_line else ""))
    odoo_coating = _norm(so("coating"))
    odoo_q       = _norm(so("choice"))

    # OC spec pool: normalised-lower value → field name it came from (first wins)
    _oc_spec = {}
    for _fn, _fv in [("grade", oc_grade), ("coating", oc_coating), ("quality_choice", oc_q)]:
        if _fv:
            _oc_spec.setdefault(_fv.lower(), _fn)

    def _spec_field(key, label, odoo_val, oc_primary, primary_name, extra_note=""):
        """
        Compare one spec field with cross-field fallback.
        odoo_val     — what Odoo has
        oc_primary   — what the OC put in the corresponding field
        primary_name — display name of that OC field (for notes)
        """
        if not odoo_val:
            return _field(key, label, "skip", "—", oc_primary or None)
        if not _oc_spec:                          # OC sent no spec at all
            return _field(key, label, "skip", odoo_val, None)
        odoo_norm = odoo_val.lower()
        if not oc_primary:                        # primary OC field empty
            if odoo_norm in _oc_spec:
                found = _oc_spec[odoo_norm]
                note = f"cross-field: found in OC {found}"
                if extra_note:
                    note = extra_note + "; " + note
                return _field(key, label, "match", odoo_val, odoo_val, note)
            return _field(key, label, "skip", odoo_val, None)
        if oc_primary.lower() == odoo_norm:       # direct match
            return _field(key, label, "match", odoo_val, oc_primary, extra_note)
        if odoo_norm in _oc_spec:                 # cross-field match
            found = _oc_spec[odoo_norm]
            note = f"cross-field: found in OC {found} (OC {primary_name}: {oc_primary})"
            if extra_note:
                note = extra_note + "; " + note
            return _field(key, label, "match", odoo_val, odoo_val, note)
        return _field(key, label, "mismatch", odoo_val, oc_primary, extra_note)

    strip_note = f"OC grade field: '{oc_grade_raw}' — coating suffix stripped" if oc_coating_from_grade else ""
    results.append(_spec_field("grade",          "Grade",          odoo_grade,   oc_grade,   "grade",          strip_note))
    results.append(_spec_field("quality_choice", "Quality Choice", odoo_q,       oc_q,       "quality_choice"))
    results.append(_spec_field("coating",        "Coating",        odoo_coating, oc_coating, "coating"))

    # 4. FINISH (not part of cross-field spec pool — different semantics)
    oc_finish = _norm(oc_line.get("finish"))
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
        note = group_note or "qty is group total — checked at group level"
        results.append(_field("qty", "Quantity", "skip", odoo_qty or "—", oc_qty, note))
    else:
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

    # 13. DELIVERY DATE (from PO line date_planned vs OC per-line delivery_date)
    odoo_delivery = po_line.get("date_planned") if po_line else None
    oc_delivery   = oc_line.get("delivery_date")
    results.append(_compare_date("delivery_date", "Delivery Date", odoo_delivery, oc_delivery))

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

    # Pattern B fires when the OC has fewer lines than the PO. But this also
    # happens legitimately when a supplier sends one OC file per item (e.g.
    # Bilstein: 5 separate OC PDFs each with 1 line, for a 5-line PO), or
    # when a multi-coil OC covers only a subset of a large PO.
    # Before giving up on per-line comparison, check whether the OC lines can
    # be matched to specific PO lines via article number OR coil refs in the
    # description. If any match found, treat as Pattern A.
    if pattern == "B":
        def _any_match(oc_lines, po_lines):
            for ol in oc_lines:
                if _match_po_line(ol, po_lines):
                    return True
                for ref in _extract_coil_refs(ol):
                    if _match_po_line({"vs_article": ref, "supplier_article": ref}, po_lines):
                        return True
            return False
        if _any_match(oc_lines, po_lines):
            pattern = "A"

    line_results = []
    total_mismatches = 0

    if pattern in ("B", "C"):
        # Genuine aggregation — cannot do per-line spec comparison
        line_results = []
    else:
        # Use positional matching if OC lines have no real article IDs (e.g. 1, 2, 3)
        use_positional = _is_positional_id(oc_lines) or not any(
            _match_po_line(ol, po_lines) for ol in oc_lines
        )

        # Track PO line IDs already assigned so the same physical PO line is
        # never matched twice (e.g. once via primary article and again via
        # description-extracted coil ref from another OC line).
        assigned_po_ids = set()

        for idx, ol in enumerate(oc_lines):
            if use_positional:
                # Simple 1-to-1 positional mapping
                pl = po_lines[idx] if idx < len(po_lines) else None
                matched_po_lines = [pl] if pl else []
                if pl and pl.get("id"):
                    assigned_po_ids.add(pl["id"])
            else:
                # -----------------------------------------------------------
                # Multi-coil group expansion
                #
                # Step 1: collect all coil refs present in this OC line
                #         (vs_article, coil_number, and refs embedded in
                #         the description text like "R90R904232 R90R904233").
                # Step 2: for each ref, find the matching Odoo PO line.
                # Step 3: deduplicate (skip refs already assigned to earlier
                #         OC lines) and build the group.
                #
                # If N refs resolve to N PO lines → multi-coil group:
                #   - all lines get the same spec comparison (grade/dims/price)
                #   - qty comparison is SKIPPED (OC weight is the group total,
                #     not the individual coil weight)
                # If only 1 PO line resolves → single coil, qty compared normally.
                # -----------------------------------------------------------
                coil_refs = _extract_coil_refs(ol)

                # Build ordered list of matched PO lines (no duplicates)
                matched_po_lines = []
                for ref in coil_refs:
                    synthetic = {"vs_article": ref, "supplier_article": ref}
                    apl = _match_po_line(synthetic, po_lines)
                    if apl is not None:
                        apl_id = apl.get("id")
                        if apl_id not in assigned_po_ids:
                            matched_po_lines.append(apl)
                            assigned_po_ids.add(apl_id)

                # Fall back to plain article match if description parsing
                # found nothing (e.g. refs not yet in Odoo's fields)
                if not matched_po_lines:
                    pl = _match_po_line(ol, po_lines)
                    if pl:
                        pl_id = pl.get("id")
                        if pl_id not in assigned_po_ids:
                            matched_po_lines = [pl]
                            assigned_po_ids.add(pl_id)

            is_multi_coil = len(matched_po_lines) > 1
            oc_qty        = ol.get("quantity")
            group_note    = None
            if is_multi_coil:
                group_note = "Part of %d-coil group · OC total %s MT" % (
                    len(matched_po_lines),
                    str(oc_qty) if oc_qty is not None else "?"
                )

            if not matched_po_lines:
                # OC line could not be matched to any PO line
                vs_id = _norm(ol.get("vs_article") or ol.get("supplier_article") or "?")
                lr = _compare_line(ol, None, None, config)
                lr["vs_id"]   = vs_id
                lr["oc_line"] = ol
                total_mismatches += lr["mismatches"]
                line_results.append(lr)
            else:
                for match_pl in matched_po_lines:
                    pl_vs = (match_pl.get("vs_article") or "") if match_pl else ""
                    sl    = _match_so_line(so_lines, pl_vs) if so_lines else None
                    vs_id = pl_vs or _norm(
                        ol.get("vs_article") or ol.get("supplier_article") or "?")

                    lr = _compare_line(ol, match_pl, sl, config,
                                       skip_qty=is_multi_coil,
                                       group_note=group_note)
                    lr["vs_id"]   = vs_id
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
