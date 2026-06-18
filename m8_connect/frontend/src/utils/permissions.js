export const CONNECT_ROLE_ADMIN = 'admin_m8_connect';
export const CONNECT_ROLE_LOADER = 'loader';

export const DEFAULT_PERMISSIONS = {
  menus: {
    panel: true,
    upload: true,
    batches: true,
    monitoring: false,
    config: false,
  },
  upload: {
    history: true,
    catalogs: true,
  },
  config: {
    catalogs_view: false,
    history_view: false,
    roles: false,
  },
};

export const hasPermission = (permissions, key) => {
  if (!key) return false;
  const parts = key.split('.');
  let node = permissions || {};
  for (const part of parts) {
    if (!node || typeof node !== 'object' || !(part in node)) return false;
    node = node[part];
  }
  return Boolean(node);
};

export const isConnectAdmin = (user) => user?.m8_connect_role === CONNECT_ROLE_ADMIN;

export const canAccessMenu = (user, menuKey) => {
  if (isConnectAdmin(user)) return true;
  return hasPermission(user?.permissions, `menus.${menuKey}`);
};

export const canUploadType = (user, type) => {
  if (isConnectAdmin(user)) return true;
  const key = type === 'catalogs' || type === 'catalog' ? 'upload.catalogs' : 'upload.history';
  return hasPermission(user?.permissions, key);
};

export const canViewConfig = (user, section) => {
  if (isConnectAdmin(user)) return true;
  return hasPermission(user?.permissions, `config.${section}_view`);
};

export const canEditConfig = (user) => isConnectAdmin(user);

export const PERMISSION_GROUPS = [
  {
    id: 'menus',
    label: 'Menús',
    items: [
      { key: 'panel', label: 'Panel' },
      { key: 'upload', label: 'Cargas' },
      { key: 'batches', label: 'Lotes' },
      { key: 'monitoring', label: 'Monitoreo' },
      { key: 'config', label: 'Configuración' },
    ],
  },
  {
    id: 'upload',
    label: 'Tipos de carga',
    items: [
      { key: 'history', label: 'Historia' },
      { key: 'catalogs', label: 'Catálogos' },
    ],
  },
  {
    id: 'config',
    label: 'Configuración visible para loader',
    items: [
      { key: 'catalogs_view', label: 'Ver catálogos (solo lectura)' },
      { key: 'history_view', label: 'Ver historia (solo lectura)' },
    ],
  },
];
