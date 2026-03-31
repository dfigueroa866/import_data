import api from './api';

const BASE = '/api/v1/environments';

export const environmentsService = {
    list: () => api.get(BASE).then(r => r.data),
    create: (profile) => api.post(BASE, profile).then(r => r.data),
    update: (id, profile) => api.put(`${BASE}/${id}`, profile).then(r => r.data),
    delete: (id) => api.delete(`${BASE}/${id}`).then(r => r.data),
    activate: (id) => api.post(`${BASE}/${id}/activate`).then(r => r.data),
    test: (id) => api.post(`${BASE}/${id}/test`).then(r => r.data),
    getActive: () => api.get(`${BASE}/active`).then(r => r.data),
};
