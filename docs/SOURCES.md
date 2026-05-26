# SOURCES — Research Notes on Each Data Source

## 1. SAP Fuel & Procurement

### What I researched

SAP has multiple ways to extract materials movement data. The main candidates:

- **MB51** (Material Document List): Transaction that shows individual goods
  movements. Export via SAP GUI → System → List → Save/Export gives a
  space-padded or tab-delimited flat file. Fields include posting date (`BUDAT`),
  plant (`WERKS`), material (`MATNR`), material description (`MAKTX`), quantity
  (`MENGE`), unit of measure (`MEINS`), amount in local currency (`DMBTR`), and
  movement type (`BWART`).

- **ME2M** (Purchase Orders by Material): Purchase-order-centric view useful
  for procurement data. Similar export format.

- **IDoc (Intermediate Document)**: SAP's native EDI format. IDocs for goods
  movements are of type `MBGMCR` (goods movement create). They are XML-ish
  with hierarchical segments (`E1MSEG` for line items). Used for system-to-
  system integration, not for human-readable exports.

- **OData services**: SAP Gateway exposes OData v2/v4 services for programmatic
  access. `API_MATERIAL_DOCUMENT_SRV` covers material documents. Requires
  configured SAP Gateway and authentication.

I chose the **MB51 flat file** format because:
1. It's what a sustainability coordinator would actually produce when asked to
   "pull fuel data from SAP"
2. It includes movement type, which lets us filter to consumption events
3. It's the format most commonly shared via email or uploaded to a portal
4. German column headers are realistic because many SAP systems run in German
   even in multinational companies

### What the sample data looks like and why

```
Buchungsdatum;Werk;Material;Kurztext;Menge;ME;Betrag;Bewegungsart;Kostenstelle
20240115;1001;10000042;Diesel HSD;5000;L;450000;201;CC1001
```

- **Semicolon delimiter**: SAP's default export uses semicolons (commas conflict
  with European decimal notation)
- **`YYYYMMDD` date format**: SAP's internal date format, no separators
- **German column headers**: Realistic for a German-configured SAP instance
  (`Buchungsdatum` = posting date, `Werk` = plant, `Menge` = quantity, `ME` =
  unit of measure)
- **Plant codes** (`1001`, `1002`): 4-digit numeric, meaningless without a
  lookup table. We store them verbatim in `location_ref`.
- **Movement type 201**: Goods issue to cost center (consumption). 261 would be
  goods issue to production order.
- **`L` (litre) as unit**: SAP uses ISO unit codes. `L` = litre, `KG` = kilogram,
  `M3` = cubic metre, `GAL` = gallon.

Deliberate anomalies in the sample data:
- Row with 99,999 L: triggers outlier flag (>50,000 L)
- Row with "Unknown Fuel Type XYZ": triggers fuel type inference flag
- Row with `KG` unit for CNG: realistic (CNG is often metered by weight)

### What would break in production

1. **Currency in amount field**: The `DMBTR` field is in local currency without
   currency code. If the plant is in a country with multiple currencies, you
   can't interpret the amount without the currency key (`WAERS`), which isn't
   in a standard MB51 export.

2. **Unit conversion for non-standard units**: SAP can be configured with custom
   units of measure (e.g., a manufacturing plant might use `DRM` for drum,
   `CYL` for cylinder). Our lookup table covers ISO units; custom units would
   fall through to the "unknown unit" flag.

3. **Material description quality**: `MAKTX` (short text, 40 chars) is often
   abbreviated or in a local language. "Diesel HSD" is relatively clean;
   "BS6 HSD 50PPM D/E" is more realistic. Our fuel type classifier handles
   common patterns but would fail on novel abbreviations.

4. **Multi-plant company codes**: In a multi-national SAP setup, the same
   material number in plant `1001` (India) and plant `2001` (UK) may refer to
   different products. Without a plant-to-country mapping table, we can't
   correctly apply country-specific emission factors.

5. **GR/GI reconciliation**: A proper Scope 1 calculation should reconcile
   goods receipts (purchases) against goods issues (consumption) to account for
   inventory changes. We only look at goods issues here, which is correct for
   combustion-based Scope 1 but would double-count if someone ingests both GR
   and GI data.

---

## 2. Utility / Electricity

### What I researched

Enterprise electricity accounts in India and the UK have two main digital access
paths:

**Portal CSV (what we chose):** BESCOM (Bangalore), TATA Power, MSEDCL, and
most Indian state utilities offer web portals where account holders can view
and download billing history as CSV. The format varies by utility but typically
includes: account/meter number, billing period start/end, units consumed (kWh),
tariff category, and bill amount. UK utilities (National Grid, Octopus,
British Gas Business) have more standardized formats; Green Button Data (XML/CSV)
is the emerging US standard.

**PDF bill:** The most common format for smaller accounts. Requires OCR or
structured extraction (pdfplumber). Highly variable layout across utilities.

**API:** Rare for Indian utilities. Octopus Energy (UK) has an excellent API.
ERCOT (Texas) has a data API. Not the common case for enterprise accounts in
India.

### What the sample data looks like and why

```
meter_id,site,period_start,period_end,consumption,unit,tariff
MET-001,Plant 1 Main Building,2024-01-01,2024-01-31,145000,kWh,Industrial HT
```

- **Comma delimiter**: Unlike SAP, utility portal exports are usually comma-
  delimited since they don't use European decimal notation
- **ISO date format**: Most modern portals use `YYYY-MM-DD`
- **`period_start` and `period_end`**: Billing periods don't align with
  calendar months; the period boundary depends on when the meter reader visited
- **Consumption in kWh**: Standard unit; some older meters report in "units"
  (1 unit = 1 kWh in India)
- **Tariff category**: Industrial HT (High Tension, >11kV supply), Industrial
  LT (Low Tension), Commercial — affects pricing but not our emission factor
  calculation (we use consumption, not spend)

Deliberate anomalies:
- `MET-006` with -500 kWh: credit note or reversed meter read (triggers flag)
- `MET-007` with 850,000 kWh in 14 days: suspicious volume and unusual period
- `MET-003` with period crossing month boundary (Jan 5 – Feb 4)

### What would break in production

1. **Grid emission factor variation**: India's grid factor varies by state and
   by year. Tamil Nadu's grid (more renewables) is cleaner than UP's (more coal).
   We use a single national average (IEA 2022: 0.7082 kg CO₂e/kWh). A
   production system needs the CERC/CEA state-wise factors.

2. **Market-based vs. location-based accounting**: Clients with Power Purchase
   Agreements (PPAs) or Renewable Energy Certificates (RECs) should use a
   market-based emission factor (potentially 0, if 100% certified RE). The
   portal CSV doesn't know about PPAs; this information would need to come
   from a separate source.

3. **Meter hierarchy**: Large facilities have sub-meters. The portal exports
   individual meter readings; if a main meter and its sub-meters are all in
   the export, consumption would be double-counted. We don't detect this.

4. **Self-generation**: If a client has rooftop solar, their net import from
   the grid is lower than gross consumption. The portal typically shows net
   metered consumption, which is correct for Scope 2. But if they also want to
   account for self-generated renewable electricity (for Scope 2 market-based),
   that needs a separate data source.

5. **Multi-tariff billing periods**: Some industrial tariffs have peak and off-
   peak splits within one billing period. We see aggregate consumption; the
   split is in the bill detail, not the summary export.

---

## 3. Corporate Travel

### What I researched

Concur Travel (SAP subsidiary) is the dominant corporate travel management
platform in India's enterprise segment. Navan (formerly TripActions) is the
fast-growing challenger. Both offer:

- **Report exports**: Travel managers run a date-range report in the UI and
  export as Excel or CSV. Fields vary by report template but commonly include:
  trip ID, traveler name, travel date, segment type (air/hotel/car), origin,
  destination, amount, cost center, booking class.

- **Concur Travel API (v4)**: REST API with OAuth2. Returns trip segments as
  structured JSON. Includes segment type, origin/destination airport codes,
  class of service, amount. Does NOT include calculated distances — that's a
  client-side calculation.

- **Navan API**: Similar scope. Also doesn't return distances.

Key insight from researching the APIs: **distance is not provided by either
platform.** They give you airport codes. Distance calculation is the client's
responsibility. This is why I built the airport code distance lookup table.

### What the sample data looks like and why

```
trip_id,travel_date,type,origin,destination,distance_km,nights,employee,class,cost_center
TRP-001,2024-01-08,Flight,BOM,DEL,,,Rahul Mehta,Economy,CC-SALES
```

- **Airport codes**: IATA 3-letter codes (`BOM` = Mumbai, `DEL` = Delhi,
  `LHR` = London Heathrow). This is how both Concur and Navan export them.
- **`distance_km` often blank**: Because the platform doesn't provide it; we
  estimate from the airport lookup table and flag the estimation.
- **Segment types**: "Flight", "Hotel", "Taxi", "Rail" — one row per segment,
  not per trip. A trip to Delhi has three rows: outbound flight, hotel, return
  flight.
- **Class of service**: "Economy", "Business", "First" — affects radiative
  forcing multiplier (DEFRA 2023).

Deliberate anomalies:
- Several trips with blank `distance_km` (estimated from airport codes)
- `TRP-017` CDG→BOM in First class (high CO₂e, triggers outlier check)
- `TRP-009` and `TRP-018`: taxi legs with only distance, no route

### What would break in production

1. **Airport code ambiguity**: `MXP` could be Milan Malpensa; some smaller
   airports have non-obvious codes. Our lookup table covers ~20 common routes.
   Any route not in the table triggers a flag and uses a 1000km fallback,
   which could be significantly wrong (e.g. Mumbai–Sydney is 10,265 km).

2. **Ground transport categorization**: Concur codes ground transport
   inconsistently. "Car Service" might be a chauffeured car, a rental, or
   a rideshare. Each has a different emission factor. Without structured
   sub-categorization, we default to taxi.

3. **Rail without distance**: We have an emission factor for rail
   (0.0041 kg CO₂e/km) but Concur doesn't give us distance for rail journeys,
   and we don't have a city-pair distance lookup for rail routes. We flag
   these records as needing manual distance entry.

4. **Personal vehicle use**: Some travel reports include mileage claims for
   employees using their personal cars. The emission factor for personal vehicle
   use depends on the car (our factor is for an average car). Concur may export
   this as a reimbursement rather than a travel segment.

5. **International date line / multi-day flights**: A flight BOM→SFO crosses
   time zones and can arrive before it departed (by clock). Our date parser
   takes the departure date as `activity_date`, which is correct for GHG
   reporting but could look odd in the UI.
