import api from './client';
import {
  delay, CYCLES, TEMPLATES, CYCLE_PARTICIPANTS, CYCLE_PROGRESS, MY_NOMINATIONS, ALL_NOMINATIONS,
} from '../mocks/data';

const USE_MOCK = import.meta.env.VITE_USE_MOCK === 'true';

// ─── Templates ───────────────────────────────────────────────────────────────

export const listTemplates = () => {
  if (USE_MOCK) return delay({ success: true, templates: TEMPLATES });
  return api.get('/cycles/templates/');
};

export const getTemplate = (id) => {
  if (USE_MOCK) {
    const t = TEMPLATES.find((x) => x.id === id);
    return delay({ success: true, template: t || TEMPLATES[0] });
  }
  return api.get(`/cycles/templates/${id}/`);
};

export const createTemplate = (data) => {
  if (USE_MOCK) return delay({ success: true, template: { id: 't-new', ...data } });
  return api.post('/cycles/templates/', data);
};

export const updateTemplate = (id, data) => {
  if (USE_MOCK) {
    const t = TEMPLATES.find((x) => x.id === id) || TEMPLATES[0];
    return delay({ success: true, template: { ...t, ...data } });
  }
  return api.put(`/cycles/templates/${id}/`, data);
};

// ─── Cycles ───────────────────────────────────────────────────────────────────

export const getMyCycles = () => {
  if (USE_MOCK) {
    const active = CYCLES.filter((c) => ['NOMINATION', 'ACTIVE', 'RESULTS_RELEASED'].includes(c.state));
    return delay({ success: true, cycles: active });
  }
  return api.get('/cycles/mine/');
};

export const listCycles = (params) => {
  if (USE_MOCK) return delay({ success: true, cycles: CYCLES });
  return api.get('/cycles/', { params });
};

export const getCycle = (id) => {
  if (USE_MOCK) {
    const c = CYCLES.find((x) => x.id === id);
    return delay({ success: true, cycle: c || CYCLES[0] });
  }
  return api.get(`/cycles/${id}/`);
};

export const createCycle = (data) => {
  if (USE_MOCK) return delay({ success: true, cycle: { id: 'c-new', ...data } });
  return api.post('/cycles/', data);
};

export const updateCycle = (id, data) => {
  if (USE_MOCK) {
    const c = CYCLES.find((x) => x.id === id) || CYCLES[0];
    return delay({ success: true, cycle: { ...c, ...data } });
  }
  return api.put(`/cycles/${id}/`, data);
};

// ─── Participants ─────────────────────────────────────────────────────────────

export const addParticipants = (id, participant_ids) => {
  if (USE_MOCK) return delay({ success: true });
  return api.post(`/cycles/${id}/participants/`, { participant_ids });
};

export const removeParticipant = (id, user_id) => {
  if (USE_MOCK) return delay({ success: true });
  return api.delete(`/cycles/${id}/participants/`, { data: { user_id } });
};

export const getParticipants = (id) => {
  if (USE_MOCK) {
    const participants = CYCLE_PARTICIPANTS[id] || [];
    return delay({ success: true, participants });
  }
  return api.get(`/cycles/${id}/participants/`);
};

// ─── State Transitions ────────────────────────────────────────────────────────

export const activateCycle = (id) => {
  if (USE_MOCK) return delay({ success: true, state: 'ACTIVE' });
  return api.post(`/cycles/${id}/activate/`);
};

export const finalizeCycle = (id) => {
  if (USE_MOCK) return delay({ success: true, state: 'CLOSED' });
  return api.post(`/cycles/${id}/finalize/`);
};

export const closeCycle = (id) => {
  if (USE_MOCK) return delay({ success: true, state: 'CLOSED' });
  return api.post(`/cycles/${id}/close/`);
};

export const releaseCycle = (id) => {
  if (USE_MOCK) return delay({ success: true, state: 'RESULTS_RELEASED' });
  return api.post(`/cycles/${id}/release-results/`);
};

export const archiveCycle = (id) => {
  if (USE_MOCK) return delay({ success: true, state: 'ARCHIVED' });
  return api.post(`/cycles/${id}/archive/`);
};

export const overrideCycle = (id, data) => {
  if (USE_MOCK) return delay({ success: true });
  return api.post(`/cycles/${id}/override/`, data);
};

// ─── Progress ─────────────────────────────────────────────────────────────────

export const getCycleProgress = (id) => {
  if (USE_MOCK) {
    const progress = CYCLE_PROGRESS[id] || [];
    return delay({ success: true, progress });
  }
  return api.get(`/cycles/${id}/progress/`);
};

export const getParticipantStatus = (id) => {
  if (USE_MOCK) {
    const participants = (CYCLE_PARTICIPANTS[id] || []).map((u) => ({
      user_id: u.id, first_name: u.first_name, last_name: u.last_name,
      email: u.email, tasks_total: 3, tasks_submitted: 1,
    }));
    return delay({ success: true, participants });
  }
  return api.get(`/cycles/${id}/task-status/`);
};

export const getNominationStatus = (id) => {
  if (USE_MOCK) return delay({ success: true, nominations: MY_NOMINATIONS });
  return api.get(`/cycles/${id}/nomination-status/`);
};

export const downloadNominationExcel = (id) => {
  if (USE_MOCK) return Promise.resolve({ data: new Blob() });
  return api.get(`/cycles/${id}/nomination-download/`, { responseType: 'blob' });
};

export const downloadParticipantExcel = (id, type) => {
  if (USE_MOCK) return Promise.resolve({ data: new Blob() });
  return api.get(`/cycles/${id}/participant-download/`, { params: { type }, responseType: 'blob' });
};

// ─── Nominations ──────────────────────────────────────────────────────────────

export const getMyNominations = (cycleId) => {
  if (USE_MOCK) return delay({ success: true, nominations: MY_NOMINATIONS });
  return api.get(`/tasks/cycles/${cycleId}/nominations/`);
};

export const getAllNominations = (cycleId) => {
  if (USE_MOCK) {
    const noms = ALL_NOMINATIONS.filter((n) => n.cycle_id === cycleId || cycleId === 'c-003');
    return delay({ success: true, nominations: noms });
  }
  return api.get(`/tasks/cycles/${cycleId}/nominations/all/`);
};

export const submitNominations = (cycleId, peer_ids) => {
  if (USE_MOCK) return delay({ success: true, message: 'Nominations submitted.' });
  return api.post(`/tasks/cycles/${cycleId}/nominations/`, { peer_ids });
};

export const overrideNominations = (cycleId, revieweeId, peer_ids) => {
  if (USE_MOCK) return delay({ success: true });
  return api.put(`/tasks/cycles/${cycleId}/nominations/`, { peer_ids });
};

export const getPendingApprovals = (cycleId) => {
  if (USE_MOCK) {
    const pending = ALL_NOMINATIONS.filter((n) => n.status === 'PENDING');
    return delay({ success: true, nominations: pending });
  }
  return api.get(`/tasks/cycles/${cycleId}/nominations/pending/`);
};

export const approveNomination = (cycleId, nominationId) => {
  if (USE_MOCK) return delay({ success: true, status: 'APPROVED' });
  return api.patch(`/tasks/nominations/${nominationId}/decide/`, { status: 'APPROVED' });
};

export const rejectNomination = (cycleId, nominationId, note = '') => {
  if (USE_MOCK) return delay({ success: true, status: 'REJECTED' });
  return api.patch(`/tasks/nominations/${nominationId}/decide/`, { status: 'REJECTED', rejection_note: note });
};
