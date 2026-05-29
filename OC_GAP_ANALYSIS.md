# Docsumo Gap Analysis — 7 OC PDFs
**Date**: 2026-05-27  
**Suppliers covered**: Bandstahl-Service-Hagen, Risse+Wilke, SSAB Europe, Knappstein, EMW Stahl Service, Bilstein Kaltband, Stahlhandel Vogt  
**Purpose**: Compare what Claude extracts from OC PDFs (ideal) vs what Docsumo actually extracts. Identify every gap. Provide exact Docsumo field + prompt fixes.

---

## How to read this report

For each OC:
- **Section A**: What the PDF text clearly states (ground truth)
- **Section B**: What Docsumo extracted
- **Section C**: Gaps (what Docsumo missed or got wrong)

Then at the end: **Master list of Docsumo prompt fixes** — exactly what to change.

---

---

# OC 1 — Bandstahl-Service-Hagen (KC10189-S)

## A — Ground truth from PDF

| Field | Value from OC text |
|---|---|
| VS PO Number | **BLANK** — OC shows "P-" with no number after it |
| OC Reference | KC10189-S |
| Confirmation Date | 11.03.2026 |
| Supplier | Bandstahl-Service-Hagen GmbH, Hagen |
| Incoterms | ab Werk [EXW] |
| Payment Terms | Gegen Vorkasse netto [Prepayment, no discount] |
| Net Total | €7,311.35 |
| VAT | 19% → gross €8,700.51 |
| Delivery | März 2026 [March 2026] |
| No. of Items | 9 coils (1 per position) |

**9 line items:**

| Pos | Kundenmaterial Nr. | Grade+Coating string | Form | Thickness | Width | Qty (t) | Price €/t | Value € | Quality |
|---|---|---|---|---|---|---|---|---|---|
| 1 | JE5444-R01 | DX54D+ZMA CO 275 g/m² | Spaltband (Slit Coil) | 1.26 | 158.0 | 1.540 | 530 | 816.20 | IIa |
| 2 | JG6355-N01 | DX51D+ZMAC 140 g/m² | Spaltband | 1.54 | 272.0 | 1.265 | 530 | 670.45 | IIa |
| 3 | KA0527-B11 | DX51D+ZMAC 140 g/m² | Spaltband | 1.55 | 232.0 | 1.100 | 530 | 583.00 | IIa |
| 4 | KA0527-B16 | DX51D+ZMAC 140 g/m² | Spaltband | 1.55 | 232.0 | 1.055 | 530 | 559.15 | IIa |
| 5 | KA0527-B15 | DX51D+ZMAC 140 g/m² | Spaltband | 1.55 | 232.0 | 1.100 | 530 | 583.00 | IIa |
| 6 | JA2083-B08 | DX51D MAC 120 g/m² Zink-Magnesium | Spaltband | 1.47 | 326.0 | 1.920 | 530 | 1,017.60 | IIa |
| 7 | JA2083-B15 | DX51D MAC 120 g/m² Zink-Magnesium | Spaltband | 1.47 | 326.0 | 1.950 | 530 | 1,033.50 | IIa |
| 8 | JA2083-B01 | DX51D MAC 120 g/m² Zink-Magnesium | Spaltband | 1.47 | 326.0 | 1.915 | 530 | 1,014.95 | IIa |
| 9 | KB1355-A01 | HX380LAD+ZM MB leicht gefettet 90 g/m² | Spaltband | 1.50 | 127.0 | 1.950 | 530 | 1,033.50 | IIa |

**Notes visible in OC:**
- "Bei deklassiertem / IIa Material sind Reklamationen jeglicher Art ausgeschlossen!" (every position)  
  → [For 2nd choice material, complaints of any kind are excluded]
- "Materialprüfbescheinigung: keine Prüfbescheinigung / in Anlehnung an DIN EN 10204"  
  → [No material test certificate / based on DIN EN 10204]
- Loading instructions per position (stehend = upright, liegend = flat)
- "Liefertermine vorbehaltlich Preisstabilität und der rechtzeitigen Belieferung durch das Herstellerwerk"  
  → [Delivery dates subject to price stability and timely supply from manufacturer]

## B — What Docsumo extracted

```json
{
  "po_number": "P-000000",          ← FABRICATED (OC has "P-" with no number)
  "supplier_order_num": "KC10189-S",  ✅
  "supplier_name": "Bandstahl-Service-Hagen GmbH",  ✅
  "total_amount": 7311.35,  ✅
  "gross_amount": 8700.506,  ✅
  "vat_amount": 1389.16,  ✅
  "vat_pct": "19%",  ✅
  "incoterm": "ab Werk",  ✅ (value, though not normalized to EXW)
  "payment_terms": "Prepayment",  ✅
  "pickup_address": "Walzenstraße 12 - 17 58093 Hagen",  ✅
  "confirmation_date": "11/03/2026",  ✅
  "lines": [9 lines with grade/thickness/width/qty/price...]
}
```

Line extraction summary:

| Pos | vs_article (Docsumo) | Grade | Coating | Thickness | Width | Qty | Price | Quality |
|---|---|---|---|---|---|---|---|---|
| 1 | **null** ❌ | DX54D ✅ | **"Z"** ❌ (should be ZMACO 275) | 1.26 ✅ | 158.0 ✅ | 1.540 ✅ | 530 ✅ | **missing** ❌ |
| 2 | **null** ❌ | DX51D ✅ | **"Z"** ❌ (should be ZMAC 140) | 1.54 ✅ | 272.0 ✅ | 1.265 ✅ | 530 ✅ | **missing** ❌ |
| 3 | **null** ❌ | DX51D ✅ | **"Z"** ❌ (should be ZMAC 140) | 1.55 ✅ | 232.0 ✅ | 1.100 ✅ | 530 ✅ | **missing** ❌ |
| 4 | **null** ❌ | DX51D ✅ | **"Z"** ❌ (should be ZMAC 140) | 1.55 ✅ | 232.0 ✅ | 1.055 ✅ | 530 ✅ | **missing** ❌ |
| 5 | **null** ❌ | DX51D ✅ | **"Z"** ❌ (should be ZMAC 140) | 1.55 ✅ | 232.0 ✅ | 1.100 ✅ | 530 ✅ | **missing** ❌ |
| 6 | JA2083-B08 ✅ | DX51D ✅ | **null** ❌ (should be ZM/ZMAC 120) | 1.47 ✅ | 326.0 ✅ | 1.920 ✅ | 530 ✅ | **missing** ❌ |
| 7 | JA2083-B15 ✅ | DX51D ✅ | **null** ❌ | 1.47 ✅ | 326.0 ✅ | 1.950 ✅ | 530 ✅ | **missing** ❌ |
| 8 | **null** ❌ | DX51D ✅ | **null** ❌ | 1.47 ✅ | 326.0 ✅ | 1.915 ✅ | 530 ✅ | **missing** ❌ |
| 9 | **null** ❌ | HX380LAD ✅ | ZM ✅ (partial) | 1.50 ✅ | 127.0 ✅ | 1.950 ✅ | 530 ✅ | **missing** ❌ |

## C — Gaps for OC 1

| # | Field | What OC says | What Docsumo got | Severity |
|---|---|---|---|---|
| G1 | **PO Number** | Blank ("P-" with no number) | "P-000000" (fabricated!) | 🔴 CRITICAL — will match wrong PO in Odoo |
| G2 | **Quality Choice** | "IIa" on every line in description | Not extracted at all | 🔴 CRITICAL — IIa is commercially critical |
| G3 | **Form** | "Spaltband" (= Slit Coil) | Not extracted | 🟠 HIGH |
| G4 | **Coating (spaced codes)** | "Z M A C 140", "Z M A CO 275" | Only "Z" (truncates at first space) | 🔴 CRITICAL — wrong coating |
| G5 | **Coating (no + sign)** | "MAC 120 g/m² Zink-Magnesium" | null | 🟠 HIGH — ZM coating missed entirely |
| G6 | **Item ID (Kundenmaterial Nr.)** | JE5444-R01, JG6355-N01, KA0527-B11, KA0527-B16, KA0527-B15, JA2083-B01, KB1355-A01 | null for 7 of 9 | 🔴 CRITICAL — line matching will fail |
| G7 | **Finish** | "feuerverzinkt" [hot-dip galvanized] | Not extracted | 🟡 MEDIUM |
| G8 | **No. of Items** | 1 coil per position | Not extracted | 🟡 MEDIUM |
| G9 | **Supplier Notes** | IIa no-warranty disclaimer, no material cert, loading instructions, delivery reservation | Not extracted | 🟠 HIGH |

**Ideal Slack message (OC side only — Odoo comparison requires API query):**

```
❌  OC MISMATCH — PO: UNKNOWN · KC10189-S

PO: [not in OC]   Supplier: Bandstahl-Service-Hagen GmbH
OC Ref: KC10189-S   Confirmed: 2026-03-11

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PART 1 — PARAMETER CHECK
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

⚠️ NOTE: OC does not contain VS PO number. Manual identification required.

JE5444-R01 · DX54D · 1.26×158mm · 1.54t
   ❌ Quality Choice: IIa (2nd choice)  [Odoo: needs query]
   ✅ Form: Slit Coil  [OC: Spaltband]
   ✅ Grade: DX54D  [OC: DX54D+ZMACO — coating suffix stripped]
   — Finish: feuerverzinkt [hot-dip galvanized]  (not labelled separately in OC)
   ❌ Coating: ZMACO 275 g/m²  [OC: "Z M A CO 275" = ZMACO275]  [Odoo: needs query]
   ✅ Quantity: 1.54 t
   — # of Items: 1 coil (Bundgewicht max 2.0t)
   ✅ Unit Price: €530.00/t
   ✅ Thickness: 1.26 mm
   ✅ Width: 158.0 mm
   ✅ Total Value: €816.20 net  (OC: €816.20 + 19% VAT = €971.28 gross)
   N/A Length: not applicable (slit coil)
   — Tensile Strength: not stated in OC

[Positions 2–9 repeat same structure — all IIa, all Spaltband, 530€/t]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PART 2 — FLAGS BEFORE SENDING SO
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📍 Pickup Address:
   OC: Bandstahl-Service-Hagen GmbH, Walzenstraße 12-17, 58093 Hagen
   [Compare against Odoo SO shipping address]

📅 Delivery Date:
   März 2026 [March 2026] — subject to price stability and manufacturer supply

⚠️ Incoterms:
   OC: ab Werk [EXW — Ex Works, Hagen]  |  Compare with PO in Odoo

⚠️ Payment Terms MISMATCH (likely):
   OC: Gegen Vorkasse netto [Prepayment, no discount]  |  Compare with PO in Odoo

🧾 VAT: 19%  |  Net: €7,311.35  |  Gross (incl. VAT): €8,700.51

📝 Supplier Notes:
   • "Bei deklassiertem / IIa Material sind Reklamationen jeglicher Art ausgeschlossen!"
     [For 2nd choice material, complaints of any kind are excluded — no warranty]
   • "Materialprüfbescheinigung: keine Prüfbescheinigung" [No material test certificate]
   • Loading: Positions 1,2,6,7,8,9 stehend [upright]; Positions 3,4,5 liegend [flat]
   • "Liefertermine vorbehaltlich Preisstabilität und der rechtzeitigen Belieferung durch das
     Herstellerwerk" [Delivery dates subject to price stability and timely supply from manufacturer]
```

---

---

# OC 2 — Risse+Wilke Kaltband (P01740 / OC 6300167048)

## A — Ground truth from PDF

| Field | Value |
|---|---|
| VS PO Number | P01740 |
| OC Reference | 6300167048 |
| Date | 29.04.2026 |
| Supplier | RISSE + WILKE Kaltband GmbH & Co. KG, Iserlohn |
| Incoterms | FCA Iserlohn / Letmathe |
| Payment Terms | 30 Tage nach Rechnungsdatum netto [30 days from invoice date, net] |
| Gross Price (list) | 560.00 EUR/1.000 KG × 2,312 KG = €1,294.72 |
| Dealer Discount | −6.00% = −€77.68 |
| **Net Total** | **€1,217.04** |
| VAT | Not stated (OC says "zuzüglich der... vorgeschriebenen MwSt" = "plus statutory VAT") |
| Pattern | **C — Single weight for entire PO** |
| Delivery | Woche 19.2026 [Week 19 / 2026, approx. 4–10 May 2026] — "unter Vorbehalt" |

Single line item:
- Supplier article: 630242239
- Description: DIN EN 10140:2006, surface MA / MA-RL  
- Quantity: 2,312 KG = 2.312 t
- List price: 560.00 EUR/1.000 KG (= 560 EUR/t)
- Net price after discount: 525.67 EUR/t (calculated: 1217.04 / 2.312)
- Grade, thickness, width: NOT STATED IN THIS OC

**Commercially important note:**  
"Die Terminzusage erfolgt unter Vorbehalt einer gesicherten Vormaterialversorgung."  
[Delivery commitment is subject to secured supply of raw materials]

## B — What Docsumo extracted

```json
{
  "po_number": "P01740",  ✅
  "supplier_order_num": "6300167048",  ✅
  "supplier_name": "RISSE + WILKE Kaltband GmbH & Co. KG",  ✅
  "total_amount": 1217.04,  ✅
  "gross_amount": 1448.278,  ← WRONG: calculated 1217.04 × 1.19 = VAT not in OC
  "vat_amount": 231.24,  ← WRONG: VAT not explicitly stated in OC
  "vat_pct": null,  ✅ (correctly null — not stated)
  "incoterm": "FCA Iserlohn / Letmathe",  ✅
  "payment_terms": null,  ❌ MISSED — "30 Tage nach Rechnungsdatum netto"
  "pickup_address": null,  ✅ (none stated in OC — correct)
  "confirmation_date": "29/04/2026",  ✅
  "lines": [
    {
      "vs_article": "630242239",  ✅ (supplier article, used as ID)
      "unit_price": 560.0,  ⚠️ LIST price — discount not applied
      "total_price": 1294.72,  ⚠️ GROSS before discount
      "quantity": 2.312,  ✅
      "grade": null,  ✅ (not in OC — correct)
      "thickness": null,  ✅ (not in OC — correct)
      "width": null,  ✅ (not in OC — correct)
      "coating": null  ✅ (not in OC — correct)
    }
  ]
}
```

## C — Gaps for OC 2

| # | Field | What OC says | What Docsumo got | Severity |
|---|---|---|---|---|
| G1 | **Payment Terms** | "30 Tage nach Rechnungsdatum netto" | null — MISSED | 🔴 CRITICAL — can't check payment mismatch |
| G2 | **VAT / Gross Amount** | VAT not stated (just "plus statutory VAT") | Calculated 19% gross — INCORRECT | 🟠 HIGH — fabricated value |
| G3 | **Unit Price** | Net after 6% discount = €525.67/t | Raw list price 560 €/t (before discount) | 🟠 HIGH — price comparison will show false mismatch |
| G4 | **Delivery Reservation** | "Vorbehalt einer gesicherten Vormaterialversorgung" | Not extracted | 🟠 HIGH — commercially important note |
| G5 | **Pattern detection** | Pattern C (single weight for full PO) | Not detected — treated as single normal line | 🟡 MEDIUM |

**Ideal Slack message:**

```
✅  OC CONFIRMED — P01740 · [SO: needs Odoo query]

PO: P01740   Supplier: RISSE + WILKE Kaltband GmbH   Buyer: [Odoo]
OC Ref: 6300167048   Confirmed: 2026-04-29

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PART 1 — PARAMETER CHECK
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

⚠️ PATTERN C — Supplier confirmed entire PO as one combined weight.
   OC total weight: 2.312 t  |  [compare sum of Odoo PO lines]
   Individual spec fields cannot be verified from this OC.

630242239 · 2.312 t total
   ✅ Quantity (total): 2.312 t
   ✅ Total Value: €1,217.04 net  (OC: list €1,294.72 − 6% dealer discount = €1,217.04)
   — Grade: not stated in OC  (Odoo: [needs query])
   — Thickness: not stated in OC
   — Width: not stated in OC
   — Form: not stated in OC
   — Finish: not stated in OC
   — Coating: not stated in OC
   — Quality Choice: not stated in OC
   — # of Items: not stated
   — Unit Price: €525.67/t net (after 6% discount)
   — Tensile Strength: not stated

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PART 2 — FLAGS BEFORE SENDING SO
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📅 Delivery Date:
   Week 19 / 2026 (approx. 4–10 May 2026) — subject to raw material supply

⚠️ Payment Terms:
   OC: 30 Tage nach Rechnungsdatum netto [30 days from invoice date, net]
   |  Compare with PO in Odoo

⚠️ Manual Verification Required:
   RISSE + WILKE confirmed the entire PO as a single weight of 2.312 t.
   Individual spec fields (grade, thickness, width) cannot be auto-verified.
   Please check each Odoo PO line against the full OC manually.

📝 Supplier Notes:
   • "Die Terminzusage erfolgt unter Vorbehalt einer gesicherten Vormaterialversorgung."
     [Delivery commitment is subject to secured supply of raw materials]
```

---

---

# OC 3 — SSAB Europe Oy (P01755 / Order 85531-01)

## A — Ground truth from PDF

| Field | Value |
|---|---|
| VS PO Number | P01755 |
| OC Reference | 85531(01) |
| Date | 2026-05-15 |
| Supplier | SSAB Europe Oy, Hämeenlinna, Finland |
| Incoterms | CIP (INCOTERMS 2020) BRZESC KUJAWSKI VIA SZCZECIN |
| Payment Terms | 30 DAYS FROM INVOICE DATE |
| Net Total | €45,499.44 |
| VAT | 0.00% (B2B cross-border, explicitly stated "Tax rate 0.00") |
| Mode of Transport | SHIP + TRUCK |
| Consignee / Delivery | H&S STEEL SP. Z O.O., Machnacz 81, 87-880 BRZESC KUJAWSKI, POLAND |
| Manufacturer | SSAB EUROPE OY RAAHE (origin plant) |
| Quality | SECOND CHOICE COILS (2nd choice — all items) |

**4 line items:**

| Item | Description | Thickness | Width | Qty (KG) | Price EUR/TN | Total EUR | Tariff/CN | Coil No. |
|---|---|---|---|---|---|---|---|---|
| 001 | HOT ROLLED SECOND CHOICE COILS | 3.00 mm | 1509.0 mm | 27,112 KG | 600.00 | 16,267.20 | 72083800 | 12192-031 |
| 002 | HOT ROLLED SECOND CHOICE COILS | 3.98 mm | 1507.0 mm | 23,510 KG | 615.00 | 14,458.65 | 72083800 | 12214-040 |
| 003 | HOT ROLLED SECOND CHOICE COILS | 4.98 mm | 1510.0 mm | 11,720 KG | 610.00 | 7,149.20 | 72083700 | 88478-110 |
| 004 | HOT ROLLED SECOND CHOICE COILS | 4.98 mm | 1510.0 mm | 12,499 KG | 610.00 | 7,624.39 | 72083700 | 88945-058 |

Total: 74,841 KG, 4 PCS

Notes:
- All items: "EX WORKS" price basis (even though delivery incoterm is CIP — distinction matters)
- "ALL BANK CHARGES OUTSIDE FINLAND FOR BUYER'S ACCOUNT"
- Delivery W23, 2026 (all items)
- Grade/steel standard: Not stated (just "SECOND CHOICE COILS" — no EN grade)
- No warranty for 2nd choice implied

## B — What Docsumo extracted

```json
{
  "po_number": "P01755",  ✅
  "supplier_order_num": "85531(01)",  ✅
  "supplier_name": "SSAB Europe Oy",  ✅
  "total_amount": 45499.44,  ✅
  "gross_amount": 54144.334,  ← WRONG: tax is 0% but Docsumo applied 19%
  "vat_amount": 8644.89,  ← WRONG: tax is 0.00%
  "vat_pct": null,  ❌ MISSED — OC says "Tax rate 0.00" explicitly
  "incoterm": "CIP (INCOTERMS 2020)",  ✅ (partial — location not captured)
  "payment_terms": "30 DAYS FROM INVOICE DATE",  ✅
  "pickup_address": "SSAB EUROPE OY RAAHE",  ❌ WRONG — that's manufacturer, not consignee
  "confirmation_date": "15/05/2026",  ✅
  "lines": [4 lines with grade=null, tariff=null, quality=null, vs_article=001/002/003/004]
}
```

Line extraction summary:

| Item | vs_article (Docsumo) | Grade | Coating | Thickness | Width | Qty (t) | Price | Quality |
|---|---|---|---|---|---|---|---|---|
| 001 | "001" ❌ | null | null | 3.00 ✅ | 1509.0 ✅ | 27.112 ✅ | 600 ✅ | **missing** ❌ |
| 002 | "002" ❌ | null | null | 3.98 ✅ | 1507.0 ✅ | 23.51 ✅ | 615 ✅ | **missing** ❌ |
| 003 | "003" ❌ | null | null | 4.98 ✅ | 1510.0 ✅ | 11.72 ✅ | 610 ✅ | **missing** ❌ |
| 004 | "004" ❌ | null | null | 4.98 ✅ | 1510.0 ✅ | 12.499 ✅ | 610 ✅ | **missing** ❌ |

## C — Gaps for OC 3

| # | Field | What OC says | What Docsumo got | Severity |
|---|---|---|---|---|
| G1 | **Quality Choice** | "SECOND CHOICE COILS" (all items) | Not extracted | 🔴 CRITICAL |
| G2 | **VAT rate + gross** | Tax rate: 0.00% → gross = net | Calculated 19% — WRONG | 🔴 CRITICAL — wrong invoice amount shown |
| G3 | **Tariff/CN Code** | 72083800 (items 1-2), 72083700 (items 3-4) | Not extracted | 🔴 CRITICAL — customs data |
| G4 | **Consignee Address** | H&S STEEL, Machnacz 81, Brzesc Kujawski, POLAND | "SSAB EUROPE OY RAAHE" (manufacturer origin) ❌ | 🔴 CRITICAL — wrong address |
| G5 | **Form** | "HOT ROLLED STEEL COILS" | Not extracted | 🟠 HIGH |
| G6 | **Item ID** | "001"-"004" captured but are row numbers, not VS article IDs | "001"-"004" picked up — triggers wrong Odoo matching | 🟠 HIGH |
| G7 | **Delivery Date** | W23, 2026 per item | Not extracted | 🟠 HIGH |
| G8 | **Incoterm location** | "CIP BRZESC KUJAWSKI VIA SZCZECIN" | "CIP (INCOTERMS 2020)" — location missing | 🟡 MEDIUM |
| G9 | **Transport Mode** | "SHIP + TRUCK" | Not extracted | 🟡 LOW |

**Ideal Slack message:**

```
✅  OC CONFIRMED — P01755 · [SO: needs Odoo query]

PO: P01755   SO: [Odoo]   Supplier: SSAB Europe Oy   Buyer: [Odoo]
OC Ref: 85531(01)   Confirmed: 2026-05-15

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PART 1 — PARAMETER CHECK
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Item 001 · 3.00×1509mm · 27.112t · Coil No. 12192-031
   ❌ Quality Choice: SECOND CHOICE  [Odoo: needs query]
   ✅ Form: HOT ROLLED COIL
   — Grade: not stated in OC  (no EN standard grade — "SECOND CHOICE COILS" only)
   — Finish: Hot Rolled (implied — no coating stated)
   — Coating: N/A (uncoated hot rolled)
   ✅ Quantity: 27.112 t
   — # of Items: 1 coil
   ✅ Unit Price: €600.00/t (EXW price basis)
   ✅ Thickness: 3.00 mm
   ✅ Width: 1509.0 mm
   ✅ Total Value: €16,267.20 net
   N/A Length: not applicable (coil)
   — Tensile Strength: not stated

Item 002 · 3.98×1507mm · 23.51t · Coil No. 12214-040
   ❌ Quality Choice: SECOND CHOICE  [Odoo: needs query]
   ✅ Form: HOT ROLLED COIL
   — Grade: not stated  |  — Finish: Hot Rolled  |  — Coating: N/A
   ✅ Quantity: 23.51 t  |  ✅ Unit Price: €615.00/t
   ✅ Thickness: 3.98 mm  |  ✅ Width: 1507.0 mm
   ✅ Total Value: €14,458.65 net
   N/A Length (coil)  |  — Tensile Strength: not stated

Item 003 · 4.98×1510mm · 11.72t · Coil No. 88478-110
   ❌ Quality Choice: SECOND CHOICE
   [same structure as above — price €610/t, total €7,149.20]

Item 004 · 4.98×1510mm · 12.499t · Coil No. 88945-058
   ❌ Quality Choice: SECOND CHOICE
   [same structure — price €610/t, total €7,624.39]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PART 2 — FLAGS BEFORE SENDING SO
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📍 Consignee / Delivery Address:
   OC: H&S STEEL SP. Z O.O., Machnacz 81, 87-880 BRZESC KUJAWSKI, POLAND
   Odoo SO: [needs query — compare partner_shipping_id]
   → Verify buyer's consignee matches

📅 Delivery Date:
   Week 23 / 2026 (approx. 1–7 Jun 2026) — all 4 items

🔢 Tariff / CN Code:
   Items 001–002: 72083800
   Items 003–004: 72083700
   (from OC — note for customs)

🧾 VAT: 0.00%  |  Net: €45,499.44  |  Gross: €45,499.44 (no VAT — intra-EU B2B)
```

---

---

# MASTER GAPS SUMMARY

| Gap | Affects | Severity | Fix type |
|---|---|---|---|
| PO number fabrication (P-000000) | OC1 | 🔴 CRITICAL | Prompt fix |
| Quality Choice (IIa / Second Choice) | OC1, OC3 | 🔴 CRITICAL | New field |
| Coating with internal spaces (ZMAC, ZMACO) | OC1 | 🔴 CRITICAL | Prompt fix |
| Coating without + prefix | OC1 | 🟠 HIGH | Prompt fix |
| Item ID (Kundenmaterial Nr.) inconsistent | OC1 | 🔴 CRITICAL | Prompt fix |
| Payment Terms (German format) | OC2 | 🔴 CRITICAL | Prompt fix |
| VAT not stated → Docsumo calculates wrong gross | OC2, OC3 | 🔴 CRITICAL | Prompt fix |
| Consignee/delivery address (vs manufacturer) | OC3 | 🔴 CRITICAL | Prompt fix |
| Tariff / CN Code | OC3 | 🔴 CRITICAL | New field |
| Form (Spaltband, Hot Rolled Coil) | OC1, OC3 | 🟠 HIGH | New field |
| Finish (feuerverzinkt) | OC1 | 🟠 HIGH | New field |
| Supplier Notes / key conditions | OC1, OC2 | 🟠 HIGH | New field |
| Delivery Date | OC1, OC3 | 🟠 HIGH | Prompt fix |
| Row numbers as item IDs (001/002) | OC3 | 🟠 HIGH | Prompt fix |

---

---

# DOCSUMO PROMPT FIXES — EXACT CHANGES

Go to **Docsumo → Document Type → Edit Fields** for type `others__vNgOt`.

---

## FIX 1: VS Order Number (CRITICAL — EXISTING FIELD)

**Problem**: When PO field has "P-" with no number, Docsumo outputs "P-000000" (fabricated). This will silently match the wrong PO in Odoo.

**New prompt for "VS Order Number":**
> Extract the Vanilla Steel purchase order number. This is always in the format P0XXXX (e.g. P01740, P01755). Look for: 'Ihre Bestellung', 'Ihre Bestell-Nr.', 'Bestellnummer', 'Your order no.', 'Buyer's order', 'PO', 'Order no.', 'Ref'. CRITICAL: Only extract a COMPLETE number with digits after the P. If the document shows only "P-" with nothing after it, or "P- vom", output nothing — do NOT generate or guess a number.

---

## FIX 2: Coating (CRITICAL — EXISTING FIELD)

**Problem A**: "Z M A C 140 g/m²" is the same as "ZMAC140" — spaces are between individual characters, not between words. Docsumo only captures up to the first space → outputs "Z".

**Problem B**: Coating after no-plus notation ("DX51D MAC 120 g/m²" with space not +) → Docsumo outputs null.

**New prompt for "Coating":**
> Extract the coating weight class. It may appear as:
> 1. Part of the grade after a '+' sign: 'DX51D+Z275' → Z275, 'HX380LAD+ZM' → ZM
> 2. Separated from grade with a space: 'DX51D MAC 120 g/m²' → MAC120 (zinc-magnesium)
> 3. Written with spaces between characters: 'Z M A C 140 g/m²' means 'ZMAC140' — treat spaced letters as a single continuous code
> Common prefixes and their meaning: Z=hot-dip zinc, ZM=zinc-magnesium, ZMA=zinc-magnesium alloy, ZMAC=zinc-magnesium alloy coated, AZ=aluzinc, ZE=electrolytic zinc.
> Always include the weight number (e.g. Z275, ZM90, ZMAC140). Remove spaces within the code itself.
> If truly not stated: leave blank.

---

## FIX 3: Item ID / Kundenmaterial Nr. (CRITICAL — EXISTING FIELD)

**Problem**: The field labeled "Kundenmaterial Nr." in German OCs contains the VS article reference, but Docsumo only captures it for some rows.

**New prompt for "Item ID":**
> Extract the customer's own article/material reference number for this line item. In German OCs look for 'Kundenmaterial Nr.', 'Kundenmaterial-Nr.', 'Ihre Materialnummer', 'Kunden-Artikel-Nr.'. In English OCs look for 'Your material no.', 'Customer material no.', 'Customer ref.'. This is typically an alphanumeric code like 'JA2083-B08', 'JE5444-R01', 'KB1355-A01'. Do NOT extract sequential row numbers (001, 002, 1, 2, 3) — if the only identifier available is a row number, leave this field blank.

---

## FIX 4: Payment Terms (CRITICAL — EXISTING FIELD)

**Problem**: "30 Tage nach Rechnungsdatum netto" (OC2) was not extracted.

**New prompt for "Payment Terms":**
> Extract payment terms. Look for: 'Zahlungsbedingung', 'Zahlung:', 'Zahlungsziel', 'Payment terms', 'Payment'.
> Common values to capture exactly as found:
> - 'Vorkasse' or 'Gegen Vorkasse netto' = Prepayment
> - '30 Tage netto' = 30 days net
> - '30 Tage nach Rechnungsdatum netto' = 30 days from invoice date net
> - '30 DAYS FROM INVOICE DATE' = 30 days from invoice date
> - '14 Tage 2% Skonto, 30 Tage netto' = 2% discount 14 days, 30 days net
> Return the value as it appears in the document.

---

## FIX 5: VAT Amount + Gross Amount (CRITICAL — EXISTING FIELDS)

**Problem A**: OC2 does not state a VAT amount, but Docsumo calculated 19% and invented a gross total.

**Problem B**: OC3 states "Tax rate 0.00%" but Docsumo calculated 19% gross anyway.

**New prompt for "VAT Amount":**
> Extract the VAT or MwSt amount ONLY if it is EXPLICITLY stated as a number in the document. Look for: 'MwSt', 'Mehrwertsteuer', 'USt', 'VAT amount', 'Tax amount'. Do NOT calculate it from the net total. If the document says 'zuzüglich gesetzlicher MwSt' without a number, output nothing. If VAT is 0% or not charged, output 0.

**New prompt for "Gross Amount":**
> Extract the total amount INCLUSIVE of VAT/MwSt, ONLY if explicitly stated in the document. This may appear as 'Bruttopreis', 'Gesamtbetrag inkl. MwSt', 'Total incl. VAT', or a final total line after a VAT line. Do NOT calculate it. If not explicitly stated, output nothing.

---

## FIX 6: Supplier Pick-up Address (CRITICAL — EXISTING FIELD)

**Problem**: OC3 (SSAB) — Docsumo extracted "SSAB EUROPE OY RAAHE" (the manufacturer/origin plant) instead of the consignee H&S Steel in Poland. The field needs to look for the delivery/shipping address, not the sender's address.

**New prompt for "Supplier Pick up address":**
> Extract the address where goods will be DELIVERED or from which they must be COLLECTED. This is the consignee or shipping address. Look for: 'Consignee', 'Ship to', 'Deliver to', 'Versandanschrift', 'Lieferanschrift', 'Warenempfänger', 'Delivery address'. For EXW/FCA incoterms, also note the location stated after the incoterm code (e.g. 'FCA Iserlohn' → Iserlohn).
> Do NOT extract the supplier's own letterhead address, factory address, or place of manufacture. Those belong to the seller, not the consignee.

---

## NEW FIELD 1: Quality Choice (NEW — HIGH PRIORITY)

**Where to add**: Line Items table → new column "Quality Choice"

**Prompt:**
> Extract the quality grade or class of the material on this line. Look for:
> - '**IIa**', 'II.Wahl', '2. Wahl', '2.Wahl', 'II Wahl', 'Zweitqualität', 'deklassiert', 'deklassiertes Material' → output: IIa
> - '**Second Choice**', '2nd Choice', 'Second Quality', 'SECOND CHOICE', 'Grade 2', '2A Material' → output: Second Choice
> - 'Prima', '1. Wahl', '1.Wahl', 'Ia', 'Erstqualität', 'First Choice', 'Prime' → output: Prime / 1st Choice
> This often appears in the product description line, not as a labelled field. E.g. 'IIa Spaltband DX54D...' → quality = IIa.
> If no quality tier is stated, leave blank.

---

## NEW FIELD 2: Product Form (NEW)

**Where to add**: Line Items table → new column "Product Form"

**Prompt:**
> Extract the physical form/shape of the product. Look for:
> - 'Spaltband', 'Spaltbänder', 'slit strip' → Slit Coil
> - 'Coil', 'Coils', 'Bund', 'Bänder', 'Breitband', 'VZC', 'Bandbund' → Coil  
> - 'HOT ROLLED STEEL COILS', 'Hot Rolled Coil' → Hot Rolled Coil
> - 'Blech', 'Bleche', 'Tafel', 'Sheet', 'Sheets' → Sheet
> - 'Platte', 'Plate', 'Grobblech' → Plate
> Only state a form if explicitly mentioned. If not stated, leave blank.

---

## NEW FIELD 3: Tariff / CN Code (NEW — IMPORTANT FOR CUSTOMS)

**Where to add**: Line Items table → new column "Tariff/CN Code"

**Prompt:**
> Extract the customs tariff code or CN code for this line item. It may appear as:
> - English: 'Tariff/CN', 'CN code', 'HS code', 'Commodity code', 'Tariff code'
> - German: 'Zolltarifnummer', 'Warennummer', 'Intrastat-Nr.'
> - Dutch: 'Douanetarief'
> This is typically an 8-digit number like 72083800, 72083700.
> Note: different line items may have different codes. Extract the code for this specific item.

---

## NEW FIELD 4: Delivery Date (NEW — IMPORTANT)

**Where to add**: Basic Information → new field "Delivery Date / Week"

**Prompt:**
> Extract the promised or expected delivery date or week. Look for: 'Liefertermin', 'Lieferdatum', 'Bereitstellungstermin', 'Delivery date', 'Del. time', 'KW' (Kalenderwoche = calendar week), 'CW'. 
> Examples: 'Woche 19.2026' → 'Week 19/2026', 'März 2026' → 'March 2026', 'W23, 2026' → 'Week 23/2026'.
> Note any reservation phrase ('unter Vorbehalt', 'subject to', 'u.V.') if present.
> If not stated, leave blank.

---

## NEW FIELD 5: Supplier Notes / Conditions (NEW)

**Where to add**: Basic Information → new field "Supplier Notes"

**Prompt:**
> Extract any commercially important conditions, reservations, or notes. Look for:
> - Delivery reservations: 'unter Vorbehalt', 'Vorbehalt Selbstbelieferung', 'subject to secured supply'
> - No warranty clauses: 'Reklamationen ausgeschlossen', 'ohne Gewährleistung', 'no warranty'
> - Storage fees: 'Lagergeld', 'storage charges' — include amount and trigger
> - Call-off requirements: 'Abruf', 'Abruffrist', 'call-off within X days'
> - No material certificate: 'keine Prüfbescheinigung', 'no test certificate'
> - Bank charges: 'bank charges for buyer's account'
> Include a brief excerpt (max 120 characters per note). Skip standard legal boilerplate.

---

## FIELD NOT NEEDING A CHANGE (from first 3 OCs)

- Thickness, Width, Quantity, Unit Price, Total Value, OC Reference (Supplier Order Number), Supplier Name, Confirmation Date, Incoterm — all extracted correctly.

---

---

# OCs 4–7 — ADDITIONAL SUPPLIERS (Round 2)

---

# OC 4 — Knappstein STAHLSERVICE (146190 / P01750)

## Special note: Image/scanned PDF

This OC is a scanned image — pdfplumber returns blank pages. **Docsumo's OCR reads it correctly**. This is one of Docsumo's clear strengths over pure text extraction tools.

## B — What Docsumo extracted (OCR)

```json
{
  "po_number": "P01750",  ✅  (OCR read correctly)
  "supplier_order_num": "146190",  ✅
  "supplier_name": "Knappstein STAHLSERVICE GmbH",  ✅
  "total_amount": 10116.42,  ✅
  "gross_amount": 12038.54,  ✅
  "vat_amount": 1922.12,  ✅
  "vat_pct": "19%",  ✅
  "incoterm": "FCA",  ⚠️  location missing
  "payment_terms": "Prepayment",  ← needs verification against OC text
  "pickup_address": "Industriestraße 12 57368 Lennestadt",  ✅
  "confirmation_date": "06/05/2026",  ✅
  "lines": [
    {
      "vs_article": "VSI-17890730",  ✅  (supplier provided VS ID — Docsumo got it)
      "description": "Feuerverzinktes Feinblech (C) geölt GI 50/50",
      "grade": "CR380LA",  ✅
      "thickness": 3.0,  ✅
      "width": 1430.0,  ✅
      "quantity": 12.13,  ✅
      "unit_price": 834.0,  ✅
      "total_price": 10116.42,  ✅
      "coating": null  ❌  OC clearly says "GI 50/50"
    }
  ]
}
```

## C — Gaps for OC 4

| # | Field | What OC says | What Docsumo got | Severity |
|---|---|---|---|---|
| G1 | **Coating** | "GI 50/50" in product description | null | 🔴 CRITICAL — coating missed entirely |
| G2 | **Form** | "Feinblech" (thin sheet) or coil — need to check OC | Not extracted | 🟠 HIGH |
| G3 | **Quality** | Likely stated somewhere in OC | Not extracted | Unknown until OC is readable |
| G4 | **Incoterm location** | FCA + location (Lennestadt likely) | "FCA" only | 🟡 MEDIUM |

**New discovery**: GI (galvanized iron, 50g/m² per side) coating is written as "GI 50/50" — separate from the grade string. The existing coating prompt covers Z/ZM/AZ prefixes but NOT the GI format.

---

# OC 5 — EMW Stahl Service GmbH (2000046743 / P01752)

## A — Ground truth from PDF

| Field | Value |
|---|---|
| VS PO Number | P01752 (in **"Referenznummer:"** field — atypical!) |
| OC Reference | 2000046743 |
| Date | 07.05.2026 |
| Supplier | EMW Stahl Service GmbH, Neunkirchen |
| Incoterms | FCA Weidenau |
| Payment Terms | innerhalb von 30 Tagen ohne Abzug [30 days net, no discount] |
| Net Total | €30,724.32 |
| VAT | 19% → €5,837.62 → Gross €36,561.94 |
| Delivery | T 11.05.2026 ("T" = Terminauftrag / scheduled delivery order) |

**1 line item:**

| Field | Value |
|---|---|
| Supplier article | 18504713 (in "Material:" field) |
| Description | Breitband [wide strip/coil] |
| Grade | HR660Y760T-CP (complex phase, yield 660 / tensile 760 MPa) |
| Coating | GI50/50 U O (galvanized iron 50g/m² — "U O" = oil, unspecified surface) |
| Thickness | 2.50 mm |
| Width | 1260.00 mm |
| Quantity | 23.276 t |
| Price | 1,320.00 EUR/1000 KG = €1,320/t |
| Value | €30,724.32 |

Other notable details:
- Material test: "Werkszeugnis Prüfbesch.gemäß EN10204-3.1" [EN 10204 3.1 certificate required]
- Thickness tolerance: ±0.220 mm
- Width tolerance: +6.00 / -0.00 mm
- "Achslage bei Verladung stehend in Mulde + Steher hoch" [upright loading, cradle + upright bracket]
- "Unsere Lieferverpflichtungen stehen unter dem Vorbehalt richtiger und rechtzeitiger Selbstbelieferung" [delivery subject to receiving material ourselves]

*(Not yet in Docsumo — no extraction comparison available)*

## C — New gaps discovered from OC 5

| # | Field | Observation | Severity |
|---|---|---|---|
| G1 | **PO Number location** | PO is in "Referenznummer:" field — not "Ihre Bestellung" or "Bestell-Nr." | 🔴 CRITICAL if Docsumo prompt is too narrow |
| G2 | **Coating GI format** | "GI50/50 U O" — GI prefix not covered by existing coating prompt | 🔴 CRITICAL |
| G3 | **Supplier article in "Material:" field** | Not the usual "Artikel-Nr." or "Kundenmaterial Nr." | 🟠 HIGH |
| G4 | **Tensile/Yield in grade name** | HR660Y760T-CP encodes Rp660/Rm760 in the grade string | 🟡 LOW — not a separate field issue |
| G5 | **Payment Terms** | "innerhalb von 30 Tagen ohne Abzug" — variant wording | 🔴 CRITICAL — another format to add to prompt |
| G6 | **Delivery reservation** | "Vorbehalt richtiger und rechtzeitiger Selbstbelieferung" | 🟠 HIGH — should be in Supplier Notes |

---

# OC 6 — BILSTEIN Kaltband (211880 / P01773)

## A — Ground truth from PDF

| Field | Value |
|---|---|
| VS PO Number | P01773 (in "Ihre Bestell-Nr." field) |
| OC Reference | 211880 |
| Date | 19.05.2026 |
| Supplier | BILSTEIN GmbH & Co. KG, Hagen |
| Incoterms | FCA Hagen (INCOTERMS 2020) |
| Payment Terms | Innerhalb 30 Tagen ohne Abzug [30 days net, no discount] |
| Total | €1,022.40 |
| VAT | 19% (explicitly stated: "Mehrwertsteuer: 19,00%") |
| Delivery | 20.05.2026 (specific date — day after OC!) |
| VS Article ID | **VSI-17892446** (explicitly labeled "VS Artikel-ID") |
| Supplier Article | 30058974 (labeled "Lieferantenartikel-ID") |
| Quality | "2A Material" AND "Slit Coils 2nd Choice" |
| Form | Slit Coils |
| Grade | DC04 |
| Finish | Cold Drawn / Soft (+LC) = uncoated cold rolled |
| Dimensions | 1.79mm × 279mm |
| Quantity | 2,556 KG = 2.556 t |
| Price | 400.00 EUR/1000 KG = 400 EUR/t |
| Additional note | "Verladung - Liegend" [loading flat] |
| PCF data | 2.479 kg CO2e/t Kaltband [carbon footprint data] |
| Reason for 2nd choice | "Rust / Punktrost" [surface rust] |

## B — What Docsumo extracted

```json
{
  "po_number": "P01773",  ✅
  "supplier_order_num": "211880",  ✅
  "supplier_name": "BILSTEIN GmbH & Co. KG",  ✅
  "total_amount": 1022.4,  ✅
  "gross_amount": 1216.656,  ✅  (VAT explicitly stated → correct gross this time)
  "vat_amount": 194.26,  ✅
  "vat_pct": "19%",  ✅
  "incoterm": "FCA Hagen",  ✅  (including location!)
  "payment_terms": null,  ❌  "Innerhalb 30 Tagen ohne Abzug" MISSED
  "pickup_address": null,  ✅  (EXW — no separate pickup noted in OC)
  "confirmation_date": "19/05/2026",  ✅
  "lines": [
    {
      "vs_article": "VSI-17892446",  ✅  EXCELLENT — supplier wrote VS Article ID
      "grade": "DC04",  ✅
      "thickness": 1.79,  ✅
      "width": 279.0,  ✅
      "quantity": 2.556,  ✅
      "unit_price": 400.0,  ✅
      "coating": null,  ✅  (uncoated — correct)
      "quality": ← not extracted ❌  OC says "2A Material" / "2nd Choice"
      "form": ← not extracted ❌  OC says "Slit Coils"
    }
  ]
}
```

## C — Gaps for OC 6

| # | Field | What OC says | What Docsumo got | Severity |
|---|---|---|---|---|
| G1 | **Payment Terms** | "Innerhalb 30 Tagen ohne Abzug" | null | 🔴 CRITICAL |
| G2 | **Quality Choice** | "2A Material" + "Slit Coils 2nd Choice" | Not extracted | 🔴 CRITICAL |
| G3 | **Form** | "Slit Coils" | Not extracted | 🟠 HIGH |
| G4 | **Delivery Date** | 20.05.2026 (specific date) | Not extracted | 🟠 HIGH |
| G5 | **PCF / Carbon footprint** | "2.479 kg CO2e/t Kaltband" | Not extracted | 🟡 LOW (nice to have) |
| G6 | **Supplier Notes** | Loading: liegend [flat], rust reason for downgrade | Not extracted | 🟠 HIGH |

**Positive finding**: Bilstein explicitly writes the VS Article ID on the OC ("VS Artikel-ID: VSI-17892446"). Docsumo captures it ✅. When suppliers provide this, line matching is perfect. Encourages us to ask more suppliers to include the VS article ID on their OCs.

---

# OC 7 — Stahlhandel Vogt GmbH (7628990 / P01771)

*This is the worked example in OC Analysis Instructions v1.1.*

## A — Ground truth from PDF

| Field | Value |
|---|---|
| VS PO Number | P01771 (embedded in delivery address block — no "Bestell-Nr." label!) |
| OC Reference | 7628990 |
| Date | 18.05.2026 |
| Supplier | Stahlhandel Vogt GmbH & Co. KG, Bottrop |
| Incoterms | CPT (Frachtfrei Bestimmungsort) |
| Payment Terms | Vorkasse ohne Abzug [Prepayment, no discount] |
| Net Total | €18,883.20 |
| VAT | 19% → €3,587.81 → Gross €22,471.01 |
| Delivery | KW 23-24 "unter Vorbehalt des Selbsterhalts" |
| Shipping Address | Spedition Josef Wiechers GmbH, Bremerhaven Str. 10, D-47229 Duisburg-Rheinhausen (Logport) |
| Quality | IIa (in "VZC Feuerverzinktes Coil, IIa - Material"), also "II. Wahl" on page 2 |
| Form | VZC (= Verzinktes Coil) = Coil |
| Grade | DX51D (from "DX51D+Z275") |
| Coating | Z275 (from "+Z275") |
| Finish | Feuerverzinkt [hot-dip galvanized] |
| Tensile Strength | **Rm 312 N/mm²** (in product description: "DX51D+Z275 trockenRe 203 / Rm 312 / 37,0 %") |
| Thickness | 0.82 mm |
| Width | 1003 mm |
| Quantity | 22,480 KG = 22.48 t |
| Price | €840.00/t |
| Tariff | Nimexe-Nr. 7210 (old Nimexe code — older format, 4 digits) |

**Critical supplier notes (page 2 & 3):**
- "IIA/deklassiertes Material wird unter Ausschluss jeglicher Gewährleistung geliefert" [no warranty]
- "Abwertungsgründe: Diverse Oberflächenfehler und Qualitätsabweichungen" [downgrade reason: surface defects]
- "14 Tage nach Fertigmeldung wird Material berechnet" [invoiced 14 days after ready notification]
- "Lagergeld in Höhe von 0,80 €/to je angefangener Woche" [storage fee €0.80/t per week — triggered from Fertigmeldung + 14 days]
- "Bestätigung erfolgt vorbehaltlich des Selbsterhalts" [delivery subject to receiving material]

*(Not yet in Docsumo via the automated pipeline — no extraction comparison available)*

## C — New gaps discovered from OC 7

| # | Field | Observation | Severity |
|---|---|---|---|
| G1 | **PO number in delivery block** | "P01771" appears only inside the delivery address layout, not in a labeled field like "Ihre Bestell-Nr." | 🔴 CRITICAL — easily missed by Docsumo |
| G2 | **Tensile strength in grade line** | "Rm 312 N/mm²" is part of the product description, not a dedicated field | 🟠 HIGH — Docsumo needs to scan description for Rm/Re values |
| G3 | **Tariff code Nimexe format** | "Nimexe-Nr. 7210" — only 4 digits, older format (not CN 8-digit) | 🟡 MEDIUM — still useful for customs |
| G4 | **Invoicing trigger** | "14 Tage nach Fertigmeldung wird Material berechnet" — billing not on delivery | 🔴 CRITICAL for cash flow — must be in supplier notes |
| G5 | **Storage fee with trigger** | "0,80€/to je angefangener Woche" — starts 14 days after ready notice | 🔴 CRITICAL for cost control |
| G6 | **Shipping address = forwarder** | Wiechers GmbH is a freight forwarder, not the end buyer — address comparison with Odoo SO needs care | 🟡 MEDIUM |

---

---

# UPDATED MASTER GAPS SUMMARY (all 7 OCs)

| Gap | Seen in | Severity | Fix type |
|---|---|---|---|
| PO number hallucination (blank field) | OC1 | 🔴 CRITICAL | Prompt fix |
| PO number in unlabeled/wrong field | OC7 (delivery block), OC5 ("Referenznummer") | 🔴 CRITICAL | Prompt fix |
| Quality Choice (IIa / Second Choice / 2A) | OC1, OC3, OC6, OC7 | 🔴 CRITICAL | New field |
| Coating GI format (GI50/50) | OC4, OC5 | 🔴 CRITICAL | Prompt fix |
| Coating with internal spaces (ZMAC, ZMACO) | OC1 | 🔴 CRITICAL | Prompt fix |
| Coating without + prefix | OC1 | 🟠 HIGH | Prompt fix |
| Payment Terms (German variants) | OC2, OC5, OC6 | 🔴 CRITICAL | Prompt fix |
| VAT not stated → wrong gross calculated | OC2, OC3 | 🔴 CRITICAL | Prompt fix |
| Consignee/delivery address vs manufacturer | OC3 | 🔴 CRITICAL | Prompt fix |
| Tariff/CN Code | OC3, OC7 (Nimexe) | 🔴 CRITICAL | New field |
| Tensile strength in product description | OC7 | 🟠 HIGH | New field |
| Form (Spaltband, Slit Coil, HR Coil) | OC1, OC3, OC6 | 🟠 HIGH | New field |
| Finish (feuerverzinkt) | OC1 | 🟠 HIGH | New field |
| Item ID — Kundenmaterial Nr. inconsistent | OC1 | 🔴 CRITICAL | Prompt fix |
| Delivery Date | OC1, OC3, OC6, OC7 | 🟠 HIGH | New field |
| Invoicing trigger / Fertigmeldung billing | OC7 | 🔴 CRITICAL | Supplier Notes |
| Storage fee with trigger | OC7 | 🔴 CRITICAL | Supplier Notes |
| Delivery reservation note | OC2, OC5, OC7 | 🟠 HIGH | Supplier Notes |
| PCF carbon footprint | OC6 | 🟡 LOW | Supplier Notes |

---

## ADDITIONAL PROMPT FIX: VS Order Number (expanded for more locations)

**Updated problem**: P01771 (Vogt) has the PO number embedded in the delivery address block without a label. P01752 (EMW) uses "Referenznummer:" instead of "Ihre Bestellung".

**Updated prompt for "VS Order Number":**
> Extract the Vanilla Steel purchase order number. Format: P0XXXX (e.g. P01740, P01755, P01771).
> Look everywhere in the document for this pattern, including:
> - Labeled fields: 'Ihre Bestellung', 'Ihre Bestell-Nr.', 'Bestellnummer', 'Referenznummer', 'Referenz', 'Your order no.', 'Buyer's order', 'PO', 'Order no.', 'Ref', 'Customer PO'
> - Delivery address blocks: the PO number sometimes appears next to the delivery address without a label
> - Header/footer areas
> Match the pattern P followed by 4–6 digits (e.g. P01740, P01752, P01771).
> CRITICAL: Only extract a COMPLETE number. If you see only "P-" with nothing after it, output nothing — do NOT generate or guess a number.

---

## ADDITIONAL PROMPT FIX: Coating (add GI format)

**Updated prompt for "Coating":**
> Extract the coating weight class. It may appear as:
> 1. After a '+' in the grade: 'DX51D+Z275' → Z275, 'HX380LAD+ZM' → ZM
> 2. Separated from grade with a space: 'DX51D MAC 120 g/m²' → MAC120
> 3. With internal spaces: 'Z M A C 140 g/m²' = 'ZMAC140' — treat spaced single letters as one continuous code
> 4. Standalone after grade: 'CR380LA GI50/50' → GI50/50
> 5. In product description: 'Feuerverzinktes Feinblech GI 50/50' → GI50/50
> Common types:
> - Z = hot-dip zinc (e.g. Z275 = 275g/m²)
> - ZM, ZMA, ZMAC = zinc-magnesium alloy
> - AZ, ZA = aluzinc
> - ZE = electrolytic zinc
> - GI = galvanized iron (e.g. GI50/50 = 50g/m² each side)
> Always include the weight number. Remove internal spaces from codes.
> If not stated: leave blank.

---

## ADDITIONAL NEW FIELD: Tensile Strength (line item level)

**Where to add**: Line Items table → new column "Tensile Strength (Rm)"

**Prompt:**
> Extract the tensile strength (Rm) for this line item. Look for:
> - In dedicated fields: 'Rm', 'Rm ≥', 'tensile strength', 'Zugfestigkeit'
> - In the product description line: e.g. 'DX51D+Z275 trocken Re 203 / Rm 312 / 37,0 %' → Rm = 312
> - After the grade string: 'HR660Y760T-CP' — the 760T encodes Rm = 760 MPa in the grade name
> Output the value in MPa/N/mm² (they are equivalent). If not stated, leave blank.

---

## PRIORITY ORDER FOR IMPLEMENTATION (updated — all 7 OCs)

| Priority | Field/Fix | Why urgent |
|---|---|---|
| 1 | VS Order Number (fix all locations + no-hallucination) | Wrong PO match = wrong everything |
| 2 | Payment Terms (expand German variants) | Missed in 3 of 7 OCs tested |
| 3 | Coating (add GI, fix spaced codes, no-plus) | Wrong or missing coating in 4 of 7 OCs |
| 4 | Quality Choice (new field) | Missed in 4 of 7 OCs — commercially critical |
| 5 | VAT/Gross (no calculation) | Wrong invoice amount in 2 of 7 OCs |
| 6 | Supplier Notes (new field — invoicing trigger, storage fee, reservation) | Invoicing trigger/storage fee = direct cost risk |
| 7 | Tariff/CN Code (new field — include Nimexe) | Required for customs in all cross-border OCs |
| 8 | Consignee Address (fix prompt) | Wrong for CIP/CPT deliveries |
| 9 | Delivery Date (new field) | Missed in most OCs |
| 10 | Tensile Strength at line item level | Useful for spec verification |
| 11 | Product Form (new field) | Useful but lower risk |
| 12 | Finish (new field) | Derivable from grade/coating in most cases |
