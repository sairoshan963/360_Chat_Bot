import api from './client';
import { delay, USERS, DEPARTMENTS, ORG_HIERARCHY } from '../mocks/data';

const USE_MOCK = import.meta.env.VITE_USE_MOCK === 'true';

export const listUsers = (params) => {
  if (USE_MOCK) return delay({ success: true, users: USERS });
  return api.get('/users/', { params });
};

export const getUser = (id) => {
  if (USE_MOCK) {
    const user = USERS.find((u) => u.id === id);
    return delay({ success: true, user: user || USERS[0] });
  }
  return api.get(`/users/${id}/`);
};

export const createUser = (data) => {
  if (USE_MOCK) return delay({ success: true, user: { id: 'u-new', ...data } });
  return api.post('/users/', data);
};

export const updateUser = (id, data) => {
  if (USE_MOCK) {
    const user = USERS.find((u) => u.id === id) || USERS[0];
    return delay({ success: true, user: { ...user, ...data } });
  }
  return api.patch(`/users/${id}/`, data);
};

export const deleteUser = (id) => {
  if (USE_MOCK) return delay({ success: true });
  return api.delete(`/users/${id}/`);
};

export const listDepartments = () => {
  if (USE_MOCK) return delay({ success: true, departments: DEPARTMENTS });
  return api.get('/users/departments/');
};

export const createDepartment = (data) => {
  if (USE_MOCK) return delay({ success: true, department: { id: 'd-new', ...data } });
  return api.post('/users/departments/', data);
};

export const getOrgHierarchy = () => {
  if (USE_MOCK) return delay({ success: true, hierarchy: ORG_HIERARCHY });
  return api.get('/users/org/hierarchy/');
};

export const getOrgHierarchyForUser = (userId) => {
  if (USE_MOCK) {
    const rows = ORG_HIERARCHY.filter((r) => r.employee_id === userId || r.manager_id === userId);
    return delay({ success: true, hierarchy: rows });
  }
  return api.get(`/org/hierarchy/${userId}/`);
};

export const updateManagerRelationship = (userId, data) => {
  if (USE_MOCK) return delay({ success: true });
  return api.post(`/org/hierarchy/${userId}/`, data);
};

export const importOrg = (csvText) => {
  if (USE_MOCK) return delay({ success: true, imported: 13 });
  const form = new FormData();
  form.append('file', new Blob([csvText], { type: 'text/csv' }), 'import.csv');
  return api.post('/users/import/', form, { headers: { 'Content-Type': 'multipart/form-data' } });
};
