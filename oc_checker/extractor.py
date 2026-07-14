"""
Claude API PDF extractor for Vanilla Steel OC checker.

Replaces Docsumo. Sends the raw PDF to Claude as a native document and
extracts structured OC data. Returns the same schema as
docsumo_client.parse_oc_data() so the rest of the pipeline is unchanged.

Environment variables:
  ANTHROPIC_API_KEY  — Anthropic API key
"""

import os
import re
import json
import base64
import urllib.request


# ---------------------------------------------------------------------------
# Model config
# ---------------------------------------------------------------------------

CLAUDE_MODEL   = "claude-sonnet-4-6"
CLAUDE_API_URL = "https://api.anthropic.com/v1/messages"
MAX_TOKENS     = 4096


# ---------------------------------------------------------------------------
# Extraction prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are a data extraction assistant for Vanilla Steel, a steel trading company.
You extract structured data from supplier PDF documents and return ONLY valid JSON — no explanation,
no markdown fences, no commentary of any kind."""

EXTRACTION_PROMPT = """Extract data from this PDF and return a single JSON object.

════════════════════════════════════════
STEP 1 — IDENTIFY DOCUMENT TYPE
════════════════════════════════════════
First determine what kind of document this is:

  "oc"  → Order Confirmation (Auftragsbestätigung, Orderbevestiging, etc.)
           Sent BY a supplier TO Vanilla Steel. This is what we want.

  "po"  → Purchase Order sent BY Vanilla Steel to a supplier.
           Header will say "Purchase Order", "Bestellung", "Bon de commande" etc.
           Issued by "Vanilla Steel" or "VS" as the SENDER (not just referenced).

If doc_type is "po" (VS's own PO), return ONLY this and stop — do not extract further:
  {"doc_type": "po", "po_number": null, "supplier_name": null, "lines": []}

════════════════════════════════════════
STEP 2 — NUMBER FORMAT RULES
════════════════════════════════════════
European PDFs mix period (thousands separator) and comma (decimal separator):

  Weight/quantity context (coils are 0.1–60 MT each):
    "1.586 MT"   → 1586.0  (period = thousands separator → reads as 1.586 tonnes → WRONG,
                             1.586 MT is less than 2 tonnes, but 1.586 with no comma
                             = could be 1586 kg = 1.586 MT → keep as 1.586)
    RULE: if the number has ONLY periods and no comma, and the value would be
          unreasonably large for a single coil (> 60 MT), treat period as thousands sep.
    "3,0 mm"     → 3.0     (comma = decimal)
    "1.586,34"   → 1586.34 (both: period=thousands, comma=decimal)
    "500,00 €"   → 500.0

  Sanity ranges (use these to resolve ambiguity):
    Coil weight    → 0.1 – 60 MT
    Thickness      → 0.3 – 25 mm
    Width          → 50 – 2000 mm
    Unit price     → 100 – 2000 EUR/MT
    Total per line → weight × unit_price  (within 2%)

  ARITHMETIC CHECK: For each line, verify quantity × unit_price ≈ total_price.
  If they don't match within 5%, set extraction_warning on that line to the discrepancy.

════════════════════════════════════════
STEP 3 — ARTICLE / COIL REFERENCE RULES
════════════════════════════════════════
vs_article and coil_number = the PHYSICAL coil or material reference code.
NOT a sequential position number.

  VALID:   "F900258989", "R90R904232", "52101848", "COIL-12345", "VSI-1234"
  INVALID: "1", "2", "3", "01", "02", "Pos. 1"  → set vs_article to null

If coil references appear in description text (e.g. "R90R904232 R90R904233"),
extract ALL of them space-separated into vs_article.

════════════════════════════════════════
STEP 4 — VS PO NUMBER
════════════════════════════════════════
Vanilla Steel's PO number pattern: P0XXXX (e.g. "P01807", "P01826").
Common label variants in multiple languages:
  "Ihre Bestellnummer", "Your Order No.", "Customer PO", "Ref. VS",
  "Bestell-Nr.", "Auftragsnummer Kunde", "Kundenbestellnummer",
  "Order Reference", "VS Order", "Bestellnr."

════════════════════════════════════════
STEP 5 — GRADE AND COATING
════════════════════════════════════════
Split combined grade+coating strings on "+":
  "DX51D+Z140MACU"     → grade="DX51D",    coating="Z140MACU"
  "HX260LAD+ZA130MC_O" → grade="HX260LAD", coating="ZA130MC_O"
  "S235JR"             → grade="S235JR",   coating=null

════════════════════════════════════════
STEP 6 — INCOTERM AND PAYMENT TERMS NORMALISATION
════════════════════════════════════════
incoterm — extract ONLY the standard 3-letter Incoterm code. Drop city, port, and location.
  Recognised codes and their aliases:
    FCA — "Free Carrier", "Frei Frachtführer", "Franco Vettore"
    DAP — "Delivered At Place", "Geliefert benannter Ort"
    DDP — "Delivered Duty Paid", "Frei Haus", "Geliefert verzollt"
    CIF — "Cost, Insurance and Freight"
    CPT — "Carriage Paid To", "Frachtfrei"
    EXW — "Ex Works", "Ab Werk", "Ex Usine"
    FOB — "Free On Board"
    CFR — "Cost and Freight"
    CIP — "Carriage and Insurance Paid To"
    DPU — "Delivered at Place Unloaded"
  If the code appears in brackets like "[FCA] FREE CARRIER", extract just "FCA".
  Examples:
    "FCA Im Weinhof 36, 58119 Hagen"  → "FCA"
    "Free Carrier Győr"               → "FCA"
    "[FCA] FREE CARRIER"              → "FCA"
    "DAP München"                     → "DAP"
    "Frei Haus"                       → "DDP"
    "Ab Werk"                         → "EXW"

payment_terms — normalise to "X Days" where X is the number of days.
  Examples:
    "Innerhalb 30 Tagen ohne Abzug"  → "30 Days"
    "30 Tage netto"                  → "30 Days"
    "Netto 30 Tage"                  → "30 Days"
    "Net 30 days"                    → "30 Days"
    "Within 30 Days Net"             → "30 Days"
    "60 giorni data fattura"         → "60 Days"
    "60 jours net"                   → "60 Days"
    "Zahlbar sofort netto"           → "0 Days"
    "Immediate payment"              → "0 Days"
  If no simple single day count can be determined (e.g. staged "30/60/90 days"),
  extract the raw text as-is.

════════════════════════════════════════
JSON STRUCTURE TO RETURN
════════════════════════════════════════
{
  "doc_type":           "oc",
  "po_number":          "P01807",
  "supplier_order_num": "84916029",
  "supplier_name":      "ThyssenKrupp Materials",
  "confirmation_date":  "2026-06-17",
  "incoterm":           "FCA",
  "payment_terms":      "30 Days",
  "pickup_address":     "9011 Győr, Gerda utca 3.",
  "total_amount":       12500.00,
  "gross_amount":       14875.00,
  "vat_amount":         2375.00,
  "vat_pct":            "19%",
  "supplier_notes":    ["Loading surcharge: €50/t applies", "Test certificates available on request"],
  "lines": [
    {
      "vs_article":          "F900258989",
      "supplier_article":    "F900258989",
      "description":         "Full description text from the PDF line item",
      "quantity":            1.586,
      "unit":                "MT",
      "unit_price":          500.00,
      "total_price":         793.00,
      "grade":               "DX51D",
      "thickness":           3.0,
      "width":               166.0,
      "length":              null,
      "coating":             "Z140MACU",
      "coil_number":         "F900258989",
      "delivery_date":       "2026-08-15",
      "extraction_warning":  null
    }
  ]
}

Field rules:
- doc_type: always "oc" or "po". Never null.
- Use null for any field not present in the PDF. Never invent values.
- confirmation_date: ISO YYYY-MM-DD. If only month/year given, use first of month.
- delivery_date: ISO YYYY-MM-DD per line item. null if not stated on that line.
  Check column headers like "Liefertermin", "Delivery Date", "Requested Delivery",
  "Livraison", "Leveringsdatum". If one date applies to all lines, repeat it on each.
- length: null for coils; value in mm for cut sheets/plates.
- vat_pct: string with % sign e.g. "19%", or null if not stated.
- All numeric fields: standard decimal float, not strings.
- extraction_warning: string describing arithmetic discrepancy if qty×price!=total, else null.
- supplier_notes: array of short strings capturing any EXTRA information the supplier included
  that is NOT already covered by the standard fields above. Look for things like:
  extra charges (loading, testing, transport surcharges), certificate notes (test certs not
  included / available at cost), special material or grade conditions, truck/logistics
  requirements, validity periods, force majeure clauses, or any other noteworthy remark.
  Each note should be one concise sentence. Empty array [] if nothing extra found.
  Translate to English if the OC is in another language.
"""



# ---------------------------------------------------------------------------
# Low-level API call (no external dependency on anthropic package)
# ---------------------------------------------------------------------------

def _call_claude(pdf_bytes: bytes, filename: str = "") -> str:
    """
    Call the Anthropic Messages API with the PDF as a native document.
    Returns the raw text response from Claude.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY environment variable not set.")

    pdf_b64 = base64.standard_b64encode(pdf_bytes).decode("utf-8")

    payload = {
        "model":      CLAUDE_MODEL,
        "max_tokens": MAX_TOKENS,
        "system":     SYSTEM_PROMPT,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "document",
                        "source": {
                            "type":       "base64",
                            "media_type": "application/pdf",
                            "data":       pdf_b64,
                        },
                        "title": filename or "order_confirmation.pdf",
                    },
                    {
                        "type": "text",
                        "text": EXTRACTION_PROMPT,
                    },
                ],
            }
        ],
    }

    data = json.dumps(payload).encode("utf-8")
    req  = urllib.request.Request(
        CLAUDE_API_URL,
        data=data,
        headers={
            "Content-Type":      "application/json",
            "x-api-key":         api_key,
            "anthropic-version": "2023-06-01",
            "anthropic-beta":    "pdfs-2024-09-25",
        },
        method="POST",
    )

    with urllib.request.urlopen(req, timeout=120) as resp:
        result = json.loads(resp.read().decode("utf-8"))

    # Extract text from the first content block
    content = result.get("content", [])
    for block in content:
        if block.get("type") == "text":
            return block["text"].strip()

    raise RuntimeError("Claude returned no text content. Response: %s" % result)


# ---------------------------------------------------------------------------
# JSON parsing — strip markdown fences if Claude added them despite instructions
# ---------------------------------------------------------------------------

def _parse_json(text: str) -> dict:
    """Parse Claude's response as JSON, stripping any accidental markdown."""
    text = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text.strip())
    return json.loads(text)


# ---------------------------------------------------------------------------
# Number normalisation helpers
# ---------------------------------------------------------------------------

def _to_float(v) -> float | None:
    """Convert a value to float, handling European number formats."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    s = re.sub(r"[€$£\s]", "", s)
    # European format: 1.234,56 → 1234.56
    if re.search(r"\d\.\d{3},\d", s):
        s = s.replace(".", "").replace(",", ".")
    # German decimal only: 3,0 → 3.0
    elif re.search(r"^\d+,\d+$", s):
        s = s.replace(",", ".")
    s = s.rstrip("%")
    try:
        return float(s)
    except (ValueError, TypeError):
        return None


def _normalise_line(line: dict) -> dict:
    """Ensure all numeric fields in a line item are proper Python floats."""
    for field in ("quantity", "unit_price", "total_price", "thickness", "width", "length"):
        v = line.get(field)
        if v is not None:
            line[field] = _to_float(v)
    line.setdefault("unit", "MT")
    line.setdefault("delivery_date", None)
    line.setdefault("extraction_warning", None)
    return line


# ---------------------------------------------------------------------------
# Public extraction function
# ---------------------------------------------------------------------------

def extract_oc_from_pdf(pdf_bytes: bytes, filename: str = "", doc_id: str = "") -> dict:
    """
    Extract OC data from a PDF using the Claude API.

    Returns a dict with keys:
      doc_type, po_number, supplier_order_num, supplier_name, confirmation_date,
      incoterm, payment_terms, pickup_address, total_amount, gross_amount,
      vat_amount, vat_pct, currency, lines[], _doc_id

    Returns None if the PDF is a VS Purchase Order (not a supplier OC).
    Raises RuntimeError on API failure.
    """
    print(f"  Extracting via Claude API: {filename or doc_id}")

    raw_text = _call_claude(pdf_bytes, filename)
    print(f"  Claude response: {len(raw_text)} chars")

    try:
        parsed = _parse_json(raw_text)
    except json.JSONDecodeError as e:
        raise RuntimeError(
            "Claude returned invalid JSON: %s\n\nRaw response:\n%s" % (e, raw_text[:500])
        )

    # ── Doc-type guard ──────────────────────────────────────────────────────
    # If Claude identified this as a VS Purchase Order (not a supplier OC),
    # return None so the caller can skip it cleanly.
    doc_type = parsed.get("doc_type", "oc")
    if doc_type == "po":
        print(f"  SKIPPED: document identified as a VS Purchase Order, not a supplier OC.")
        return None

    # Normalise top-level numeric fields
    for field in ("total_amount", "gross_amount", "vat_amount"):
        v = parsed.get(field)
        if v is not None:
            parsed[field] = _to_float(v)

    # Normalise line items
    lines = parsed.get("lines") or []
    parsed["lines"] = [_normalise_line(line) for line in lines if isinstance(line, dict)]

    # Log any extraction warnings from arithmetic checks
    warnings = [
        (i + 1, line["extraction_warning"])
        for i, line in enumerate(parsed["lines"])
        if line.get("extraction_warning")
    ]
    if warnings:
        for line_num, warn in warnings:
            print(f"  ⚠️  Line {line_num} arithmetic warning: {warn}")

    # Normalise supplier_notes — always a list of non-empty strings
    notes = parsed.get("supplier_notes")
    if isinstance(notes, list):
        parsed["supplier_notes"] = [str(n).strip() for n in notes if n and str(n).strip()]
    elif isinstance(notes, str) and notes.strip():
        parsed["supplier_notes"] = [notes.strip()]
    else:
        parsed["supplier_notes"] = []

    # Always set currency
    parsed["currency"] = "EUR"
    parsed["_doc_id"]  = doc_id or filename

    po  = parsed.get("po_number", "?")
    n   = len(parsed["lines"])
    sup = parsed.get("supplier_name", "?")
    print(f"  Extracted: PO={po}  lines={n}  supplier={sup}")

    return parsed


# ---------------------------------------------------------------------------
# CLI test — run: python extractor.py path/to/oc.pdf
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python extractor.py <path_to_pdf>")
        sys.exit(1)
    path = sys.argv[1]
    with open(path, "rb") as f:
        pdf_bytes = f.read()
    result = extract_oc_from_pdf(pdf_bytes, filename=path)
    if result is None:
        print("Skipped — document is a VS Purchase Order, not a supplier OC.")
    else:
        print(json.dumps(result, indent=2, default=str))
