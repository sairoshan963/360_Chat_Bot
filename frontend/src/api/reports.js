import api from './client';
import { delay, MY_REPORT, HR_DASHBOARD, MANAGER_DASHBOARD, SUMMARY_STATS, AUDIT_LOGS } from '../mocks/data';

const USE_MOCK = import.meta.env.VITE_USE_MOCK === 'true';

export const getMyReport = (cycleId) => {
  if (USE_MOCK) {
    const report = MY_REPORT[cycleId];
    if (!report) return Promise.reject({ response: { data: { detail: 'No report available for this cycle.' } } });
    return delay({ success: true, report });
  }
  return api.get(`/feedback/cycles/${cycleId}/my-report/`);
};

export const getEmployeeReport = (cycleId, employeeId) => {
  if (USE_MOCK) {
    const report = MY_REPORT[cycleId] || MY_REPORT['c-001'];
    return delay({ success: true, report });
  }
  return api.get(`/feedback/cycles/${cycleId}/reports/${employeeId}/`);
};

export const exportEmployeeReport = (cycleId, employeeId) => {
  if (USE_MOCK) return Promise.resolve({ data: new Blob() });
  return api.get(`/feedback/cycles/${cycleId}/reports/${employeeId}/export/`, { responseType: 'blob' });
};

export const exportAllReports = (cycleId) => {
  if (USE_MOCK) return Promise.resolve({ data: new Blob() });
  return api.get(`/feedback/cycles/${cycleId}/reports/export-all/`, { responseType: 'blob' });
};

export const getHrDashboard = (cycleId) => {
  if (USE_MOCK) {
    const dashboard = HR_DASHBOARD[cycleId] || HR_DASHBOARD['c-002'];
    return delay({ success: true, dashboard });
  }
  return api.get(`/dashboard/hr/${cycleId}/`);
};

export const getManagerDashboard = (cycleId) => {
  if (USE_MOCK) {
    const dashboard = MANAGER_DASHBOARD[cycleId] || MANAGER_DASHBOARD['c-002'];
    return delay({ success: true, dashboard });
  }
  return api.get(`/dashboard/manager/${cycleId}/`);
};

export const getOrgHeatmap = () => {
  if (USE_MOCK) return delay({ success: true, heatmap: [] });
  return api.get('/dashboard/org/heatmap/');
};

export const getSummaryStats = () => {
  if (USE_MOCK) return delay({ success: true, stats: SUMMARY_STATS });
  return api.get('/dashboard/summary/');
};

export const getAuditLogs = (params) => {
  if (USE_MOCK) return delay({ success: true, logs: AUDIT_LOGS, total: AUDIT_LOGS.length });
  return api.get('/audit/', { params });
};
