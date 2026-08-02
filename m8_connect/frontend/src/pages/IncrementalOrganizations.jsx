import React, { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Building2, ArrowLeft, Plus, Trash2 } from 'lucide-react';
import {
  PageHeader,
  Button,
  Card,
  LoadingSpinner,
  Alert,
  FormField,
  Input,
  Select,
  ConfirmDialog,
} from '../components/ui';
import * as incrementalService from '../services/incrementalService';
import { listCatalogDefinitions } from '../services/catalogAdminService';
import { useAuth } from '../context/AuthContext';
import { canEditConfig } from '../utils/permissions';

const emptyOrg = () => ({
  organization_id: '',
  organization_name: '',
  enabled: true,
  source_path: '',
  notification_emails: '',
  default_granularity: 'weekly',
});

const formatApiError = (err, fallback) => {
  const data = err?.response?.data;
  if (!data) return err?.message || fallback;
  if (typeof data.detail === 'string') return data.detail;
  if (Array.isArray(data.detail)) {
    return data.detail.map((e) => e.msg || JSON.stringify(e)).join('; ');
  }
  if (typeof data.message === 'string') return data.message;
  return fallback;
};

const IncrementalOrganizations = () => {
  const { user } = useAuth();
  const canEdit = canEditConfig(user);
  const [orgs, setOrgs] = useState([]);
  const [orgCatalog, setOrgCatalog] = useState([]);
  const [selected, setSelected] = useState(null);
  const [form, setForm] = useState(emptyOrg());
  const [tables, setTables] = useState([]);
  const [catalogs, setCatalogs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [deleteTarget, setDeleteTarget] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [orgList, catList, catalog] = await Promise.all([
        incrementalService.listOrganizations(),
        listCatalogDefinitions().catch(() => []),
        incrementalService.listOrganizationCatalog().catch(() => []),
      ]);
      setOrgs(orgList);
      setCatalogs(catList);
      setOrgCatalog(catalog);
    } catch (err) {
      setError(formatApiError(err, 'Error al cargar organizaciones'));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const selectOrg = async (org) => {
    setSelected(org);
    setForm({
      ...org,
      notification_emails: (org.notification_emails || []).join(', '),
    });
    const t = await incrementalService.getOrgTables(org.organization_id);
    setTables(t);
  };

  const handleNew = () => {
    setSelected(null);
    setForm(emptyOrg());
    setTables([]);
    setError('');
  };

  const handleSave = async () => {
    if (!form.organization_id) {
      setError('Selecciona una organización');
      return;
    }
    const orgId = String(form.organization_id);
    const payload = {
      ...form,
      organization_id: orgId,
      notification_emails: form.notification_emails
        .split(',')
        .map((e) => e.trim())
        .filter(Boolean),
    };
    const isExisting = Boolean(selected) || orgs.some((o) => String(o.organization_id) === orgId);
    try {
      if (isExisting) {
        await incrementalService.updateOrganization(orgId, payload);
      } else {
        try {
          await incrementalService.createOrganization(payload);
        } catch (err) {
          if (err.response?.status !== 409) throw err;
          await incrementalService.updateOrganization(orgId, payload);
        }
      }
      await incrementalService.updateOrgTables(orgId, tables);
      const orgList = await incrementalService.listOrganizations();
      setOrgs(orgList);
      const saved = orgList.find((o) => String(o.organization_id) === orgId);
      if (saved) {
        await selectOrg(saved);
      }
      setError('');
    } catch (err) {
      setError(formatApiError(err, 'Error al guardar'));
    }
  };

  const toggleCatalog = (slug) => {
    const exists = tables.find((t) => t.load_kind === 'catalog' && t.catalog_slug === slug);
    if (exists) {
      setTables(tables.filter((t) => !(t.load_kind === 'catalog' && t.catalog_slug === slug)));
    } else {
      setTables([...tables, { load_kind: 'catalog', catalog_slug: slug, enabled: true }]);
    }
  };

  const toggleHistory = (granularity) => {
    const exists = tables.find((t) => t.load_kind === 'history');
    if (exists && exists.granularity === granularity) {
      setTables(tables.filter((t) => t.load_kind !== 'history'));
    } else {
      setTables([
        ...tables.filter((t) => t.load_kind !== 'history'),
        { load_kind: 'history', catalog_slug: null, enabled: true, granularity },
      ]);
    }
  };

  const configuredOrgIds = new Set(orgs.map((o) => String(o.organization_id)));
  const availableOrgOptions = orgCatalog.filter(
    (o) => !configuredOrgIds.has(String(o.id)) || String(form.organization_id) === String(o.id),
  );

  const handleOrganizationSelect = (organizationId) => {
    const match = orgCatalog.find((o) => String(o.id) === String(organizationId));
    setForm((f) => ({
      ...f,
      organization_id: organizationId,
      organization_name: match?.name || f.organization_name,
      source_path: match?.suggested_source_path || f.source_path || '',
    }));
  };

  if (loading) return <LoadingSpinner label="Cargando…" />;

  return (
    <div className="flex flex-1 flex-col gap-5 overflow-y-auto p-8 scrollbar-thin">
      <PageHeader
        icon={Building2}
        title="Organizaciones incremental"
        subtitle="Rutas de origen y tablas participantes"
        actions={(
          <div className="flex gap-2">
            <Link to="/incremental">
              <Button variant="secondary"><ArrowLeft className="mr-2 h-4 w-4" />Volver</Button>
            </Link>
            {canEdit && (
              <Button onClick={handleNew}><Plus className="mr-2 h-4 w-4" />Nueva</Button>
            )}
          </div>
        )}
      />
      {error && <Alert variant="error">{error}</Alert>}

      <div className="flex gap-6">
        <Card className="w-72 shrink-0 p-3">
          {canEdit && (
            <Button
              type="button"
              variant={!selected ? 'primary' : 'secondary'}
              size="sm"
              className="mb-3 w-full"
              onClick={handleNew}
            >
              <Plus className="mr-2 h-4 w-4" />
              Nueva organización
            </Button>
          )}
          <ul className="space-y-1">
            {orgs.map((org) => (
              <li key={org.organization_id}>
                <button
                  type="button"
                  onClick={() => selectOrg(org)}
                  className={`w-full rounded px-3 py-2 text-left text-sm ${
                    selected?.organization_id === org.organization_id
                      ? 'bg-[#3b82f6]/10 text-[#3b82f6]'
                      : 'hover:bg-[#f1f5f9] dark:hover:bg-[#1e293b]'
                  }`}
                >
                  {org.organization_name}
                </button>
              </li>
            ))}
          </ul>
        </Card>

        <Card className="flex-1 p-6">
          {!selected && !canEdit && orgs.length === 0 ? (
            <p className="text-sm text-[#64748b]">Selecciona una organización</p>
          ) : !selected && availableOrgOptions.length === 0 ? (
            <p className="text-sm text-[#64748b]">
              Todas las organizaciones del catálogo ya tienen perfil incremental configurado.
            </p>
          ) : (
            <div className="space-y-4">
              <FormField label="Organización">
                {selected ? (
                  <Input value={form.organization_name || form.organization_id} readOnly />
                ) : (
                  <Select
                    value={form.organization_id}
                    onChange={(e) => handleOrganizationSelect(e.target.value)}
                    disabled={!canEdit}
                  >
                    <option value="">Selecciona una organización…</option>
                    {availableOrgOptions.map((org) => (
                      <option key={org.id} value={org.id}>
                        {org.name}
                      </option>
                    ))}
                  </Select>
                )}
              </FormField>
              <FormField
                label="Ruta origen"
                hint="Se completa al elegir la organización. Si no existe, se crea al guardar (catalogos/ e historia/)."
              >
                <Input
                  value={form.source_path}
                  onChange={(e) => setForm((f) => ({ ...f, source_path: e.target.value }))}
                  readOnly={!canEdit}
                  placeholder="D:/…/Incremental/NombreOrg"
                />
              </FormField>
              <FormField label="Emails (separados por coma)">
                <Input
                  value={form.notification_emails}
                  onChange={(e) => setForm((f) => ({ ...f, notification_emails: e.target.value }))}
                  readOnly={!canEdit}
                />
              </FormField>
              <FormField label="Granularidad por defecto">
                <Select
                  value={form.default_granularity || 'weekly'}
                  onChange={(e) => setForm((f) => ({ ...f, default_granularity: e.target.value }))}
                  disabled={!canEdit}
                >
                  <option value="weekly">Semanal</option>
                  <option value="monthly">Mensual</option>
                </Select>
              </FormField>

              <div>
                <h4 className="mb-2 font-medium">Catálogos</h4>
                <div className="flex flex-wrap gap-2">
                  {catalogs.map((cat) => {
                    const on = tables.some(
                      (t) => t.load_kind === 'catalog' && t.catalog_slug === cat.name,
                    );
                    return (
                      <Button
                        key={cat.name}
                        type="button"
                        variant={on ? 'primary' : 'secondary'}
                        size="sm"
                        disabled={!canEdit}
                        onClick={() => toggleCatalog(cat.name)}
                      >
                        {cat.label || cat.name}
                      </Button>
                    );
                  })}
                </div>
              </div>

              <div>
                <h4 className="mb-2 font-medium">Historia</h4>
                <div className="flex gap-2">
                  {['weekly', 'monthly'].map((g) => {
                    const on = tables.some((t) => t.load_kind === 'history' && t.granularity === g);
                    return (
                      <Button
                        key={g}
                        type="button"
                        variant={on ? 'primary' : 'secondary'}
                        size="sm"
                        disabled={!canEdit}
                        onClick={() => toggleHistory(g)}
                      >
                        {g === 'weekly' ? 'Semanal' : 'Mensual'}
                      </Button>
                    );
                  })}
                </div>
              </div>

              {canEdit && (
                <div className="flex gap-2 pt-2">
                  <Button onClick={handleSave}>Guardar</Button>
                  {selected && (
                    <Button variant="danger" onClick={() => setDeleteTarget(selected)}>
                      <Trash2 className="mr-2 h-4 w-4" />Eliminar
                    </Button>
                  )}
                </div>
              )}
            </div>
          )}
        </Card>
      </div>

      <ConfirmDialog
        isOpen={!!deleteTarget}
        title="Eliminar perfil"
        message={`¿Eliminar configuración de ${deleteTarget?.organization_name}?`}
        variant="danger"
        onConfirm={async () => {
          await incrementalService.deleteOrganization(deleteTarget.organization_id);
          setDeleteTarget(null);
          handleNew();
          load();
        }}
        onClose={() => setDeleteTarget(null)}
      />
    </div>
  );
};

export default IncrementalOrganizations;
