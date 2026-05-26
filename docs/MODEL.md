# DATA MODEL — Breathe ESG Ingestion Platform

## Core Philosophy

The data model serves two masters: **operational correctness** (ingest data from
messy sources, normalize it, surface it for review) and **audit defensibility**
(every number that goes to an auditor must be traceable to its source with a
complete chain of custody). These requirements pull in different directions —
audit defensibility wants immutability, operational correctness wants the ability
to flag and correct errors — so the model separates the concerns.

---

## Entity Overview

```
Tenant ────────────────────────────────────────────────────────────────────┐
  │                                                                         │
  ├── IngestionBatch (one per file upload)                                 │
  │       └── RawRow (verbatim row from source, one per CSV row)           │
  │               └─── EmissionRecord (normalized, reviewable)  ───────────┘
  │                         └── AuditEvent (append-only log)
  └── EmissionRecord (tenant FK directly for fast queries)
```

---

## Multi-Tenancy Design

**Decision: Row-level isolation via FK, not schema-per-tenant.**

Every table that holds emissions data carries a `tenant` FK. Queries always
filter on `tenant_id`. This is the simplest approach for a prototype and allows
the Django ORM to enforce isolation at the application layer.

**What I deliberately did not do:** schema-per-tenant (separate Postgres schema
per client). Schema-per-tenant gives stronger isolation guarantees and makes it
physically impossible to accidentally leak one client's data to another through
a missing filter. It also simplifies cross-tenant queries (you just connect to
the right schema). The cost is higher operational complexity: migrations must
run on every schema, connection pooling is harder, and Django's ORM doesn't
natively support schema switching at runtime.

**For production:** schema-per-tenant is the right call for an ESG SaaS where
client data sensitivity and regulatory requirements are high. The migration path
from row-level to schema-level is non-trivial but the FK model keeps that
option open since tenant IDs are already on every row.

---

## Scope 1 / 2 / 3 Categorization

Scope is **stored on EmissionRecord** (not computed on the fly) and assigned
during ingestion by the parser, not by the analyst.

| Source type | Default scope | Rationale |
|-------------|---------------|-----------|
| SAP fuel/procurement | Scope 1 | Company owns the combustion assets |
| Utility electricity | Scope 2 | Purchased energy, indirect |
| Travel (flights, hotels, ground) | Scope 3 | Business travel, value chain |

Edge cases:
- If an SAP row contains purchased electricity (e.g. a utility invoice routed
  through SAP procurement), it should be Scope 2. We detect this by looking for
  keywords like "electricity" or "kWh" in the material description and flag it
  for human review rather than auto-classifying.
- Scope 3 has 15 sub-categories (GHG Protocol). We handle only Category 6
  (business travel) in this prototype. Category 1 (purchased goods) would be
  the next to add for procurement data.

---

## Source-of-Truth Tracking

Every `EmissionRecord` has a `batch` FK pointing to the `IngestionBatch` that
created it, which in turn has:
- `filename`: the original file name
- `file_content`: the raw CSV stored verbatim (up to 100KB)
- `uploaded_by`, `created_at`: who uploaded and when

Every `EmissionRecord` also has a `RawRow` counterpart (OneToOne) storing the
verbatim key-value dict of that specific row from the source file. This means:

> Even after normalization, unit conversion, and emission factor application,
> you can always reconstruct exactly what the source said.

If a row is edited after ingestion (`is_edited=True`), the original `RawRow`
is preserved unchanged. The edit is tracked via `AuditEvent` with `before_state`
and `after_state` JSON snapshots.

---

## Unit Normalization

All physical quantities are stored **twice**: once verbatim (`raw_quantity`,
`raw_unit`), once normalized to SI-adjacent base units:

| Category | Normalized unit | Notes |
|----------|----------------|-------|
| Fuel | L (litres) | US/UK gallons, m³ converted on ingest |
| Electricity | kWh | MWh, GJ, kJ converted |
| Distance | km | Miles converted |
| Hotel stays | nights | Count |

CO₂e is always `kg CO₂e`, computed as `quantity_normalized × emission_factor`.

Emission factors are recorded with their source (`emission_factor_source` field)
so auditors can verify the factor provenance. We use DEFRA 2023 and IEA 2022
as primary sources.

---

## Audit Trail (AuditEvent)

`AuditEvent` is **append-only**. No row is ever updated or deleted. Every state
transition on an `EmissionRecord` appends a new event:

| Action | When |
|--------|------|
| `created` | Ingestion pipeline creates the record |
| `reviewed` | Analyst approves or rejects |
| `flagged` | Analyst or system flags as suspicious |
| `edited` | Any field on the record is changed |
| `locked` | Record is locked for audit submission |

The `before_state` and `after_state` JSON fields capture a snapshot of the
relevant fields before and after the change.

**Lock semantics:** Once `is_locked=True`, the record cannot be edited or have
its review status changed. This is the "signed off" state before export to
auditors. In this prototype, locking is manual. In production it would be
triggered by a batch-close workflow where an authorized user locks all approved
records for a reporting period.

---

## Suspicion Flagging

The ingestion pipeline auto-flags rows that look anomalous:
- Quantity outliers (e.g. >50,000 L fuel in one movement, <10 kWh electricity)
- Billing periods outside 28–92 days
- Unknown or ambiguous fuel types (inferred diesel from non-specific description)
- Missing distance data for flights (estimated from airport codes lookup)
- Negative quantities (possible credit notes or meter read errors)

Flagged rows get `review_status='suspicious'` and a list of flag strings in the
`flags` JSON field. Analysts can see exactly which flags fired and why.

---

## Indexes

| Index | Rationale |
|-------|-----------|
| `(tenant, scope)` | Most common dashboard query: "show me all Scope 2 for client X" |
| `(tenant, review_status)` | Review queue filter |
| `batch` | Drill-down from batch list to records |
| `activity_date` | Time-series queries for charts |

---

## What the model does NOT yet handle

1. **Reporting periods**: There's no `ReportingPeriod` entity for formal
   GHG inventory boundaries (typically calendar year). In production you'd
   want records to be assigned to a reporting period, with the period having
   a status (open → review → locked → submitted).

2. **Custom emission factors per tenant**: The current model uses global
   factors. Enterprise clients often have negotiated grid mix certificates
   (RECs, PPAs) that change their Scope 2 factor. A `TenantEmissionFactor`
   override table would handle this.

3. **Supplier-specific Scope 3 factors**: Category 1 (purchased goods) needs
   product-level emission factors, not just activity-based estimates.
