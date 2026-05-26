from django.utils import timezone
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from django_filters.rest_framework import DjangoFilterBackend
from emissions.models import Tenant, IngestionBatch, EmissionRecord, RawRow, AuditEvent
from .parsers import parse_sap, parse_utility, parse_travel
from .serializers import (
    TenantSerializer, IngestionBatchSerializer,
    EmissionRecordSerializer, EmissionRecordDetailSerializer,
    AuditEventSerializer, RawRowSerializer
)


class TenantViewSet(viewsets.ModelViewSet):
    queryset = Tenant.objects.all()
    serializer_class = TenantSerializer


class IngestionBatchViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = IngestionBatch.objects.select_related('tenant', 'uploaded_by').all()
    serializer_class = IngestionBatchSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['tenant', 'source_type', 'status']


class IngestView(APIView):
    """
    POST /api/ingest/
    Accepts multipart/form-data with:
      - file: the CSV file
      - source_type: sap | utility | travel
      - tenant_id: UUID
    """
    PARSERS = {
        'sap': parse_sap,
        'utility': parse_utility,
        'travel': parse_travel,
    }

    def post(self, request):
        source_type = request.data.get('source_type')
        tenant_id = request.data.get('tenant_id')
        uploaded_file = request.FILES.get('file')

        if not source_type or source_type not in self.PARSERS:
            return Response({'error': f'source_type must be one of: {list(self.PARSERS)}'}, 400)
        if not tenant_id:
            return Response({'error': 'tenant_id required'}, 400)
        if not uploaded_file:
            return Response({'error': 'file required'}, 400)

        try:
            tenant = Tenant.objects.get(id=tenant_id)
        except Tenant.DoesNotExist:
            return Response({'error': 'Tenant not found'}, 404)

        csv_text = uploaded_file.read().decode('utf-8-sig', errors='replace')

        batch = IngestionBatch.objects.create(
            tenant=tenant,
            source_type=source_type,
            uploaded_by=request.user if request.user.is_authenticated else None,
            filename=uploaded_file.name,
            file_content=csv_text[:100000],  # store up to 100KB
            status=IngestionBatch.STATUS_PROCESSING,
        )

        try:
            parse_fn = self.PARSERS[source_type]
            parsed_rows = parse_fn(csv_text)
        except Exception as e:
            batch.status = IngestionBatch.STATUS_FAILED
            batch.error_message = str(e)
            batch.save()
            return Response({'error': f'Parse error: {e}'}, 500)

        ok_count = 0
        fail_count = 0
        suspicious_count = 0

        for row in parsed_rows:
            if row['record'] is None:
                # Failed to parse
                RawRow.objects.create(
                    batch=batch,
                    row_index=row['row_index'],
                    raw_data=row['raw_data'],
                    parse_error=row['parse_error'],
                )
                fail_count += 1
            else:
                rec_data = row['record']
                rec = EmissionRecord.objects.create(
                    tenant=tenant,
                    batch=batch,
                    scope=rec_data['scope'],
                    category=rec_data['category'],
                    activity_date=rec_data['activity_date'],
                    period_end=rec_data.get('period_end'),
                    location_ref=rec_data.get('location_ref', ''),
                    location_label=rec_data.get('location_label', ''),
                    raw_quantity=rec_data.get('raw_quantity'),
                    raw_unit=rec_data.get('raw_unit', ''),
                    raw_fuel_type=rec_data.get('raw_fuel_type', ''),
                    raw_description=rec_data.get('raw_description', ''),
                    quantity_normalized=rec_data.get('quantity_normalized'),
                    quantity_unit_normalized=rec_data.get('quantity_unit_normalized', ''),
                    emission_factor=rec_data.get('emission_factor'),
                    emission_factor_source=rec_data.get('emission_factor_source', ''),
                    co2e_kg=rec_data.get('co2e_kg'),
                    review_status=rec_data.get('review_status', 'pending'),
                    flags=rec_data.get('flags', []),
                )
                RawRow.objects.create(
                    batch=batch,
                    row_index=row['row_index'],
                    raw_data=row['raw_data'],
                    record=rec,
                )
                AuditEvent.objects.create(
                    record=rec,
                    action='created',
                    actor=request.user if request.user.is_authenticated else None,
                    after_state={'review_status': rec.review_status, 'co2e_kg': str(rec.co2e_kg)},
                )
                if rec.review_status == 'suspicious':
                    suspicious_count += 1
                else:
                    ok_count += 1

        batch.status = IngestionBatch.STATUS_DONE
        batch.row_count_total = len(parsed_rows)
        batch.row_count_ok = ok_count
        batch.row_count_failed = fail_count
        batch.row_count_suspicious = suspicious_count
        batch.processed_at = timezone.now()
        batch.save()

        return Response({
            'batch_id': str(batch.id),
            'rows_total': len(parsed_rows),
            'rows_ok': ok_count,
            'rows_failed': fail_count,
            'rows_suspicious': suspicious_count,
        }, status=201)


class EmissionRecordViewSet(viewsets.ModelViewSet):
    queryset = EmissionRecord.objects.select_related(
        'tenant', 'batch', 'reviewed_by', 'edited_by'
    ).prefetch_related('audit_events').all()
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['tenant', 'scope', 'category', 'review_status', 'batch', 'is_locked']

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return EmissionRecordDetailSerializer
        return EmissionRecordSerializer

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        rec = self.get_object()
        if rec.is_locked:
            return Response({'error': 'Record is locked for audit'}, 400)
        before = {'review_status': rec.review_status}
        rec.review_status = EmissionRecord.REVIEW_APPROVED
        rec.reviewed_by = request.user if request.user.is_authenticated else None
        rec.reviewed_at = timezone.now()
        rec.review_note = request.data.get('note', '')
        rec.save()
        AuditEvent.objects.create(
            record=rec, action='reviewed',
            actor=request.user if request.user.is_authenticated else None,
            before_state=before,
            after_state={'review_status': rec.review_status},
            note=rec.review_note,
        )
        return Response(EmissionRecordSerializer(rec).data)

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        rec = self.get_object()
        if rec.is_locked:
            return Response({'error': 'Record is locked for audit'}, 400)
        before = {'review_status': rec.review_status}
        rec.review_status = EmissionRecord.REVIEW_REJECTED
        rec.reviewed_by = request.user if request.user.is_authenticated else None
        rec.reviewed_at = timezone.now()
        rec.review_note = request.data.get('note', '')
        rec.save()
        AuditEvent.objects.create(
            record=rec, action='reviewed',
            actor=request.user if request.user.is_authenticated else None,
            before_state=before,
            after_state={'review_status': rec.review_status},
            note=rec.review_note,
        )
        return Response(EmissionRecordSerializer(rec).data)

    @action(detail=True, methods=['post'])
    def flag(self, request, pk=None):
        rec = self.get_object()
        reason = request.data.get('reason', 'Manually flagged')
        if reason not in rec.flags:
            rec.flags = rec.flags + [reason]
        rec.review_status = EmissionRecord.REVIEW_SUSPICIOUS
        rec.save()
        AuditEvent.objects.create(
            record=rec, action='flagged',
            actor=request.user if request.user.is_authenticated else None,
            note=reason,
        )
        return Response(EmissionRecordSerializer(rec).data)


class DashboardStatsView(APIView):
    """Summary stats for the analyst dashboard."""

    def get(self, request):
        tenant_id = request.query_params.get('tenant_id')
        qs = EmissionRecord.objects.all()
        if tenant_id:
            qs = qs.filter(tenant_id=tenant_id)

        from django.db.models import Sum, Count
        stats = qs.aggregate(
            total_co2e=Sum('co2e_kg'),
            total_records=Count('id'),
        )
        by_scope = list(qs.values('scope').annotate(
            co2e=Sum('co2e_kg'), count=Count('id')
        ).order_by('scope'))
        by_status = list(qs.values('review_status').annotate(
            count=Count('id')
        ))
        by_category = list(qs.values('category').annotate(
            co2e=Sum('co2e_kg'), count=Count('id')
        ).order_by('-co2e'))
        batches = IngestionBatch.objects.all()
        if tenant_id:
            batches = batches.filter(tenant_id=tenant_id)

        return Response({
            'total_co2e_kg': stats['total_co2e'] or 0,
            'total_records': stats['total_records'],
            'by_scope': by_scope,
            'by_status': by_status,
            'by_category': by_category,
            'batch_count': batches.count(),
        })
