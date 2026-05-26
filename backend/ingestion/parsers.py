"""
Source-specific parsers. Each parser takes raw CSV text and returns a list of
normalized dicts ready for EmissionRecord creation.

Design rationale per source type is in SOURCES.md and DECISIONS.md.
"""

import csv
import io
import re
from datetime import datetime, date
from decimal import Decimal, InvalidOperation
from typing import Optional


# ─── Unit conversion tables ──────────────────────────────────────────────────

# Fuel: all to litres, then use density for kg, then to kWh via NCV
FUEL_TO_LITRE = {
    'L': Decimal('1'), 'l': Decimal('1'),
    'LTR': Decimal('1'), 'LITRE': Decimal('1'), 'LITRES': Decimal('1'),
    'GAL': Decimal('3.78541'),   # US gallon
    'USGAL': Decimal('3.78541'),
    'UKGAL': Decimal('4.54609'),
    'M3': Decimal('1000'),       # cubic metre of liquid
    'KG': None,                  # handled separately for LPG/CNG
}

# Electricity units to kWh
ELEC_TO_KWH = {
    'KWH': Decimal('1'), 'kwh': Decimal('1'),
    'MWH': Decimal('1000'),
    'GWH': Decimal('1000000'),
    'KJ': Decimal('1') / Decimal('3600'),
    'MJ': Decimal('1000') / Decimal('3600'),
    'GJ': Decimal('1000000') / Decimal('3600'),
}

# Distance units to km
DIST_TO_KM = {
    'KM': Decimal('1'), 'km': Decimal('1'),
    'MI': Decimal('1.60934'), 'MILE': Decimal('1.60934'), 'MILES': Decimal('1.60934'),
    'M': Decimal('0.001'),
}

# Emission factors: kg CO2e per unit
# Sources: DEFRA 2023 GHG Conversion Factors, IEA 2022, ICAO Carbon Estimator
EMISSION_FACTORS = {
    # Fuel (kg CO2e per litre)
    'diesel':   {'factor': Decimal('2.6780'), 'unit': 'L', 'source': 'DEFRA 2023'},
    'petrol':   {'factor': Decimal('2.3120'), 'unit': 'L', 'source': 'DEFRA 2023'},
    'hfo':      {'factor': Decimal('3.1140'), 'unit': 'L', 'source': 'DEFRA 2023'},  # heavy fuel oil
    'lpg':      {'factor': Decimal('1.5551'), 'unit': 'L', 'source': 'DEFRA 2023'},
    'cng':      {'factor': Decimal('0.0023'), 'unit': 'L', 'source': 'DEFRA 2023'},  # approx per litre equiv
    'natural_gas': {'factor': Decimal('0.00203'), 'unit': 'kWh', 'source': 'DEFRA 2023'},

    # Electricity (kg CO2e per kWh) — India grid default
    'electricity': {'factor': Decimal('0.7082'), 'unit': 'kWh', 'source': 'IEA 2022 India grid'},
    'electricity_uk': {'factor': Decimal('0.2078'), 'unit': 'kWh', 'source': 'DEFRA 2023 UK grid'},
    'electricity_us': {'factor': Decimal('0.3860'), 'unit': 'kWh', 'source': 'EPA eGRID 2022'},

    # Travel (kg CO2e per km per passenger)
    'flight_short': {'factor': Decimal('0.2553'), 'unit': 'km', 'source': 'DEFRA 2023 avg economy <3700km'},
    'flight_long':  {'factor': Decimal('0.1951'), 'unit': 'km', 'source': 'DEFRA 2023 avg economy >3700km'},
    'hotel':        {'factor': Decimal('18.4'), 'unit': 'night', 'source': 'DEFRA 2023 avg hotel night'},
    'taxi':         {'factor': Decimal('0.1491'), 'unit': 'km', 'source': 'DEFRA 2023 taxi'},
    'car_rental':   {'factor': Decimal('0.1702'), 'unit': 'km', 'source': 'DEFRA 2023 avg car'},
    'rail':         {'factor': Decimal('0.0041'), 'unit': 'km', 'source': 'DEFRA 2023 avg rail'},
}

# Airport-to-airport great circle distances (km) for common routes
# In production this would call a geo API; here we embed the most common
AIRPORT_DISTANCES = {
    frozenset(['BOM', 'DEL']): 1148,
    frozenset(['BOM', 'BLR']): 845,
    frozenset(['DEL', 'BLR']): 1740,
    frozenset(['BOM', 'HYD']): 711,
    frozenset(['DEL', 'HYD']): 1253,
    frozenset(['LHR', 'JFK']): 5540,
    frozenset(['LHR', 'SIN']): 10841,
    frozenset(['JFK', 'SFO']): 4139,
    frozenset(['SIN', 'BOM']): 3916,
    frozenset(['CDG', 'BOM']): 6590,
    frozenset(['LHR', 'BOM']): 7192,
    frozenset(['DXB', 'BOM']): 1929,
    frozenset(['DXB', 'DEL']): 2194,
    frozenset(['DXB', 'LHR']): 5475,
}


def _parse_date(s: str) -> Optional[date]:
    """Try multiple date formats including SAP's YYYYMMDD and European DD.MM.YYYY."""
    if not s or not s.strip():
        return None
    s = s.strip()
    for fmt in ('%Y%m%d', '%Y-%m-%d', '%d.%m.%Y', '%d/%m/%Y', '%m/%d/%Y', '%d-%m-%Y',
                '%Y/%m/%d', '%d %b %Y', '%d %B %Y'):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _parse_decimal(s) -> Optional[Decimal]:
    if s is None:
        return None
    s = str(s).strip().replace(',', '.').replace(' ', '')
    # European format: 1.234,56 → 1234.56
    if re.match(r'^\d{1,3}(\.\d{3})+(,\d+)?$', s):
        s = s.replace('.', '').replace(',', '.')
    try:
        return Decimal(s)
    except InvalidOperation:
        return None


def _normalize_unit(u: str) -> str:
    return u.strip().upper()


def _fuel_type_canonical(raw: str) -> str:
    raw = raw.lower().strip()
    if any(x in raw for x in ['diesel', 'hsd', 'gasoil', 'go ']):
        return 'diesel'
    if any(x in raw for x in ['petrol', 'gasoline', 'unleaded', 'pms']):
        return 'petrol'
    if any(x in raw for x in ['lpg', 'propane', 'butane']):
        return 'lpg'
    if any(x in raw for x in ['cng', 'compressed natural']):
        return 'cng'
    if any(x in raw for x in ['hfo', 'heavy fuel', 'furnace oil', 'fo ']):
        return 'hfo'
    if any(x in raw for x in ['natural gas', 'natgas', 'ng ']):
        return 'natural_gas'
    return 'diesel'  # default assumption; flagged as suspicious


def _litres_to_co2e(litres: Decimal, fuel_type: str) -> tuple[Decimal, str]:
    key = _fuel_type_canonical(fuel_type)
    ef = EMISSION_FACTORS.get(key, EMISSION_FACTORS['diesel'])
    return litres * ef['factor'], ef['source']


def _flag_outlier(value: Decimal, low: Decimal, high: Decimal, label: str) -> Optional[str]:
    if value < low:
        return f"{label} unusually low: {value}"
    if value > high:
        return f"{label} unusually high: {value}"
    return None


# ─── SAP Parser ──────────────────────────────────────────────────────────────

SAP_COL_MAP = {
    # English names
    'posting_date': 'posting_date', 'budat': 'posting_date', 'Buchungsdatum': 'posting_date',
    'plant': 'plant', 'werks': 'plant', 'Werk': 'plant',
    'material': 'material', 'matnr': 'material', 'Material': 'material',
    'material_description': 'description', 'maktx': 'description', 'Kurztext': 'description',
    'quantity': 'quantity', 'menge': 'quantity', 'Menge': 'quantity',
    'unit': 'unit', 'meins': 'unit', 'ME': 'unit',
    'amount': 'amount', 'dmbtr': 'amount', 'Betrag': 'amount',
    'movement_type': 'mvt', 'bwart': 'mvt', 'Bewegungsart': 'mvt',
    'cost_center': 'cost_center', 'kostl': 'cost_center', 'Kostenstelle': 'cost_center',
}

# SAP movement types that indicate fuel/energy consumption (goods issue for consumption)
FUEL_MOVEMENT_TYPES = {'201', '261', '291', '411', '551', '901'}


def parse_sap(csv_text: str) -> list[dict]:
    """
    Parse a SAP MM flat-file export (tab or semicolon delimited).
    We handle the MM60 / ME2M report format which gives material movements.
    German column headers are mapped via SAP_COL_MAP.
    """
    results = []
    # Detect delimiter
    sample = csv_text[:2000]
    delim = '\t' if sample.count('\t') > sample.count(';') else ';'
    if delim == '\t' and sample.count(',') > sample.count('\t') * 2:
        delim = ','

    reader = csv.DictReader(io.StringIO(csv_text), delimiter=delim)

    # Normalize column names
    def normalize_col(col):
        col = col.strip()
        return SAP_COL_MAP.get(col, col.lower().replace(' ', '_').replace('-', '_'))

    for i, raw_row in enumerate(reader):
        row = {normalize_col(k): v.strip() if isinstance(v, str) else v
               for k, v in raw_row.items() if k}

        flags = []
        err = None

        try:
            # Date
            dt = _parse_date(row.get('posting_date', ''))
            if not dt:
                raise ValueError(f"Cannot parse date: {row.get('posting_date')}")

            # Quantity
            qty = _parse_decimal(row.get('quantity', ''))
            if qty is None:
                raise ValueError(f"Cannot parse quantity: {row.get('quantity')}")
            if qty <= 0:
                flags.append("Non-positive quantity")

            raw_unit = _normalize_unit(row.get('unit', 'L'))

            # Convert to litres
            conv = FUEL_TO_LITRE.get(raw_unit)
            if conv is None:
                flags.append(f"Unknown unit '{raw_unit}', assuming litres")
                litres = qty
            else:
                litres = qty * conv

            desc = row.get('description', row.get('material', ''))
            fuel_type_canonical = _fuel_type_canonical(desc)

            # Flag if fuel type couldn't be determined
            if fuel_type_canonical == 'diesel' and 'diesel' not in desc.lower():
                flags.append(f"Fuel type inferred as diesel from '{desc}' — verify")

            co2e, ef_source = _litres_to_co2e(litres, fuel_type_canonical)

            # Outlier checks: <10L or >50,000L per row is suspicious
            flag = _flag_outlier(litres, Decimal('10'), Decimal('50000'), 'Fuel volume (L)')
            if flag:
                flags.append(flag)

            results.append({
                'row_index': i,
                'raw_data': dict(raw_row),
                'parse_error': '',
                'record': {
                    'scope': 1,
                    'category': 'fuel',
                    'activity_date': dt,
                    'location_ref': row.get('plant', row.get('cost_center', '')),
                    'location_label': '',
                    'raw_quantity': float(qty),
                    'raw_unit': raw_unit,
                    'raw_fuel_type': desc,
                    'raw_description': desc,
                    'quantity_normalized': float(litres),
                    'quantity_unit_normalized': 'L',
                    'emission_factor': float(EMISSION_FACTORS[fuel_type_canonical]['factor']),
                    'emission_factor_source': ef_source,
                    'co2e_kg': float(co2e),
                    'flags': flags,
                    'review_status': 'suspicious' if flags else 'pending',
                },
            })
        except Exception as e:
            results.append({
                'row_index': i,
                'raw_data': dict(raw_row),
                'parse_error': str(e),
                'record': None,
            })

    return results


# ─── Utility (Electricity) Parser ────────────────────────────────────────────

UTILITY_COL_MAP = {
    'account_number': 'meter_id', 'meter_id': 'meter_id', 'meter': 'meter_id',
    'account': 'meter_id', 'supply_point': 'meter_id',
    'billing_start': 'period_start', 'period_from': 'period_start', 'from': 'period_start',
    'start_date': 'period_start', 'bill_start_date': 'period_start',
    'billing_end': 'period_end', 'period_to': 'period_end', 'to': 'period_end',
    'end_date': 'period_end', 'bill_end_date': 'period_end',
    'consumption': 'consumption', 'units_consumed': 'consumption', 'usage': 'consumption',
    'kwh': 'consumption', 'energy_consumed': 'consumption',
    'unit': 'unit', 'uom': 'unit',
    'site': 'site', 'facility': 'site', 'location': 'site', 'premises': 'site',
    'tariff': 'tariff', 'rate': 'tariff',
}


def parse_utility(csv_text: str) -> list[dict]:
    """
    Parse a utility portal CSV export.
    Key challenge: billing periods don't align with calendar months.
    We record both period_start and period_end; activity_date = period_start.
    Units can be kWh, MWh, kJ, etc.
    """
    results = []
    sample = csv_text[:2000]
    delim = '\t' if sample.count('\t') > sample.count(',') else ','

    reader = csv.DictReader(io.StringIO(csv_text), delimiter=delim)

    def normalize_col(col):
        col = col.strip().lower().replace(' ', '_').replace('-', '_')
        return UTILITY_COL_MAP.get(col, col)

    for i, raw_row in enumerate(reader):
        row = {normalize_col(k): v.strip() if isinstance(v, str) else v
               for k, v in raw_row.items() if k}

        flags = []
        try:
            period_start = _parse_date(row.get('period_start', ''))
            period_end = _parse_date(row.get('period_end', ''))
            if not period_start:
                raise ValueError(f"Cannot parse period_start: {row.get('period_start')}")

            consumption = _parse_decimal(row.get('consumption', ''))
            if consumption is None:
                raise ValueError(f"Cannot parse consumption: {row.get('consumption')}")
            if consumption < 0:
                flags.append("Negative consumption — credit note or error?")

            raw_unit = _normalize_unit(row.get('unit', 'KWH'))
            conv = ELEC_TO_KWH.get(raw_unit)
            if conv is None:
                flags.append(f"Unknown unit '{raw_unit}', assuming kWh")
                kwh = consumption
            else:
                kwh = consumption * conv

            # Billing period sanity check
            if period_end and period_start:
                days = (period_end - period_start).days
                if days < 20 or days > 95:
                    flags.append(f"Billing period is {days} days — unusual (expected 28–92)")

            # Outlier: >500,000 kWh/month is a large factory; <10 kWh suspicious
            flag = _flag_outlier(kwh, Decimal('10'), Decimal('500000'), 'Electricity (kWh)')
            if flag:
                flags.append(flag)

            ef_info = EMISSION_FACTORS['electricity']
            co2e = kwh * ef_info['factor']

            results.append({
                'row_index': i,
                'raw_data': dict(raw_row),
                'parse_error': '',
                'record': {
                    'scope': 2,
                    'category': 'electricity',
                    'activity_date': period_start,
                    'period_end': period_end,
                    'location_ref': row.get('meter_id', ''),
                    'location_label': row.get('site', ''),
                    'raw_quantity': float(consumption),
                    'raw_unit': raw_unit,
                    'raw_fuel_type': 'electricity',
                    'raw_description': row.get('tariff', ''),
                    'quantity_normalized': float(kwh),
                    'quantity_unit_normalized': 'kWh',
                    'emission_factor': float(ef_info['factor']),
                    'emission_factor_source': ef_info['source'],
                    'co2e_kg': float(co2e),
                    'flags': flags,
                    'review_status': 'suspicious' if flags else 'pending',
                },
            })
        except Exception as e:
            results.append({
                'row_index': i,
                'raw_data': dict(raw_row),
                'parse_error': str(e),
                'record': None,
            })

    return results


# ─── Travel Parser ────────────────────────────────────────────────────────────

TRAVEL_COL_MAP = {
    'trip_id': 'trip_id', 'booking_id': 'trip_id', 'record_locator': 'trip_id',
    'travel_date': 'travel_date', 'departure_date': 'travel_date', 'check_in_date': 'travel_date',
    'date': 'travel_date',
    'type': 'travel_type', 'segment_type': 'travel_type', 'service_type': 'travel_type',
    'category': 'travel_type', 'mode': 'travel_type',
    'origin': 'origin', 'from': 'origin', 'departure': 'origin',
    'origin_airport': 'origin', 'departure_airport': 'origin',
    'destination': 'destination', 'to': 'destination', 'arrival': 'destination',
    'destination_airport': 'destination', 'arrival_airport': 'destination',
    'distance_km': 'distance_km', 'distance': 'distance_km',
    'nights': 'nights', 'duration_nights': 'nights', 'hotel_nights': 'nights',
    'employee': 'employee', 'traveler': 'employee', 'traveller': 'employee',
    'class': 'cabin_class', 'cabin_class': 'cabin_class', 'service_class': 'cabin_class',
    'cost_center': 'cost_center',
    'hotel': 'hotel_name', 'hotel_name': 'hotel_name', 'property': 'hotel_name',
}


def _travel_type_canonical(raw: str) -> str:
    raw = raw.lower().strip()
    if any(x in raw for x in ['flight', 'air', 'plane', 'aviation']):
        return 'flight'
    if any(x in raw for x in ['hotel', 'accommodation', 'lodging', 'stay']):
        return 'hotel'
    if any(x in raw for x in ['taxi', 'cab', 'uber', 'ola', 'rideshare', 'car hire', 'rental']):
        return 'taxi'
    if any(x in raw for x in ['rail', 'train', 'metro', 'subway']):
        return 'rail'
    if any(x in raw for x in ['bus', 'coach']):
        return 'rail'  # approx similar EF
    return 'taxi'  # default


def _airport_distance(origin: str, dest: str) -> Optional[Decimal]:
    key = frozenset([origin.upper().strip(), dest.upper().strip()])
    d = AIRPORT_DISTANCES.get(key)
    return Decimal(str(d)) if d else None


def parse_travel(csv_text: str) -> list[dict]:
    """
    Parse a corporate travel export (Concur/Navan-style).
    Key challenges:
    - Distance may not be provided; we derive from airport codes for flights
    - Multiple segment types in same file (flights, hotels, ground)
    - Cabin class affects emission factor for flights
    """
    results = []
    sample = csv_text[:2000]
    delim = '\t' if sample.count('\t') > sample.count(',') else ','

    reader = csv.DictReader(io.StringIO(csv_text), delimiter=delim)

    def normalize_col(col):
        col = col.strip().lower().replace(' ', '_').replace('-', '_').replace('/', '_')
        return TRAVEL_COL_MAP.get(col, col)

    for i, raw_row in enumerate(reader):
        row = {normalize_col(k): v.strip() if isinstance(v, str) else v
               for k, v in raw_row.items() if k}

        flags = []
        try:
            travel_date = _parse_date(row.get('travel_date', ''))
            if not travel_date:
                raise ValueError(f"Cannot parse date: {row.get('travel_date')}")

            raw_type = row.get('travel_type', 'flight')
            ttype = _travel_type_canonical(raw_type)

            category_map = {
                'flight': 'flight', 'hotel': 'hotel',
                'taxi': 'ground_transport', 'rail': 'ground_transport',
            }
            category = category_map[ttype]

            origin = row.get('origin', '').upper().strip()
            destination = row.get('destination', '').upper().strip()

            if ttype == 'hotel':
                nights = _parse_decimal(row.get('nights', '1')) or Decimal('1')
                ef_info = EMISSION_FACTORS['hotel']
                co2e = nights * ef_info['factor']
                results.append({
                    'row_index': i,
                    'raw_data': dict(raw_row),
                    'parse_error': '',
                    'record': {
                        'scope': 3,
                        'category': 'hotel',
                        'activity_date': travel_date,
                        'location_ref': row.get('cost_center', ''),
                        'location_label': row.get('hotel_name', destination),
                        'raw_quantity': float(nights),
                        'raw_unit': 'nights',
                        'raw_fuel_type': 'hotel',
                        'raw_description': raw_type,
                        'quantity_normalized': float(nights),
                        'quantity_unit_normalized': 'nights',
                        'emission_factor': float(ef_info['factor']),
                        'emission_factor_source': ef_info['source'],
                        'co2e_kg': float(co2e),
                        'flags': flags,
                        'review_status': 'pending',
                    },
                })
                continue

            # Flights and ground: need distance
            dist_km = _parse_decimal(row.get('distance_km', ''))
            if dist_km is None and ttype == 'flight' and origin and destination:
                dist_km = _airport_distance(origin, destination)
                if dist_km:
                    flags.append(f"Distance estimated from airport codes {origin}→{destination}: {dist_km} km")
                else:
                    flags.append(f"No distance data and airport pair {origin}→{destination} not in lookup table")
                    dist_km = Decimal('1000')  # rough fallback

            if dist_km is None:
                dist_km = Decimal('0')
                flags.append("Distance missing, assumed 0 — verify")

            # Flight emission factor: short (<3700km) vs long haul
            if ttype == 'flight':
                ef_key = 'flight_long' if dist_km > 3700 else 'flight_short'
                # Cabin class multiplier
                cabin = row.get('cabin_class', 'economy').lower()
                cabin_mult = Decimal('2.0') if 'business' in cabin else (
                    Decimal('2.9') if 'first' in cabin else Decimal('1.0')
                )
                ef_info = EMISSION_FACTORS[ef_key]
                co2e = dist_km * ef_info['factor'] * cabin_mult
            else:
                ef_key = ttype  # taxi or rail
                ef_info = EMISSION_FACTORS.get(ef_key, EMISSION_FACTORS['taxi'])
                cabin_mult = Decimal('1')
                co2e = dist_km * ef_info['factor']

            flag = _flag_outlier(dist_km, Decimal('1'), Decimal('20000'), f"{ttype} distance (km)")
            if flag:
                flags.append(flag)

            results.append({
                'row_index': i,
                'raw_data': dict(raw_row),
                'parse_error': '',
                'record': {
                    'scope': 3,
                    'category': category,
                    'activity_date': travel_date,
                    'location_ref': row.get('cost_center', ''),
                    'location_label': f"{origin}→{destination}" if origin else destination,
                    'raw_quantity': float(dist_km),
                    'raw_unit': 'km',
                    'raw_fuel_type': ttype,
                    'raw_description': f"{raw_type} {origin}→{destination}".strip(),
                    'quantity_normalized': float(dist_km),
                    'quantity_unit_normalized': 'km',
                    'emission_factor': float(ef_info['factor']),
                    'emission_factor_source': ef_info['source'],
                    'co2e_kg': float(co2e),
                    'flags': flags,
                    'review_status': 'suspicious' if flags else 'pending',
                },
            })
        except Exception as e:
            results.append({
                'row_index': i,
                'raw_data': dict(raw_row),
                'parse_error': str(e),
                'record': None,
            })

    return results
