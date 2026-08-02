import api from './api';

export const getSchedule = async () => {
  const { data } = await api.get('/api/v1/incremental/schedule');
  return data;
};

export const listOrganizationCatalog = async () => {
  const { data } = await api.get('/api/v1/incremental/organization-catalog');
  return data;
};

export const updateSchedule = async (payload) => {
  const { data } = await api.put('/api/v1/incremental/schedule', payload);
  return data;
};

export const listOrganizations = async () => {
  const { data } = await api.get('/api/v1/incremental/organizations');
  return data;
};

export const createOrganization = async (payload) => {
  const { data } = await api.post('/api/v1/incremental/organizations', payload);
  return data;
};

export const updateOrganization = async (organizationId, payload) => {
  const { data } = await api.put(`/api/v1/incremental/organizations/${organizationId}`, payload);
  return data;
};

export const deleteOrganization = async (organizationId) => {
  const { data } = await api.delete(`/api/v1/incremental/organizations/${organizationId}`);
  return data;
};

export const getOrgTables = async (organizationId) => {
  const { data } = await api.get(`/api/v1/incremental/organizations/${organizationId}/tables`);
  return data;
};

export const updateOrgTables = async (organizationId, tables) => {
  const { data } = await api.put(`/api/v1/incremental/organizations/${organizationId}/tables`, tables);
  return data;
};

export const listRuns = async (params = {}) => {
  const { data } = await api.get('/api/v1/incremental/runs', { params });
  return data;
};

export const getRun = async (runId) => {
  const { data } = await api.get(`/api/v1/incremental/runs/${runId}`);
  return data;
};

export const triggerRun = async (organizationId = null) => {
  const { data } = await api.post('/api/v1/incremental/runs/trigger', {
    organization_id: organizationId,
  });
  return data;
};

export const deleteRuns = async (runIds) => {
  const { data } = await api.post('/api/v1/incremental/runs/delete', {
    run_ids: runIds,
  });
  return data;
};

export const downloadRunRejected = async (runId) => {
  const response = await api.get(`/api/v1/incremental/runs/${runId}/rejected/download`, {
    responseType: 'blob',
  });
  return response.data;
};
