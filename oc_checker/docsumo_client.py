"""
Docsumo API client for Vanilla Steel OC checker.

Since OC PDFs are already being pushed into Docsumo automatically,
this module only needs to:
  1. List recently processed documents for the OC doc type
  2. Fetch extracted data for each document

No PDF uploading needed.

Environment variables:
  DOCSUMO_API_KEY      — Docsumo API key
  DOCSUMO_DOC_TYPE_ID  — others__vNgOt
"""

import os
import json
import urllib.request
from datetime import datetime, timezone


DOCSUMO_BASE_URL = "https://app.docsumo.com/api/v1/eevee/apikey"


def _api_key() -> str:
    key = os.environ.get("DOCSUMO_API_KEY", "")
    if not key:
        raise RuntimeError("DOCSUMO_API_KEY environment variable not set.")
    return key


def _doc_type_id() -> str:
    dt = os.environ.get("DOCSUMO_DOC_TYPE_ID", "")
    if not dt:
        raise RuntimeError("DOCSUMO_DOC_TYPE_ID environment variable not set.")
    return dt


# ── List documents ────────────────────────────────────────────────

def list_recent_documents(limit: int = 50) -> list[dict]:
    """
    List recently processed documents for the OC doc type.
    Returns list of {id, title, status, created_at} dicts.
    """
    url = (
        f"{DOCSUMO_BASE_URL}/list/"
        f"?api_key={_api_key()}"
        f"&doc_type_id={_doc_type_id()}"
        f"&limit={limit}"
    )
    req = urllib.request.Request(url, headers={"Authorization": f"apikey {_api_key()}"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        result = json.loads(resp.read())

    # Handle different response shapes across Docsumo API versions
    data = result.get("data", result)
    if isinstance(data, dict):
        docs = data.get("data") or data.get("documents") or data.get("list") or []
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


# ── Fetch extracted data ──────────────────────────────────────────

def fetch_document_data(doc_id: str) -> dict:
    """Fetch the extracted fields for a specific document."""
    url = f"{DOCSUMO_BASE_URL}/{doc_id}/data/?api_key={_api_key()}"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=30) as resp:
        result = json.loads(resp.read())
    raw = result.get("data", result)
    if "data" in raw and isinstance(raw["data"], dict):
        raw = raw["data"]
    return raw


# ── Field helpers ─────────────────────────────────────────────────

def _val(section: dict, field: str, default=None):
    entry = section.get(field, {})
    if isinstance(entry, dict):
        v = entry.get("value")
        return v if v not in (None, "", []) else default
    return entry if entry is not None else default


def _to_float(v) -> float | None:
    if v is None:
        return None
    try:
        return float(str(v).replace(",", "").replace(" ", ""))
    except (ValueError, TypeError):
        return None


# ── Line item parser ──────────────────────────────────────────────

def _parse_lines(raw: dict) -> list[dict]:
    """
    Parse Table → Line Items from Docsumo response.
    Structure: {"Table": {"Line Items": [[{row}, {row}], ...]}}
    """
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


# ── Parse a full document into our OC format ─────────────────────

def parse_oc_data(raw: dict, doc_id: str = "") -> dict:
    """Convert Docsumo raw JSON into our standard OC dict."""
    basic  = raw.get("Basic Information", {})
    seller = raw.get("Seller Information", {})

    return {
        "po_number":          _val(basic,  "VS Order Number"),
        "supplier_order_num": _val(basic,  "Supplier Order Number"),
        "supplier_name":      _val(seller, "Company Name"),
        "total_amount":       _to_float(_val(basic, "Net Amount")),
        "currency":           "EUR",
        "lines":              _parse_lines(raw),
        "_docsumo_id":        doc_id,
    }


# ── Quick test ────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Fetching recent documents...")
    docs = list_recent_documents(limit=5)
    print(f"Found {len(docs)} document(s):")
    for d in docs:
        print(f"  {d['id']} | {d['title']} | {d['status']} | {d['created_at']}")

    if docs:
        print(f"\nFetching data for first document: {docs[0]['id']}")
        raw  = fetch_document_data(docs[0]["id"])
        oc   = parse_oc_data(raw, docs[0]["id"])
        print(json.dumps(oc, indent=2, default=str))
