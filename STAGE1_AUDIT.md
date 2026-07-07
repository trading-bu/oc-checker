# Stage 1 — Extraction Audit Results (2026-07-06)

10 OC PDFs audited across 6 supplier formats. Ground truth: PDFs read visually,
compared against stored Docsumo extractions in `processed_ocs.json`.

## Decision Gate Result: PASS (≥85%) → Skip Stage 2 rebuild, proceed to Stage 3 with targeted extraction patches

Accuracy on gate fields (qty / price / dims), excluding the invalid P01821 doc (24 line items):

| Field | Correct | Accuracy |
|-------|---------|----------|
| Quantity | 23/24 | 95.8% |
| Unit Price | 24/24 | 100% |
| Thickness | 23/24 | 95.8% |
| Width | 20/24 | 83.3% |
| **Combined** | **90/96** | **93.75%** |

Grade/coating: ~95% (all misses recoverable — cross-field or shared-header cases).
po_number & oc_ref: 100% across all valid docs.

## Per-PDF Results

| PDF | Supplier | PO | Result |
|-----|----------|----|--------|
| 146190 | Knappstein | P01750 | 7/7 perfect |
| 146358 | Knappstein | P01791 | 23/27 — page-break width shift (see Bug 1) |
| 01164295 | ESB | P01778 | 30/32 — shared-header grade/coating null on 2nd line |
| TILKKURA_85554 | SSAB | P01757 | perfect (grades correctly null — not in PDF) |
| TILKKURA_85555 | SSAB | P01758 | width missing on page-2 item 004 |
| AB 212205 | Bilstein | P01779 | 7/7 perfect |
| AB 212618 | Bilstein | P01811 | qty ❌ 0.003 vs 2.978 MT (see Bug 2) |
| Auftrag 2000049586 | Schäfer/EMW | P01786 | 8/8 perfect |
| Auftrag 2000050946 | Schäfer/EMW | P01802 | 21/21 perfect |
| "Bestellung - P01821" | Risse+Wilke | P01821 | INVALID — see Bug 3 |

## Bugs Found (priority order)

### Bug 1 — Page-break / shared-header spec shift (MOST DANGEROUS)
When a line's spec block spans a page break (Knappstein 146358) or one description
header covers multiple positions (ESB, SSAB 85555 item 004), Docsumo leaves dims
null on one line and/or shifts values onto the WRONG lines.
- Knappstein 146358: widths 1062/1095 assigned to positions 3/4 instead of 2/3;
  width 1155 never extracted. Produced 2 FALSE mismatch alerts in Slack
  (PDF actually matches Odoo exactly), and silently skipped checks on another line.
- Impact: false alarms + hidden true state. Worst possible failure mode.

### Bug 2 — European thousands separator on small kg values
Bilstein "Menge in KG 2.978" (= 2,978 kg = 2.978 MT) parsed as 2.978 kg → 0.003 MT.
Only bites when kg < 10,000 (one digit before the dot). "10.086" parsed fine.
Self-verifying fix: qty × unit_price must ≈ printed line total (1.131,64 EUR proves 2.978 t).
The logged P01811 "mismatch" was a false alarm — supplier confirmed the full qty.

### Bug 3 — Own documents processed as supplier OCs
- P01821: VS's own Odoo-generated "Bestellung - P01821.pdf" was graded as an OC.
  The 6/6 "confirmed" is Odoo compared against itself — circular, meaningless.
  The REAL OC (Auftragsbestätigung 6300167921) sits unprocessed in the folder.
- P01814: same problem — "Purchase Order - P01814.pdf" from vanillasteel.com.
- Fix: skip PDFs from vanillasteel.com / titled "Bestellung"/"Purchase Order" /
  PDF metadata Producer=Odoo. Invalidate P01821 + P01814 statuses and re-process real OCs.

### Gap 4 — delivery_date never extracted
Present in ALL 10 PDFs (exact dates: ESB 29/05/2026, Bilstein Termin 30.05.2026;
week formats: SSAB "W23, 2026", EMW "W 23.2026", Knappstein "KW 19/2026").
`docsumo_client.py` has no delivery_date field. Needs Docsumo field or supplement.

### Gap 5 — Minor
- Coil numbers not extracted (SSAB prints them per line).
- Knappstein "VSO001262" (VS order ref) misattributed to coil_number field.
- EMW split-pickup ("Pos 100+200 Weidenau / Pos 300 Neunkirchen") only partially flagged.
- Silent "skip" on null fields hides extraction failures — a null dim on a line that
  has dims in Odoo should show as ⚠️ pending, not silently pass.

## Recommended Stage 3 Scope (updated by this audit)
1. Doc-type guard (Bug 3) — cheap, do first; also clear P01814/P01821 from log.
2. Arithmetic self-check: qty × unit_price ≈ total_price → auto-correct thousands-separator
   misparses (Bug 2) and flag lines where dims are null but Odoo has values (Bug 1 mitigation).
3. Treat null-extracted fields as "pending confirmation", not silent skip.
4. Add delivery_date + incoterms to per-line output (Gap 4, feeds Stage 4 Slack format).
