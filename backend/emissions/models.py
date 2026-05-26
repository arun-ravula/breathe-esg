"""
Data model for Breathe ESG ingestion platform.
See MODEL.md for full rationale.
"""

from django.db import models
from django.contrib.auth.models import User
import uuid


class Tenant(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class IngestionBatch(models.Model):
    SOURCE_SAP = 'sap'
    SOURCE_UTILITY = 'utility'
    SOURCE_TRAVEL = 'travel'
    SOURCE_CHOICES = [
        (SOURCE_SAP, 'SAP Fuel & Procurement'),
        (SOURCE_UTILITY, 'Utility / Electricity'),
        (SOURCE_TRAVEL, 'Corporate Travel'),
    ]

    STATUS_PENDING = 'pending'
    STATUS_PROCESSING = 'processing'
    STATUS_DONE = 'done'
    STATUS_FAILED = 'failed'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_PROCESSING, 'Processing'),
        (STATUS_DONE, 'Done'),
        (STATUS_FAILED, 'Failed'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='batches')
    source_type = models.CharField(max_length=20, choices=SOURCE_CHOICES)
    uploaded_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)
    filename = models.CharField(max_length=500, blank=True)
    file_content = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    error_message = models.TextField(blank=True)
    row_count_total = models.IntegerField(default=0)
    row_count_ok = models.IntegerField(default=0)
    row_count_failed = models.IntegerField(default=0)
    row_count_suspicious = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.tenant} | {self.source_type} | {self.created_at:%Y-%m-%d}"


class EmissionRecord(models.Model):
    SCOPE_CHOICES = [(1, 'Scope 1'), (2, 'Scope 2'), (3, 'Scope 3')]

    CATEGORY_FUEL = 'fuel'
    CATEGORY_PROCUREMENT = 'procurement'
    CATEGORY_ELECTRICITY = 'electricity'
    CATEGORY_FLIGHT = 'flight'
    CATEGORY_HOTEL = 'hotel'
    CATEGORY_GROUND = 'ground_transport'
    CATEGORY_CHOICES = [
        (CATEGORY_FUEL, 'Fuel Combustion'),
        (CATEGORY_PROCUREMENT, 'Procurement'),
        (CATEGORY_ELECTRICITY, 'Electricity'),
        (CATEGORY_FLIGHT, 'Flight'),
        (CATEGORY_HOTEL, 'Hotel Stay'),
        (CATEGORY_GROUND, 'Ground Transport'),
    ]

    REVIEW_PENDING = 'pending'
    REVIEW_APPROVED = 'approved'
    REVIEW_REJECTED = 'rejected'
    REVIEW_SUSPICIOUS = 'suspicious'
    REVIEW_CHOICES = [
        (REVIEW_PENDING, 'Pending Review'),
        (REVIEW_APPROVED, 'Approved'),
        (REVIEW_REJECTED, 'Rejected'),
        (REVIEW_SUSPICIOUS, 'Suspicious'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='records')
    batch = models.ForeignKey(IngestionBatch, on_delete=models.CASCADE, related_name='records')

    scope = models.IntegerField(choices=SCOPE_CHOICES)
    category = models.CharField(max_length=30, choices=CATEGORY_CHOICES)

    activity_date = models.DateField()
    period_end = models.DateField(null=True, blank=True)

    location_ref = models.CharField(max_length=100, blank=True)
    location_label = models.CharField(max_length=255, blank=True)

    raw_quantity = models.DecimalField(max_digits=18, decimal_places=6, null=True, blank=True)
    raw_unit = models.CharField(max_length=50, blank=True)
    raw_fuel_type = models.CharField(max_length=100, blank=True)
    raw_description = models.CharField(max_length=500, blank=True)

    quantity_normalized = models.DecimalField(max_digits=18, decimal_places=6, null=True, blank=True)
    quantity_unit_normalized = models.CharField(max_length=20, blank=True)

    emission_factor = models.DecimalField(max_digits=12, decimal_places=6, null=True, blank=True)
    emission_factor_source = models.CharField(max_length=255, blank=True)
    co2e_kg = models.DecimalField(max_digits=18, decimal_places=3, null=True, blank=True)

    review_status = models.CharField(max_length=20, choices=REVIEW_CHOICES, default=REVIEW_PENDING)
    reviewed_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='reviewed_records')
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_note = models.TextField(blank=True)

    flags = models.JSONField(default=list)

    is_edited = models.BooleanField(default=False)
    edited_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='edited_records')
    edited_at = models.DateTimeField(null=True, blank=True)

    is_locked = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-activity_date', '-created_at']
        indexes = [
            models.Index(fields=['tenant', 'scope']),
            models.Index(fields=['tenant', 'review_status']),
            models.Index(fields=['batch']),
            models.Index(fields=['activity_date']),
        ]

    def __str__(self):
        return f"{self.tenant} | {self.category} | {self.activity_date} | {self.co2e_kg} kg CO2e"


class RawRow(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    batch = models.ForeignKey(IngestionBatch, on_delete=models.CASCADE, related_name='raw_rows')
    record = models.OneToOneField(EmissionRecord, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='raw_row')
    row_index = models.IntegerField()
    raw_data = models.JSONField()
    parse_error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['batch', 'row_index']


class AuditEvent(models.Model):
    ACTION_CHOICES = [
        ('created', 'Created'),
        ('reviewed', 'Reviewed'),
        ('edited', 'Edited'),
        ('locked', 'Locked for Audit'),
        ('flagged', 'Flagged as Suspicious'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    record = models.ForeignKey(EmissionRecord, on_delete=models.CASCADE, related_name='audit_events')
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    actor = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)
    timestamp = models.DateTimeField(auto_now_add=True)
    before_state = models.JSONField(null=True, blank=True)
    after_state = models.JSONField(null=True, blank=True)
    note = models.TextField(blank=True)

    class Meta:
        ordering = ['timestamp']
