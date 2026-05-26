# Breathe ESG — Emissions Ingestion Platform

A Django REST + React prototype for ingesting, normalizing, and reviewing emissions data from three enterprise source types: SAP fuel/procurement, utility electricity data, and corporate travel.

## Live App
**[→ Deployed on Railway/Render — URL after deployment]**

**Login:** `analyst / breathe123` (or `admin / breathe123` for Django admin)

## Quick Start (local)

```bash
# Backend
cd backend
pip install -r requirements.txt
python manage.py migrate
python seed_data.py
python manage.py runserver

# Frontend (separate terminal)
cd frontend
npm install
npm start
```

The frontend dev server proxies API calls to `localhost:8000`.

## Architecture

```
breathe-esg/
├── backend/           # Django REST API
│   ├── emissions/     # Core data models (Tenant, IngestionBatch, EmissionRecord, etc.)
│   ├── ingestion/     # Parsers, serializers, views
│   │   ├── parsers.py # SAP / Utility / Travel CSV parsers + normalization
│   │   ├── views.py   # IngestView, EmissionRecordViewSet, DashboardStatsView
│   │   └── serializers.py
│   └── seed_data.py   # Realistic sample data generator
├── frontend/          # React SPA
│   └── src/App.js     # Single-file app: Dashboard, Review Queue, Ingest, History
└── docs/
    ├── MODEL.md        # Data model rationale
    ├── DECISIONS.md    # Every ambiguity resolved
    ├── TRADEOFFS.md    # What was deliberately not built
    └── SOURCES.md      # Research on each data source format
```

## The Three Sources

| Source | Format chosen | Justification |
|--------|--------------|---------------|
| SAP Fuel/Procurement | Semicolon-delimited flat file (MM60/ME2M style) | Most common export mode; IDocs require middleware, OData requires SAP Gateway config most clients lack |
| Utility / Electricity | Portal CSV | Middle ground between PDF (no structure) and API (rarely offered); facilities teams universally use portal CSV export |
| Corporate Travel | Concur/Navan-style CSV | Same format as expense report exports; API access requires OAuth2 setup not feasible for onboarding |

## Credentials for submission review

- `admin / breathe123` — Django admin + full API access
- `analyst / breathe123` — Analyst user (review queue)

## Documentation

See `docs/` for MODEL.md, DECISIONS.md, TRADEOFFS.md, SOURCES.md.
