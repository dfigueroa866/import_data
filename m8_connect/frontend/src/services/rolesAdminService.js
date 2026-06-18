import api from './api';

export const listConnectUsers = async (search = '') => {
  const params = search ? { search } : {};
  const { data } = await api.get('/api/v1/roles/users', { params });
  return data.users || [];
};

export const assignConnectRole = async (userId, role) => {
  const { data } = await api.put(`/api/v1/roles/users/${userId}`, { role });
  return data;
};

export const clearConnectRole = async (userId) => {
  const { data } = await api.delete(`/api/v1/roles/users/${userId}`);
  return data;
};

export const getLoaderProfile = async () => {
  const { data } = await api.get('/api/v1/roles/loader-profile');
  return data.permissions;
};

export const updateLoaderProfile = async (permissions) => {
  const { data } = await api.put('/api/v1/roles/loader-profile', { permissions });
  return data.permissions;
};

export const getMyConnectProfile = async () => {
  const { data } = await api.get('/api/v1/roles/me');
  return data;
};
