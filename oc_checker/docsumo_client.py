"""
Docsumo API client for Vanilla Steel OC checker.
Environment variables:
  DOCSUMO_API_KEY      -- Docsumo API key
  DOCSUMO_DOC_TYPE_ID  -- others__vNgOt
"""

import os
import json
import urllib.request

DOCSUMO_BASE_URL = "https://app.docsumo.com/api/v1/eevee/apikey"

# Cloudflare blocks Python's default user-agent -- use a browser UA
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
}


def _api_key():
    key = os.environ.get("DOCSUMO_API_KEY", "")
    if not key:
        raise RuntimeError("DOCSUMO_API_KEY environment variable not set.")
    return key


def _doc_type_id():
    dt = os.environ.get("DOCSUMO_DOC_TYPE_ID", "")
    if not dt:
        raise RuntimeError("DOCSUMO_DOC_TYPE_ID environment variable not set.")
    return dt


def list_recent_documents(limit=20):
    """List recently processed OC documents. Returns [{id, title, status, created_at}]."""
    url = (
        DOCSUMO_BASE_URL + "/documents/all/"
        + "?doc_type=" + _doc_type_id()
        + "&status=reviewing"
        + "&limit=" + str(min(limit, 20))
        + "&sort_by=created_date.desc"
    )
    req = urllib.request.Request(url, headers={**HEADERS, "apikey": _api_key()})
    with urllib.request.urlopen(req, timeout=30) as resp:
        result = json.loads(resp.read())

    data = result.get("data", result)
    if isinstance(data, dict):
        docs = data.get("documents") or data.get("data") or data.get("list") or []
    elif isinstance(data, list):
        docs = data
    else:
        docs = []

    return [
        {
            "id":         d.get("document_id") or d.get("doc_id") or d.get("id"),
            "title":      d.get("title") or d.get("file_name") or d.get("name", ""),
            "status":     d.get("status", ""),
            "created_at": d.get("created_at") or d.get("upload_date") or "",
        }
        for d in docs
        if d.get("document_id") or d.get("doc_id") or d.get("id")
    ]


def fetch_document_data(doc_id):
    """Fetch the extracted fields for a specific document."""
    url = DOCSUMO_BASE_URL + "/data/simplified/" + doc_id + "/"
    req = urllib.request.Request(url, headers={**HEADERS, "apikey": _api_key()})
    with urllib.request.urlopen(req, timeout=30) as resp:
        result = json.loads(resp.read())
    return result.get("data", result)


def _val(section, field, default=None):
    entry = section.get(field, {})
    if isinstance(entry, dict):
        v = entry.get("value")
        return v if v not in (None, "", []) else default
    return entry if entry is not None else default


def _to_float(v):
    if v is None:
        return None
    try:
        return float(str(v).replace(",", "").replace(" ", ""))
    except (ValueError, TypeError):
        return None


def _parse_lines(raw):
    """Parse Table -> Line Items from Docsumo response."""
    table = raw.get("Table", {})
    line_items_raw = table.get("Line Items", [])
    rows = []
    for item in line_items_raw:
        if isinstance(item, list):
            rows.extend(item)
        elif isinstance(item, dict):
            rows.append(item)

    lines = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        qty   = _to_float(_val(row, "Total Weight"))
        price = _to_float(_val(row, "Item price per ton"))
        if qty is None and price is None:
            continue
        lines.append({
            "vs_article":       _val(row, "Item ID"),
            "supplier_article": _val(row, "Item ID"),
            "description":      _val(row, "Item Description"),
            "quantity":         qty,
            "unit":             "MT",
            "unit_price":       price,
            "total_price":      _to_float(_val(row, "Total Value")),
            "grade":            _val(row, "Grade"),
            "thickness":        _to_float(_val(row, "Thickness")),
            "width":            _to_float(_val(row, "Width")),
            "length":           _to_float(_val(row, "Length")),
            "coating":          _val(row, "Coating"),
        })
    return lines


def parse_oc_data(raw, doc_id=""):
    """Convert Docsumo raw JSON into our standard OC dict."""
    basic  = raw.get("Basic Information", {})
    seller = raw.get("Seller Information", {})
    return {
        "po_number":          _val(basic,  "VS Order Number"),
        "supplier_order_num": _val(basic,  "Supplier Order Number"),
        "supplier_name":      _val(seller, "Company Name"),
        "total_amount":       _to_float(_val(basic, "Net Amount")),
        "gross_amount":       _to_float(_val(basic, "Gross Amount")),
        "vat_amount":         _to_float(_val(basic, "VAT Amount")),
        "vat_pct":            _val(basic,  "VAT Percentage"),          # e.g. "19%"
        "incoterm":           _val(basic,  "Incoterm"),                 # e.g. "FCA"
        "payment_terms":      _val(basic,  "Payment Terms"),
        "pickup_address":     _val(basic,  "Supplier Pick up address"),
        "confirmation_date":  _val(basic,  "Order Date"),
        "currency":           "EUR",
        "lines":              _parse_lines(raw),
        "_docsumo_id":        doc_id,
    }


if __name__ == "__main__":
    print("Fetching recent documents...")
    docs = list_recent_documents(limit=5)
    print("Found %d document(s):" % len(docs))
    for d in docs:
        print("  %s | %s | %s | %s" % (d["id"], d["title"], d["status"], d["created_at"]))
    if docs:
        print("\nFetching data for first document: %s" % docs[0]["id"])
        raw = fetch_document_data(docs[0]["id"])
        oc  = parse_oc_data(raw, docs[0]["id"])
        print(json.dumps(oc, indent=2, default=str))
