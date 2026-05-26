# DECISIONS — Ambiguities Resolved

## SAP: Format Choice

**Chosen:** SAP MM flat file export (semicolon-delimited), equivalent to what
you'd get from ME2M (Purchase Order Report) or MB51 (Material Document List).

**Why not IDoc?** IDocs are XML-like and used for system-to-system integration
(SAP to SAP, or SAP to middleware like MuleSoft). A sustainability analyst
running a periodic report would not typically export IDocs; they'd run a
transaction like MB51 and export via "List → Export → Spreadsheet". The flat
file is the realistic format for ad-hoc extracts.

**Why not OData?** OData (via the SAP Gateway) requires a configured service
endpoint and authentication. It's the right answer for a production integration
where Breathe ESG would pull data programmatically. But "the facilities team
pulls data" language in the brief implies manual exports, not automated API
pulls. OData would be the V2 answer; CSV upload is the right V1.

**Why not BAPI?** BAPI is a function module called from ABAP. Not relevant for
a data export scenario.

**Column header handling:** SAP exports often come with German column headers
(`Buchungsdatum`, `Werk`, `Menge`) depending on the SAP system language setting.
The parser maintains a bidirectional map of German ↔ English column names.

**Movement types:** We filter on movement types that indicate consumption
(201: goods issue to cost center, 261: goods issue to production order, etc.).
We ignore goods receipts (101), returns (102), and inter-plant transfers (301)
because those don't represent emissions events directly.

**What we deliberately ignored:**
- Multiple line items in one document (we treat each CSV row independently)
- Goods vs. services distinction in procurement (procurement category mapping
  to Scope 3 Category 1 would require a material-to-category lookup table)
- Batch management (SAP batches for traceability of raw material origin)
- Currency normalization (amount fields are present but unused; CO₂e is what
  matters, not spend)

---

## Utility: Format and Ingestion Mode

**Chosen:** Portal CSV export, one row per billing period per meter.

**Why not PDF bill parsing?** PDF is the most common format consumers receive,
but enterprise accounts with multiple meters typically access a portal (BESCOM
in India, UK Power Networks, ERCOT in Texas, etc.) where they can export CSV
for their entire account portfolio. PDF parsing with OCR is fragile and requires
a different toolchain (pdfplumber, tesseract). For a prototype in 4 days, CSV
is the right starting point.

**Why not utility API?** Few utilities offer developer APIs. In India, BESCOM
and TATA Power do not. Green Button Data (US standard) exists but adoption is
patchy. API integration is the right long-term answer for large clients with
real-time monitoring requirements, but not the common case today.

**Billing period vs. calendar month:** Utility bills don't align with calendar
months. A meter read on Jan 5 to Feb 4 spans two months. We store `period_start`
and `period_end` separately. `activity_date` = `period_start` for consistency.
Reporting queries that need monthly breakdowns should prorate by days in period —
we flag this in the analyst UI but don't automate the proration (that's a
reporting-layer concern, not an ingestion concern).

**Emission factor:** We default to IEA 2022 India grid (0.7082 kg CO₂e/kWh) as
our primary tenant is assumed to be India-based. In production, the emission
factor would be a tenant-configurable field, with regional grid factors (India
state-wise, UK, EU) stored in a lookup table. Location-based vs. market-based
accounting (for RE certificates) would also need to be handled.

**What we ignored:**
- Demand charges and peak/off-peak tariff splits (not relevant to emissions)
- Power factor penalties
- Multi-commodity bills (gas + electricity from same utility)
- Reactive power (kVAR)

---

## Travel: Format and Ingestion Mode

**Chosen:** Concur/Navan-style CSV export with one row per travel segment.

**Why CSV, not API?** Concur's SAP Concur Travel API (v4) and Navan's API both
exist, but they require OAuth setup with the client's travel platform account.
The common workflow is: travel manager exports a date-range report from the
platform UI as CSV. Modelling the CSV is correct for V1.

**Key design decision — distance estimation:** Concur reports don't always
include distance. They include origin and destination airport codes. We maintain
a lookup table of great-circle distances for common routes. When distance is
missing and we can compute it from airport codes, we do so and flag the row so
an analyst knows the distance is estimated, not sourced. When airport pair is
not in our table, we flag the record as suspicious and use 1000km as a fallback
(rather than blocking the row entirely).

**Cabin class multipliers:** DEFRA 2023 applies multipliers for business class
(~2x) and first class (~2.9x) relative to economy for the radiative forcing
effect at altitude. We apply these. Some methodologies (e.g. ICAO) don't apply
RFI — this is a methodological choice worth flagging to clients.

**Hotel emission factor:** We use DEFRA's average hotel night factor
(18.4 kg CO₂e/night). In reality this varies enormously by hotel star rating,
country, and whether the hotel has an energy efficiency certification. The right
answer is to get hotel-level factors from platforms like Cornell's Hotel
Sustainability Benchmarking Index. For a prototype, average is defensible.

**What we ignored:**
- Rail (Eurostar, Indian Railways — we have a factor but no distance data)
- Private flights (very different emission methodology)
- Car rental (we have a factor but rental car category in Concur is inconsistent)
- Offsetting/credit purchases reported in travel platforms

---

## Ingestion Mechanism: File Upload, Not API Pull

All three sources use file upload (multipart/form-data CSV) rather than
scheduled API pulls.

**Why:** "A PM sends you this" implies an existing client with manual data
workflows. File upload is:
- Lower friction for onboarding (no OAuth, no IT involvement from client)
- Compatible with all three source types as they exist today
- Auditable (the file itself is stored in the database)

API pull would be the right V2 answer for clients who can set up automated
connections. The model supports this — `IngestionBatch` has a `source_type`
and `filename` field; an automated pull would set `filename` to something like
`api_pull_2024-01-01` and the rest of the flow would be identical.

---

## Questions I'd ask the PM before going further

1. **Reporting period:** What's the inventory boundary? Calendar year? Fiscal
   year? Do we need to handle mid-year onboarding (partial years)?

2. **Emission factor selection:** Which methodology? DEFRA, EPA, or client-
   specific? Do clients have RECs or PPAs that affect Scope 2 accounting?

3. **Scope 3 categories beyond travel:** Which other Scope 3 categories matter
   for this client? Purchased goods? Upstream transport? Waste?

4. **Approval workflow:** Is one analyst sufficient to approve, or is there
   a two-eye principle required? Does the PM or CFO need to sign off before
   the data is locked for audit?

5. **Auditor access:** Does the auditor get read-only access to the platform,
   or do we export a report? In what format?

6. **Data correction policy:** If a supplier sends corrected data after an
   upload, do we re-ingest (creating a new batch) or update in place? The
   current model supports re-ingestion; in-place updates require careful audit
   trail design.
