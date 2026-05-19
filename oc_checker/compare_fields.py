"""
Compare OC data against PO + SO data from Vanilla Steel Odoo.

13 fields per VS article line item (denominator always 13):
  1. Form              -> SO: form
  2. Quality Choice    -> SO: choice  (cross-matched from OC grade)
  3. Grade             -> SO: grade
  4. Finish            -> SO: finish
  5. Coating           -> SO: coating
  6. Actual Qty        -> PO: product_qty
  7. # of Items        -> SO: no_of_items
  8. Purchase Price    -> PO: price_unit
  9. Thickness         -> SO: thickness
  10. Width            -> SO: width
  11. Length           -> SO: length
  12. Tensile Strength -> SO: tensile_strength
  13. Description      -> PO: name
"""
import json, re, sys

TOTAL_FIELDS = 13

FIELD_LABELS = {
    "form": "Form", "quality_choice": "Quality Choice", "grade": "Grade",
    "finish": "Finish", "coating": "Coating", "qty": "Actual Qty",
    "no_of_items": "# of Items", "price": "Actual Purchase Unit Price",
    "thickness": "Thickness", "width": "Width", "length": "Length",
    "tensile_strength": "Tensile Strength", "description": "Description",
}

_QUALITY_NORM = {
    "prime": "Prime", "1st": "1st", "first": "1st", "first choice": "1st",
    "first quality": "1st", "2nd": "2nd", "second": "2nd",
    "second choice": "2nd", "second quality": "2nd", "2. wahl": "2nd",
    "3rd": "3rd", "third": "3rd", "third choice": "3rd",
    "4th": "4th", "fourth": "4th",
}
_MT_NAMES = {"mt", "t", "ton", "tonne", "tonnen", "to"}
_KG_NAMES = {"kg", "kgs", "kilogram", "kilogramm"}


def _to_float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None

def _pct_diff(a, b):
    a, b = _to_float(a), _to_float(b)
    if a is None or b is None or a == 0:
        return None
    return abs(a - b) / abs(a) * 100

def _abs_diff(a, b):
    a, b = _to_float(a), _to_float(b)
    if a is None or b is None:
        return None
    return abs(a - b)

def _norm(s):
    return re.sub(r"\s+", " ", str(s or "").strip().lower())

def _word_overlap(a, b):
    a, b = _norm(a), _norm(b)
    if not a or not b:
        return None
    aw = set(re.split(r"[\s\-/]+", a))
    bw = set(re.split(r"[\s\-/]+", b))
    return len(aw & bw) / len(aw) * 100 if aw else 0.0

def _strip_prefix(grade):
    if not grade:
        return grade
    for p in ("MAGNELIS-", "GALV-", "ALUZINC-", "HDG-"):
        if str(grade).upper().startswith(p):
            return grade[len(p):]
    return grade

def _unit_factor(u):
    u = _norm(u)
    if u in _MT_NAMES: return 1.0
    if u in _KG_NAMES: return 0.001
    return None

def _norm_qty_price(oc_qty, oc_price, oc_unit, odoo_unit):
    of, df = _unit_factor(oc_unit), _unit_factor(odoo_unit)
    if of is None or df is None or of == df:
        return oc_qty, oc_price
    qty_mt = float(oc_qty) * of
    price_mt = float(oc_price) / of
    return qty_mt / df, price_mt * df

def _parse_quality_grade(ol):
    raw_q = _norm(ol.get("quality_choice") or ol.get("quality") or "")
    raw_g = _norm(ol.get("grade") or "")
    oc_quality = _QUALITY_NORM.get(raw_q) if raw_q else None
    qfg = None
    g_rem = ol.get("grade") or ""
    for key in sorted(_QUALITY_NORM, key=len, reverse=True):
        if key in raw_g:
            qfg = _QUALITY_NORM[key]
            g_rem = re.sub(re.escape(key), "", raw_g, flags=re.IGNORECASE)
            g_rem = re.sub(r"[\s\-]+", " ", g_rem).strip()
            break
    final_q = oc_quality or qfg or None
    if qfg and not oc_quality:
        final_g = g_rem if g_rem else None
    else:
        final_g = (ol.get("grade") or "").strip() or None
    return final_q, final_g

def _match_po(ol, po_lines):
    vs = _norm(ol.get("vs_article_id") or "").upper()
    sup = _norm(ol.get("supplier_article_id") or "")
    if vs:
        for pl in po_lines:
            if _norm(pl.get("vs_article") or "").upper() == vs:
                return pl
    if sup:
        for pl in po_lines:
            if _norm(pl.get("original_supplier_article") or "") == sup:
                return pl
            if _norm(pl.get("aoo_fast_number") or "") == sup:
                return pl
    return None

def _match_so(ol, so_lines):
    vs = _norm(ol.get("vs_article_id") or "").upper()
    if vs and so_lines:
        for sl in so_lines:
            if _norm(sl.get("vs_article") or "").upper() == vs:
                return sl
    return None

def _vs_id(obj):
    for k in ("vs_article_id", "vs_article"):
        v = obj.get(k)
        if v:
            return str(v).strip().upper()
    return ""

def _compare_line(ol, pl, sl, tol):
    qty_tol   = tol.get("quantity_tolerance_pct", 0.5)
    price_tol = tol.get("price_tolerance_pct", 1.0)
    thick_tol = tol.get("thickness_tolerance_mm", 0.05)
    width_tol = tol.get("width_tolerance_mm", 5.0)
    len_tol   = tol.get("length_tolerance_mm", 10.0)
    ts_tol    = tol.get("tensile_strength_tolerance", 0.0)

    vs_id    = _vs_id(ol) or (pl and _vs_id(pl)) or "?"
    odoo_unit = (pl.get("product_uom_id") or ["", ""])[1] if pl and pl.get("product_uom_id") else ""
    oc_unit   = ol.get("quantity_unit") or ""

    oc_quality, oc_grade_clean = _parse_quality_grade(ol)

    # Parse dims from OC dimensions string
    oc_dims = ol.get("dimensions") or ""
    oc_thick_p = oc_wide_p = None
    m = re.search(r"(\d+\.?\d*)\s*[xX×]\s*(\d+\.?\d*)", oc_dims)
    if m:
        oc_thick_p, oc_wide_p = float(m.group(1)), float(m.group(2))

    def _dim(key, fallback):
        v = ol.get(key)
        return _to_float(v) if v is not None else fallback

    oc_thick  = _dim("thickness", oc_thick_p)
    oc_width  = _dim("width", oc_wide_p)
    oc_length = _to_float(ol.get("length"))

    # Odoo values
    def _so(k, default=""):
        return (sl.get(k) or default) if sl else default

    odoo = {
        "form":             (_so("form") or "").strip(),
        "quality_choice":   (_so("choice") or "").strip(),
        "grade":            _strip_prefix((_so("grade") or "").strip()),
        "finish":           (_so("finish") or "").strip(),
        "coating":          (_so("coating") or "").strip(),
        "qty":              _to_float(pl.get("product_qty")) if pl else None,
        "no_of_items":      _to_float(_so("no_of_items", None)),
        "price":            _to_float(pl.get("price_unit")) if pl else None,
        "thickness":        _to_float(_so("thickness", None)),
        "width":            _to_float(_so("width", None)),
        "length":           _to_float(_so("length", None)),
        "tensile_strength": (_so("tensile_strength") or "").strip(),
        "description":      (pl.get("name") or "").strip() if pl else "",
    }

    # Normalize qty/price
    nq = np_ = None
    if ol.get("quantity") is not None and ol.get("unit_price") is not None and odoo_unit:
        nq, np_ = _norm_qty_price(ol["quantity"], ol["unit_price"], oc_unit, odoo_unit)
    else:
        nq  = _to_float(ol.get("quantity"))
        np_ = _to_float(ol.get("unit_price"))

    oc = {
        "form":             (ol.get("form") or "").strip(),
        "quality_choice":   oc_quality or "",
        "grade":            _strip_prefix(oc_grade_clean) if oc_grade_clean else "",
        "finish":           (ol.get("finish") or "").strip(),
        "coating":          (ol.get("coating") or "").strip(),
        "qty":              nq,
        "no_of_items":      _to_float(ol.get("no_of_items")),
        "price":            np_,
        "thickness":        oc_thick,
        "width":            oc_width,
        "length":           oc_length,
        "tensile_strength": (ol.get("tensile_strength") or "").strip(),
        "description":      (ol.get("description") or "").strip(),
    }

    field_results = []

    def _add(key, status, o_disp, c_disp):
        field_results.append({"key": key, "label": FIELD_LABELS[key],
                               "status": status, "odoo": o_disp, "oc": c_disp})

    def _both_empty(a, b):
        return not a and not b

    def _text_field(key, min_overlap):
        o, c = str(odoo[key] or ""), str(oc[key] or "")
        if _both_empty(o, c):
            _add(key, "match", "—", "—")
        elif not o:
            _add(key, "mismatch", "not specified", c or "not specified")
        elif not c:
            _add(key, "mismatch", o, "not specified")
        else:
            ov = _word_overlap(o, c)
            _add(key, "match" if (ov is not None and ov >= min_overlap) else "mismatch", o, c)

    def _quality_field():
        o, c = str(odoo["quality_choice"] or ""), str(oc["quality_choice"] or "")
        if _both_empty(o, c):
            _add("quality_choice", "match", "—", "—")
        elif not o:
            _add("quality_choice", "mismatch", "not specified", c)
        elif not c:
            _add("quality_choice", "mismatch", o, "not specified")
        else:
            on = _QUALITY_NORM.get(_norm(o), o)
            cn = _QUALITY_NORM.get(_norm(c), c)
            st = "match" if on.lower() == cn.lower() else "mismatch"
            _add("quality_choice", st, o, c)

    def _num_field(key, tolerance, unit_str="", is_pct=False):
        o_f, c_f = odoo[key], oc[key]
        if o_f is None and c_f is None:
            _add(key, "match", "—", "—")
        elif o_f is None:
            _add(key, "mismatch", "not specified", f"{c_f:g}{unit_str}")
        elif c_f is None:
            _add(key, "mismatch", f"{o_f:g}{unit_str}", "not specified")
        else:
            diff = _pct_diff(o_f, c_f) if is_pct else _abs_diff(o_f, c_f)
            st = "match" if (diff is not None and diff <= tolerance) else "mismatch"
            _add(key, st, f"{o_f:g}{unit_str}", f"{c_f:g}{unit_str}")

    def _int_field(key):
        o_f, c_f = odoo[key], oc[key]
        if o_f is None and c_f is None:
            _add(key, "match", "—", "—")
        elif o_f is None:
            _add(key, "mismatch", "not specified", str(int(round(c_f))))
        elif c_f is None:
            _add(key, "mismatch", str(int(round(o_f))), "not specified")
        else:
            st = "match" if int(round(o_f)) == int(round(c_f)) else "mismatch"
            _add(key, st, str(int(round(o_f))), str(int(round(c_f))))

    def _price_field():
        o_f, c_f = odoo["price"], oc["price"]
        if o_f is None and c_f is None:
            _add("price", "match", "—", "—")
        elif o_f is None:
            _add("price", "mismatch", "not specified", f"{c_f:,.2f}")
        elif c_f is None:
            _add("price", "mismatch", f"{o_f:,.2f}", "not specified")
        else:
            diff = _pct_diff(o_f, c_f)
            st = "match" if (diff is not None and diff <= price_tol) else "mismatch"
            _add("price", st, f"{o_f:,.2f}", f"{c_f:,.2f}")

    def _ts_field():
        o, c = str(odoo["tensile_strength"] or ""), str(oc["tensile_strength"] or "")
        if _both_empty(o, c):
            _add("tensile_strength", "match", "—", "—")
        elif not o:
            _add("tensile_strength", "mismatch", "not specified", c)
        elif not c:
            _add("tensile_strength", "mismatch", o, "not specified")
        else:
            o_f, c_f = _to_float(o), _to_float(c)
            if o_f is not None and c_f is not None:
                diff = _abs_diff(o_f, c_f)
                st = "match" if (diff is not None and diff <= ts_tol) else "mismatch"
            else:
                ov = _word_overlap(o, c)
                st = "match" if (ov is not None and ov >= 80) else "mismatch"
            _add("tensile_strength", st, o, c)

    def _desc_field():
        o = str(odoo["description"] or "")
        c = str(oc["description"] or "")
        od = (o[:80] + "…") if len(o) > 80 else o
        cd = (c[:80] + "…") if len(c) > 80 else c
        if _both_empty(o, c):
            _add("description", "match", "—", "—")
        elif not o:
            _add("description", "mismatch", "not specified", cd)
        elif not c:
            _add("description", "mismatch", od, "not specified")
        else:
            ov = _word_overlap(o, c)
            st = "match" if (ov is not None and ov >= 30) else "mismatch"
            _add("description", st, od, cd)

    _text_field("form", 50)
    _quality_field()
    _text_field("grade", 50)
    _text_field("finish", 40)
    _text_field("coating", 40)
    _num_field("qty", qty_tol, f" {odoo_unit}", is_pct=True)
    _int_field("no_of_items")
    _price_field()
    _num_field("thickness", thick_tol, " mm")
    _num_field("width", width_tol, " mm")
    _num_field("length", len_tol, " mm")
    _ts_field()
    _desc_field()

    score = sum(1 for f in field_results if f["status"] == "match")
    mismatches = [{"field": f["label"], "odoo": f["odoo"], "oc": f["oc"]}
                  for f in field_results if f["status"] == "mismatch"]
    matches    = [{"field": f["label"], "value": f["odoo"]}
                  for f in field_results if f["status"] == "match" and f["odoo"] != "—"]

    return {
        "vs_id":      vs_id,
        "score":      score,
        "total":      TOTAL_FIELDS,
        "fields":     field_results,
        "mismatches": mismatches,
        "matches":    matches,
        "oc_ref":     "",
    }


def compare(oc_data, po_data, po_lines, so_data, so_lines, config):
    tol      = config.get("comparison", {})
    oc_lines = oc_data.get("line_items", [])
    po_name  = po_data.get("name", "?")
    so_name  = so_data["name"] if so_data else "—"
    supplier = (po_data.get("partner_id") or ["", "Unknown"])[1]
    buyer    = (so_data.get("partner_id") or ["—", "—"])[1] if so_data else "—"

    line_results   = []
    all_matches    = []
    all_mismatches = []
    used_po = set()
    used_so = set()

    for i, ol in enumerate(oc_lines):
        pl = _match_po(ol, po_lines)
        if pl is None:
            for j, c in enumerate(po_lines):
                if j not in used_po:
                    pl = c
                    used_po.add(j)
                    break
        else:
            try: used_po.add(po_lines.index(pl))
            except ValueError: pass

        sl = _match_so(ol, so_lines) if so_lines else None
        if sl is None and so_lines:
            for j, c in enumerate(so_lines):
                if j not in used_so:
                    sl = c
                    used_so.add(j)
                    break
        elif sl is not None:
            try: used_so.add(so_lines.index(sl))
            except ValueError: pass

        r = _compare_line(ol, pl, sl, tol)
        r["oc_ref"] = oc_data.get("supplier_reference") or oc_data.get("po_reference") or "?"
        line_results.append(r)

        lbl = r["vs_id"]
        for m in r["matches"]:
            all_matches.append({"field": f"{lbl} — {m['field']}", "value": m["value"]})
        for m in r["mismatches"]:
            all_mismatches.append({"field": f"{lbl} — {m['field']}", "odoo": m["odoo"], "oc": m["oc"]})

    is_match = len(all_mismatches) == 0
    status   = "match" if is_match else ("partial" if all_matches else "mismatch")

    return {
        "line_results": line_results,
        "is_match":     is_match,
        "status":       status,
        "matches":      all_matches,
        "mismatches":   all_mismatches,
        "po_name":      po_name,
        "so_name":      so_name,
        "supplier":     supplier,
        "buyer":        buyer,
    }


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Usage: python compare_fields.py oc.json po.json po_lines.json [so.json so_lines.json config.json]")
        sys.exit(1)
    with open(sys.argv[1]) as f: oc  = json.load(f)
    with open(sys.argv[2]) as f: po  = json.load(f)
    with open(sys.argv[3]) as f: pol = json.load(f)
    so, sol, cfg = {}, [], {}
    if len(sys.argv) > 4:
        with open(sys.argv[4]) as f: so  = json.load(f)
    if len(sys.argv) > 5:
        with open(sys.argv[5]) as f: sol = json.load(f)
    if len(sys.argv) > 6:
        with open(sys.argv[6]) as f: cfg = json.load(f)
    result = compare(oc, po, pol, so, sol, cfg)
    print(json.dumps(result, indent=2, ensure_ascii=False))
