"""
Seed realistic sample data for the Breathe ESG demo.
Run with: python manage.py shell < seed_data.py
"""
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.contrib.auth.models import User
from emissions.models import Tenant, IngestionBatch, EmissionRecord, RawRow, AuditEvent
from ingestion.parsers import parse_sap, parse_utility, parse_travel
from django.utils import timezone

# Create superuser
if not User.objects.filter(username='admin').exists():
    User.objects.create_superuser('admin', 'admin@breatheesg.com', 'breathe123')
    print("Created admin user: admin / breathe123")

analyst = User.objects.filter(username='analyst').first()
if not analyst:
    analyst = User.objects.create_user('analyst', 'analyst@breatheesg.com', 'breathe123', 
                                        first_name='Priya', last_name='Sharma')
    print("Created analyst user: analyst / breathe123")

# Create tenants
tenant1, _ = Tenant.objects.get_or_create(
    slug='acme-india',
    defaults={'name': 'Acme Manufacturing India Pvt. Ltd.'}
)
tenant2, _ = Tenant.objects.get_or_create(
    slug='globex-logistics',
    defaults={'name': 'Globex Logistics Solutions'}
)
print(f"Tenants: {tenant1.name}, {tenant2.name}")

# ─── SAP Fuel Data ────────────────────────────────────────────────────────────
SAP_CSV = """Buchungsdatum;Werk;Material;Kurztext;Menge;ME;Betrag;Bewegungsart;Kostenstelle
20240115;1001;10000042;Diesel HSD;5000;L;450000;201;CC1001
20240118;1001;10000042;Diesel HSD;3200;L;288000;201;CC1001
20240122;1002;10000043;Petrol Unleaded;800;L;88000;201;CC1002
20240201;1001;10000042;Diesel HSD;6100;L;549000;201;CC1001
20240205;1003;10000044;LPG (Liquefied Petroleum);2000;L;140000;201;CC1003
20240210;1001;10000042;Diesel HSD;4800;L;432000;201;CC1001
20240215;1002;10000043;Petrol Unleaded;1200;L;132000;201;CC1002
20240220;1001;10000045;HFO Heavy Fuel Oil;8000;L;640000;201;CC1001
20240225;1004;10000046;CNG Compressed Natural Gas;500;KG;35000;201;CC1004
20240301;1001;10000042;Diesel HSD;5500;L;495000;201;CC1001
20240305;1001;10000042;Diesel HSD;99999;L;8999910;201;CC1001
20240310;1003;10000047;Unknown Fuel Type XYZ;300;L;27000;201;CC1003
20240315;1002;10000043;Petrol Unleaded;950;L;104500;201;CC1002
20240320;1001;10000042;Diesel HSD;4200;L;378000;201;CC1001
20240325;1004;10000044;LPG (Liquefied Petroleum);1800;L;126000;201;CC1004
"""

# ─── Utility / Electricity Data ──────────────────────────────────────────────
UTILITY_CSV = """meter_id,site,period_start,period_end,consumption,unit,tariff
MET-001,Plant 1 Main Building,2024-01-01,2024-01-31,145000,kWh,Industrial HT
MET-002,Plant 1 Warehouse,2024-01-01,2024-01-31,38000,kWh,Industrial LT
MET-003,Plant 2 Factory,2024-01-05,2024-02-04,210000,kWh,Industrial HT
MET-001,Plant 1 Main Building,2024-02-01,2024-02-29,132000,kWh,Industrial HT
MET-002,Plant 1 Warehouse,2024-02-01,2024-02-29,41000,kWh,Industrial LT
MET-004,Admin Office,2024-01-15,2024-02-14,8500,kWh,Commercial
MET-003,Plant 2 Factory,2024-02-05,2024-03-06,198000,kWh,Industrial HT
MET-005,Canteen,2024-01-01,2024-01-31,2200,kWh,Commercial
MET-006,Cold Storage,2024-01-01,2024-01-31,-500,kWh,Industrial LT
MET-001,Plant 1 Main Building,2024-03-01,2024-03-31,158000,kWh,Industrial HT
MET-007,New Annex,2024-02-20,2024-03-05,850000,kWh,Industrial HT
MET-002,Plant 1 Warehouse,2024-03-01,2024-03-31,39500,kWh,Industrial LT
"""

# ─── Corporate Travel Data ───────────────────────────────────────────────────
TRAVEL_CSV = """trip_id,travel_date,type,origin,destination,distance_km,nights,employee,class,cost_center,hotel_name
TRP-001,2024-01-08,Flight,BOM,DEL,,,,Economy,CC-SALES,
TRP-002,2024-01-08,Hotel,,DEL,,2,Rahul Mehta,,,Taj Palace Delhi
TRP-003,2024-01-10,Flight,DEL,BOM,,,Rahul Mehta,Economy,CC-SALES,
TRP-004,2024-01-15,Flight,BOM,LHR,,,,Business,CC-EXEC,
TRP-005,2024-01-15,Hotel,,LHR,,3,Saurav Patel,,,Holiday Inn Heathrow
TRP-006,2024-01-18,Flight,LHR,BOM,,,Saurav Patel,Business,CC-EXEC,
TRP-007,2024-02-01,Flight,DEL,SIN,,,,Economy,CC-OPS,
TRP-008,2024-02-03,Flight,SIN,DEL,,,Anita Nair,Economy,CC-OPS,
TRP-009,2024-02-10,Taxi,,,45,,Vijay Kumar,,CC-SALES,
TRP-010,2024-02-15,Flight,BOM,HYD,,,,Economy,CC-HR,
TRP-011,2024-02-16,Hotel,,HYD,,1,Deepa Iyer,,,Marriott Hyderabad
TRP-012,2024-02-16,Flight,HYD,BOM,,,Deepa Iyer,Economy,CC-HR,
TRP-013,2024-03-01,Flight,BOM,JFK,,,,Economy,CC-EXEC,
TRP-014,2024-03-01,Hotel,,JFK,,4,Rohit Sharma,,,Hyatt Regency JFK
TRP-015,2024-03-05,Flight,JFK,BOM,,,Rohit Sharma,Economy,CC-EXEC,
TRP-016,2024-03-10,Rail,BOM,PNQ,200,,Meena Joshi,,CC-OPS,
TRP-017,2024-03-15,Flight,BOM,CDG,,,,First,CC-EXEC,
TRP-018,2024-03-20,Taxi,,,12,,Arun Das,,CC-SALES,
"""

admin_user = User.objects.get(username='admin')

def ingest(tenant, source_type, csv_text, filename, parse_fn):
    batch = IngestionBatch.objects.create(
        tenant=tenant,
        source_type=source_type,
        uploaded_by=admin_user,
        filename=filename,
        file_content=csv_text,
        status='processing',
    )
    parsed = parse_fn(csv_text)
    ok = fail = susp = 0
    for row in parsed:
        if row['record'] is None:
            RawRow.objects.create(batch=batch, row_index=row['row_index'],
                                   raw_data=row['raw_data'], parse_error=row['parse_error'])
            fail += 1
        else:
            rd = row['record']
            rec = EmissionRecord.objects.create(
                tenant=tenant, batch=batch,
                scope=rd['scope'], category=rd['category'],
                activity_date=rd['activity_date'], period_end=rd.get('period_end'),
                location_ref=rd.get('location_ref',''), location_label=rd.get('location_label',''),
                raw_quantity=rd.get('raw_quantity'), raw_unit=rd.get('raw_unit',''),
                raw_fuel_type=rd.get('raw_fuel_type',''), raw_description=rd.get('raw_description',''),
                quantity_normalized=rd.get('quantity_normalized'),
                quantity_unit_normalized=rd.get('quantity_unit_normalized',''),
                emission_factor=rd.get('emission_factor'),
                emission_factor_source=rd.get('emission_factor_source',''),
                co2e_kg=rd.get('co2e_kg'), review_status=rd.get('review_status','pending'),
                flags=rd.get('flags',[]),
            )
            RawRow.objects.create(batch=batch, row_index=row['row_index'],
                                   raw_data=row['raw_data'], record=rec)
            AuditEvent.objects.create(record=rec, action='created', actor=admin_user,
                after_state={'review_status': rec.review_status})
            if rec.review_status == 'suspicious':
                susp += 1
            else:
                ok += 1
    batch.status = 'done'
    batch.row_count_total = len(parsed)
    batch.row_count_ok = ok
    batch.row_count_failed = fail
    batch.row_count_suspicious = susp
    batch.processed_at = timezone.now()
    batch.save()
    print(f"  {filename}: {ok} ok, {fail} failed, {susp} suspicious")
    return batch

print("Seeding Acme Manufacturing data...")
ingest(tenant1, 'sap', SAP_CSV, 'acme_sap_fuel_q1_2024.csv', parse_sap)
ingest(tenant1, 'utility', UTILITY_CSV, 'acme_electricity_q1_2024.csv', parse_utility)
ingest(tenant1, 'travel', TRAVEL_CSV, 'acme_travel_q1_2024.csv', parse_travel)

# Approve a few records for demo
from emissions.models import EmissionRecord
pending = EmissionRecord.objects.filter(tenant=tenant1, review_status='pending')[:5]
for rec in pending:
    rec.review_status = 'approved'
    rec.reviewed_by = analyst
    rec.reviewed_at = timezone.now()
    rec.save()
    AuditEvent.objects.create(record=rec, action='reviewed', actor=analyst,
        before_state={'review_status': 'pending'},
        after_state={'review_status': 'approved'}, note='Verified against invoice')

print("Seed complete!")
print(f"Total records: {EmissionRecord.objects.count()}")
print(f"Total batches: {IngestionBatch.objects.count()}")
