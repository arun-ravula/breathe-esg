# TRADEOFFS — Three Things Deliberately Not Built

## 1. Authentication and Access Control

**What I did not build:** Any real authentication. The app has Django's auth
model and an `admin` user, but the API endpoints are open. There is no login
screen, no JWT/session-based auth on the React side, no role enforcement
(analyst vs. admin vs. read-only).

**Why:** Authentication is configuration, not design. Building login pages,
JWT middleware, refresh token rotation, and RBAC for a 4-day prototype burns
time that should go to the data model and ingestion logic — the things the
assignment actually tests. Any competent engineer can add Django REST Framework's
token auth in 2 hours; the interesting question is whether the data model is
correct and whether the ingestion handles real-world messiness.

**What production would need:** JWT auth with refresh, Django groups for Analyst
/ Admin / Auditor roles, row-level permission checks that verify `request.user`
belongs to the record's `tenant`, and probably SSO (SAML/OIDC) for enterprise
clients who don't want to manage passwords separately.

---

## 2. Reporting Period Management and Audit Export

**What I did not build:** Formal reporting period lifecycle management — the
workflow where an authorized user closes a reporting period, locks all approved
records for that period, generates a structured export (CSV, JSON, or PDF) for
the external auditor, and prevents further editing.

**Why:** This is the last mile of the workflow, not the first mile. The
assignment says "approve rows before they're locked for audit" — so the _concept_
of locking exists (the `is_locked` field is on the model, the `locked` audit
event is defined). Building the full export + period-close UI would be another
day's work and adds surface area without illuminating the interesting design
questions, which are about ingestion and normalization.

**What the gap means in practice:** Right now you can approve individual records
but there's no "lock all approved records for Q1 2024 and generate the audit
package" button. An auditor would need to query the API directly or we'd need
to build this before any real audit submission.

**What production would need:** A `ReportingPeriod` model with status lifecycle
(open → under_review → locked → submitted), a period-close workflow that bulk-
locks all approved records, a structured export (probably GHG Protocol-aligned
CSV or JSON), and a read-only auditor portal view.

---

## 3. Scope 3 Completeness (Purchased Goods, Upstream Transport, Waste)

**What I did not build:** Scope 3 beyond business travel. GHG Protocol Scope 3
has 15 categories. We handle Category 6 (business travel) via the travel
ingestion pipeline. Category 1 (purchased goods and services), Category 4
(upstream transportation), and Category 12 (end-of-life treatment of sold
products) are all absent.

**Why:** Scope 3 Category 1 is the hardest and most data-intensive part of any
GHG inventory. It requires either spend-based estimation (spend in category ×
EEIO emission factor) or activity-based data from suppliers. Spend-based
estimation is feasible from the SAP procurement data we already ingest, but
mapping SAP material groups or G/L account codes to EEIO categories requires a
lookup table that is client-specific and usually takes weeks to build and
validate with the client.

Building a fake mapping and plugging in EEIO factors would create the impression
of completeness without the substance. Better to be explicit that Scope 3
Category 1 is not handled and explain what it would take.

**What production would need:** A material group → EEIO category mapping table
(client-specific), integration with an EEIO database (US EPA USEEIO or
Exiobase), and a spend-based calculation pipeline that runs after SAP data is
ingested. Supplier-specific factors (for clients with supplier engagement
programs) would be an overlay on top of the EEIO base.
