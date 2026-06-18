import React, { useCallback, useEffect, useState } from 'react';
import { Shield } from 'lucide-react';
import {
  Alert,
  Button,
  Input,
  LoadingSpinner,
  PageHeader,
  Select,
} from '../components/ui';
import { ConfigTabs } from '../components/admin/CatalogConfigEditors';
import {
  assignConnectRole,
  clearConnectRole,
  getLoaderProfile,
  listConnectUsers,
  updateLoaderProfile,
} from '../services/rolesAdminService';
import { CONNECT_ROLE_ADMIN, CONNECT_ROLE_LOADER, PERMISSION_GROUPS } from '../utils/permissions';

const ROLES_TABS = [
  { id: 'users', label: 'Usuarios' },
  { id: 'loader', label: 'Perfil loader' },
];

const ROLE_OPTIONS = [
  { value: 'default', label: 'Loader (por defecto)' },
  { value: CONNECT_ROLE_LOADER, label: 'Loader (explícito)' },
  { value: CONNECT_ROLE_ADMIN, label: 'Admin M8 Connect' },
];

const emptyPermissions = () => ({
  menus: { panel: true, upload: true, batches: true, monitoring: false, config: false },
  upload: { history: true, catalogs: true },
  config: { catalogs_view: false, history_view: false },
});

const PermissionMatrix = ({ permissions, onChange, disabled = false }) => (
  <div className="space-y-6">
    {PERMISSION_GROUPS.map((group) => (
      <div key={group.id} className="rounded-lg border border-slate-200 dark:border-slate-700 p-4">
        <h3 className="text-sm font-semibold text-slate-800 dark:text-slate-100 mb-3">{group.label}</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {group.items.map((item) => (
            <label key={item.key} className="flex items-center gap-2 text-sm text-slate-700 dark:text-slate-300">
              <input
                type="checkbox"
                className="rounded border-slate-300"
                checked={Boolean(permissions?.[group.id]?.[item.key])}
                disabled={disabled}
                onChange={(e) => onChange(group.id, item.key, e.target.checked)}
              />
              {item.label}
            </label>
          ))}
        </div>
      </div>
    ))}
  </div>
);

const RolesAdmin = () => {
  const [tab, setTab] = useState('users');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [search, setSearch] = useState('');
  const [users, setUsers] = useState([]);
  const [roleDrafts, setRoleDrafts] = useState({});
  const [permissions, setPermissions] = useState(emptyPermissions());

  const loadUsers = useCallback(async () => {
    const data = await listConnectUsers(search);
    setUsers(data);
    const drafts = {};
    data.forEach((user) => {
      drafts[user.id] = user.is_default_loader ? 'default' : user.m8_connect_role;
    });
    setRoleDrafts(drafts);
  }, [search]);

  const loadProfile = useCallback(async () => {
    const data = await getLoaderProfile();
    setPermissions({ ...emptyPermissions(), ...data });
  }, []);

  const loadAll = useCallback(async () => {
    try {
      setLoading(true);
      setError('');
      await Promise.all([loadUsers(), loadProfile()]);
    } catch (err) {
      setError(err.response?.data?.detail || 'No se pudo cargar la configuración de roles');
    } finally {
      setLoading(false);
    }
  }, [loadUsers, loadProfile]);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  const handleSaveUserRole = async (userId) => {
    try {
      setSaving(true);
      setError('');
      setSuccess('');
      const draft = roleDrafts[userId];
      if (draft === 'default') {
        await clearConnectRole(userId);
      } else {
        await assignConnectRole(userId, draft);
      }
      setSuccess('Rol actualizado correctamente');
      await loadUsers();
    } catch (err) {
      setError(err.response?.data?.detail || 'No se pudo actualizar el rol');
    } finally {
      setSaving(false);
    }
  };

  const handlePermissionChange = (groupId, key, value) => {
    setPermissions((prev) => ({
      ...prev,
      [groupId]: {
        ...prev[groupId],
        [key]: value,
      },
    }));
  };

  const handleSaveProfile = async () => {
    try {
      setSaving(true);
      setError('');
      setSuccess('');
      await updateLoaderProfile(permissions);
      setSuccess('Perfil loader guardado');
      await loadProfile();
    } catch (err) {
      setError(err.response?.data?.detail || 'No se pudo guardar el perfil loader');
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="flex flex-1 items-center justify-center p-8">
        <LoadingSpinner message="Cargando roles…" />
      </div>
    );
  }

  return (
    <div className="flex flex-1 flex-col gap-5 overflow-y-auto p-8 max-w-6xl mx-auto w-full scrollbar-thin">
      <PageHeader
        icon={Shield}
        title="Roles M8 Connect"
        subtitle="Asigna perfiles de aplicación y define qué puede ver el rol loader"
      />

      {error && <Alert variant="error">{error}</Alert>}
      {success && <Alert variant="success">{success}</Alert>}

      <ConfigTabs tabs={ROLES_TABS} activeTab={tab} onTabChange={setTab} />

      {tab === 'users' && (
        <div className="space-y-4">
          <div className="flex gap-3 items-center">
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Buscar por correo"
              className="max-w-md"
            />
            <Button type="button" variant="secondary" onClick={loadUsers}>
              Buscar
            </Button>
          </div>

          <div className="overflow-x-auto rounded-lg border border-slate-200 dark:border-slate-700">
            <table className="min-w-full text-sm">
              <thead className="bg-slate-50 dark:bg-slate-900/40 text-left">
                <tr>
                  <th className="px-4 py-3 font-medium">Correo</th>
                  <th className="px-4 py-3 font-medium">Organización</th>
                  <th className="px-4 py-3 font-medium">Rol plataforma</th>
                  <th className="px-4 py-3 font-medium">Rol M8 Connect</th>
                  <th className="px-4 py-3 font-medium">Acción</th>
                </tr>
              </thead>
              <tbody>
                {users.map((user) => (
                  <tr key={user.id} className="border-t border-slate-200 dark:border-slate-700">
                    <td className="px-4 py-3">{user.email}</td>
                    <td className="px-4 py-3">{user.organization_name || user.organization_id}</td>
                    <td className="px-4 py-3">{user.platform_role}</td>
                    <td className="px-4 py-3">
                      <Select
                        value={roleDrafts[user.id] || 'default'}
                        onChange={(e) => setRoleDrafts((prev) => ({ ...prev, [user.id]: e.target.value }))}
                      >
                        {ROLE_OPTIONS.map((option) => (
                          <option key={option.value} value={option.value}>
                            {option.label}
                          </option>
                        ))}
                      </Select>
                    </td>
                    <td className="px-4 py-3">
                      <Button
                        type="button"
                        size="sm"
                        disabled={saving}
                        onClick={() => handleSaveUserRole(user.id)}
                      >
                        Guardar
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {tab === 'loader' && (
        <div className="space-y-4">
          <p className="text-sm text-slate-600 dark:text-slate-400">
            Esta configuración aplica a todos los usuarios con rol loader, incluidos los que no tienen asignación explícita.
          </p>
          <PermissionMatrix permissions={permissions} onChange={handlePermissionChange} />
          <div>
            <Button type="button" onClick={handleSaveProfile} disabled={saving}>
              {saving ? 'Guardando…' : 'Guardar perfil loader'}
            </Button>
          </div>
        </div>
      )}
    </div>
  );
};

export default RolesAdmin;
