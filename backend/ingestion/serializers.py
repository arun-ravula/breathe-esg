from rest_framework import serializers
from emissions.models import Tenant, IngestionBatch, EmissionRecord, RawRow, AuditEvent


class TenantSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tenant
        fields = '__all__'


class IngestionBatchSerializer(serializers.ModelSerializer):
    tenant_name = serializers.CharField(source='tenant.name', read_only=True)

    class Meta:
        model = IngestionBatch
        fields = [
            'id', 'tenant', 'tenant_name', 'source_type', 'filename',
            'status', 'error_message', 'row_count_total', 'row_count_ok',
            'row_count_failed', 'row_count_suspicious', 'created_at', 'processed_at',
        ]


class EmissionRecordSerializer(serializers.ModelSerializer):
    tenant_name = serializers.CharField(source='tenant.name', read_only=True)
    scope_display = serializers.CharField(source='get_scope_display', read_only=True)
    category_display = serializers.CharField(source='get_category_display', read_only=True)
    review_status_display = serializers.CharField(source='get_review_status_display', read_only=True)

    class Meta:
        model = EmissionRecord
        fields = [
            'id', 'tenant', 'tenant_name', 'batch', 'scope', 'scope_display',
            'category', 'category_display', 'activity_date', 'period_end',
            'location_ref', 'location_label',
            'raw_quantity', 'raw_unit', 'raw_fuel_type', 'raw_description',
            'quantity_normalized', 'quantity_unit_normalized',
            'emission_factor', 'emission_factor_source', 'co2e_kg',
            'review_status', 'review_status_display', 'review_note',
            'flags', 'is_edited', 'is_locked', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'tenant', 'batch', 'created_at', 'updated_at']


class AuditEventSerializer(serializers.ModelSerializer):
    actor_name = serializers.SerializerMethodField()

    class Meta:
        model = AuditEvent
        fields = ['id', 'action', 'actor', 'actor_name', 'timestamp',
                  'before_state', 'after_state', 'note']

    def get_actor_name(self, obj):
        return obj.actor.get_full_name() or obj.actor.username if obj.actor else 'System'


class RawRowSerializer(serializers.ModelSerializer):
    class Meta:
        model = RawRow
        fields = ['id', 'row_index', 'raw_data', 'parse_error', 'created_at']


class EmissionRecordDetailSerializer(EmissionRecordSerializer):
    audit_events = AuditEventSerializer(many=True, read_only=True)
    raw_row = RawRowSerializer(read_only=True)

    class Meta(EmissionRecordSerializer.Meta):
        fields = EmissionRecordSerializer.Meta.fields + ['audit_events', 'raw_row']
