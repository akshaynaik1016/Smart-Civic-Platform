import axios from 'axios';
import type {
  Complaint, ComplaintFilters, Officer, User, PaginatedResponse,
  DashboardStats, CategoryCount, MonthlyTrend, WardSummary,
  HeatmapPoint, SeverityDistribution, OfficerPerformance,
} from '../types';

export const apiClient = axios.create({
  baseURL:         import.meta.env.VITE_API_URL ?? 'http://localhost:8000/api/v1',
  timeout:         30_000,
  headers:         { 'Content-Type': 'application/json' },
  withCredentials: false,
});
// Attach JWT token to every request

// ─── Helpers ──────────────────────────────────────────────────────────────────

const toQS = (params: Record<string, any>) => {
  const q = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== '') q.set(k, String(v));
  });
  return q;
};

// ─── Complaints ───────────────────────────────────────────────────────────────

export const complaintApi = {
  list: (filters: ComplaintFilters = {}) =>
    apiClient.get<PaginatedResponse<Complaint>>('/complaints', { params: toQS(filters as any) }),

  get: (id: string) =>
    apiClient.get<Complaint>(`/complaints/${id}`),

  updateStatus: (id: string, status: string, notes?: string, officerId?: string) =>
    apiClient.patch(`/complaints/${id}/status`, { status, notes, officerId }),

  assign: (id: string, officerId: string) =>
    apiClient.patch(`/complaints/${id}/assign`, { officerId }),

  delete: (id: string) =>
    apiClient.delete(`/complaints/${id}`),

  bulkAssign: (complaintIds: string[], officerId: string) =>
    apiClient.post('/complaints/bulk-assign', { complaintIds, officerId }),

  exportCsv: (filters: ComplaintFilters) =>
    apiClient.get('/complaints/export/csv', { params: toQS(filters as any), responseType: 'blob' }),
};

// ─── Officers ─────────────────────────────────────────────────────────────────

export const officerApi = {
  list: (params?: { page?: number; search?: string; available?: boolean }) =>
    apiClient.get<PaginatedResponse<Officer>>('/officers', { params }),

  get: (id: string) =>
    apiClient.get<Officer>(`/officers/${id}`),

  create: (payload: Partial<Officer> & { password: string }) =>
    apiClient.post<Officer>('/officers', payload),

  update: (id: string, payload: Partial<Officer>) =>
    apiClient.put<Officer>(`/officers/${id}`, payload),

  delete: (id: string) =>
    apiClient.delete(`/officers/${id}`),

  getWorkload: (id: string) =>
    apiClient.get(`/officers/${id}/workload`),

  performance: (params?: { from?: string; to?: string }) =>
    apiClient.get<OfficerPerformance[]>('/officers/analytics/performance', { params }),
};

// ─── Users ────────────────────────────────────────────────────────────────────

export const userApi = {
  list: (params?: { role?: string; status?: string; page?: number; search?: string }) =>
    apiClient.get<PaginatedResponse<User>>('/users', { params }),

  get: (id: string) =>
    apiClient.get<User>(`/users/${id}`),

  updateStatus: (id: string, status: string) =>
    apiClient.patch(`/users/${id}/status`, { status }),

  delete: (id: string) =>
    apiClient.delete(`/users/${id}`),
};

// ─── Analytics ────────────────────────────────────────────────────────────────

export const analyticsApi = {
  dashboard: () =>
    apiClient.get<DashboardStats>('/analytics/dashboard'),

  categoryCounts: () =>
    apiClient.get<CategoryCount[]>('/analytics/categories'),

  monthlyTrend: (months = 12) =>
    apiClient.get<MonthlyTrend[]>('/analytics/trend', {
      params: { months },
    }),
  wardSummary: () =>
    apiClient.get<WardSummary[]>('/analytics/wards'),

  heatmap: (zoom = 12) =>
    apiClient.get<HeatmapPoint[]>('/analytics/heatmap', { params: { zoom } }),

  severityDistribution: () =>
    apiClient.get<SeverityDistribution[]>('/analytics/severity'),

  resolutionRate: (from?: string, to?: string) =>
    apiClient.get('/analytics/resolution-rate', { params: { from, to } }),
};

// ─── Reports ──────────────────────────────────────────────────────────────────

export const reportApi = {
  list: (page = 1) =>
    apiClient.get('/reports', { params: { page } }),

  generate: (payload: {
    type: string; title: string; parameters: Record<string, any>; format: string;
  }) => apiClient.post('/reports', payload),

  get: (id: string) =>
    apiClient.get(`/reports/${id}`),

  download: (id: string) =>
    apiClient.get(`/reports/${id}/download`, { responseType: 'blob' }),

  delete: (id: string) =>
    apiClient.delete(`/reports/${id}`),
};
