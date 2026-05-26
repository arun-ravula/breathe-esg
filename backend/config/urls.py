from django.contrib import admin
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from ingestion.views import (
    TenantViewSet, IngestionBatchViewSet, EmissionRecordViewSet,
    IngestView, DashboardStatsView
)

router = DefaultRouter()
router.register(r'tenants', TenantViewSet)
router.register(r'batches', IngestionBatchViewSet)
router.register(r'records', EmissionRecordViewSet)

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include(router.urls)),
    path('api/ingest/', IngestView.as_view()),
    path('api/dashboard/stats/', DashboardStatsView.as_view()),
]

# Serve React SPA for all non-API routes
from django.views.generic import TemplateView
from django.conf import settings
import os

# Serve React index.html for all unmatched routes (SPA routing)
urlpatterns += [
    path('', TemplateView.as_view(template_name='index.html')),
]
