import axios from 'axios';

const BASE = process.env.REACT_APP_API_URL || '';

const api = axios.create({ baseURL: BASE });

export const getTenants = () => api.get('/api/tenants/');
export const getStats = (tenantId) => api.get('/api/dashboard/stats/', { params: { tenant_id: tenantId } });
export const getBatches = (tenantId) => api.get('/api/batches/', { params: { tenant: tenantId } });
export const getRecords = (params) => api.get('/api/records/', { params });
export const getRecord = (id) => api.get(`/api/records/${id}/`);
export const approveRecord = (id, note) => api.post(`/api/records/${id}/approve/`, { note });
export const rejectRecord = (id, note) => api.post(`/api/records/${id}/reject/`, { note });
export const flagRecord = (id, reason) => api.post(`/api/records/${id}/flag/`, { reason });
export const ingestFile = (formData) => api.post('/api/ingest/', formData, {
  headers: { 'Content-Type': 'multipart/form-data' }
});
