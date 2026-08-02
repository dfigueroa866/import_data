import React, { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Calendar, ArrowLeft } from 'lucide-react';
import {
  PageHeader,
  Button,
  Card,
  LoadingSpinner,
  Alert,
  FormField,
  Input,
  Select,
} from '../components/ui';
import * as incrementalService from '../services/incrementalService';
import {
  buildWeeklyCron,
  CRON_WEEKDAYS,
  describeWeeklyCron,
  formatWeeklySchedule,
  parseWeeklyCron,
} from '../lib/cronSchedule';
import { useAuth } from '../context/AuthContext';
import { canEditConfig } from '../utils/permissions';

const IncrementalSchedule = () => {
  const { user } = useAuth();
  const canEdit = canEditConfig(user);
  const [form, setForm] = useState({
    enabled: true,
    cron_expression: '0 22 * * 0',
    timezone: 'America/Mexico_City',
    retention_years: 3,
  });
  const [scheduleDay, setScheduleDay] = useState(0);
  const [scheduleTime, setScheduleTime] = useState('22:00');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await incrementalService.getSchedule();
      const parsed = parseWeeklyCron(data.cron_expression);
      setScheduleDay(parsed.dayOfWeek);
      setScheduleTime(parsed.time);
      setForm({
        enabled: data.enabled,
        cron_expression: data.cron_expression,
        timezone: data.timezone,
        retention_years: data.retention_years,
      });
    } catch (err) {
      setError(err.response?.data?.detail || 'Error al cargar programación');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const updateScheduleTiming = (dayOfWeek, time) => {
    setScheduleDay(dayOfWeek);
    setScheduleTime(time);
    setForm((f) => ({
      ...f,
      cron_expression: buildWeeklyCron(dayOfWeek, time),
    }));
  };

  const handleSave = async (e) => {
    e.preventDefault();
    if (!canEdit) return;
    setSaving(true);
    setError('');
    setSuccess('');
    try {
      await incrementalService.updateSchedule({
        ...form,
        retention_years: Number(form.retention_years),
      });
      setSuccess('Programación guardada');
    } catch (err) {
      setError(err.response?.data?.detail || 'Error al guardar');
    } finally {
      setSaving(false);
    }
  };

  if (loading) return <LoadingSpinner label="Cargando…" />;

  return (
    <div className="flex flex-1 flex-col gap-5 overflow-y-auto p-8 scrollbar-thin">
      <PageHeader
        icon={Calendar}
        title="Programación incremental"
        subtitle="Elige el día y la hora de ejecución semanal"
        actions={(
          <Link to="/incremental">
            <Button variant="secondary"><ArrowLeft className="mr-2 h-4 w-4" />Volver</Button>
          </Link>
        )}
      />
      {error && <Alert variant="error">{error}</Alert>}
      {success && <Alert variant="success">{success}</Alert>}
      <Card className="max-w-xl p-6">
        <form onSubmit={handleSave} className="space-y-4">
          <FormField label="Activa">
            <Select
              value={form.enabled ? 'true' : 'false'}
              onChange={(e) => setForm((f) => ({ ...f, enabled: e.target.value === 'true' }))}
              disabled={!canEdit}
            >
              <option value="true">Sí</option>
              <option value="false">No</option>
            </Select>
          </FormField>
          <FormField
            label="Día de la semana"
            hint={formatWeeklySchedule(scheduleDay, scheduleTime, form.timezone)}
          >
            <Select
              value={scheduleDay}
              onChange={(e) => updateScheduleTiming(Number(e.target.value), scheduleTime)}
              disabled={!canEdit}
            >
              {CRON_WEEKDAYS.map((day) => (
                <option key={day.value} value={day.value}>
                  {day.label}
                </option>
              ))}
            </Select>
          </FormField>
          <FormField label="Hora de ejecución">
            <Input
              type="time"
              value={scheduleTime}
              onChange={(e) => updateScheduleTiming(scheduleDay, e.target.value)}
              readOnly={!canEdit}
            />
          </FormField>
          <FormField label="Zona horaria">
            <Input
              value={form.timezone}
              onChange={(e) => setForm((f) => ({ ...f, timezone: e.target.value }))}
              readOnly={!canEdit}
            />
          </FormField>
          <FormField label="Años de retención">
            <Input
              type="number"
              min={1}
              max={50}
              value={form.retention_years}
              onChange={(e) => setForm((f) => ({ ...f, retention_years: e.target.value }))}
              readOnly={!canEdit}
            />
          </FormField>
          {canEdit && (
            <Button type="submit" disabled={saving}>
              {saving ? 'Guardando…' : 'Guardar'}
            </Button>
          )}
        </form>
      </Card>
    </div>
  );
};

export default IncrementalSchedule;
