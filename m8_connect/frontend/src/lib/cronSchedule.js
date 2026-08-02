/** Día de la semana en expresión cron (0 = domingo). */
export const CRON_WEEKDAYS = [
  { value: 0, label: 'Domingo' },
  { value: 1, label: 'Lunes' },
  { value: 2, label: 'Martes' },
  { value: 3, label: 'Miércoles' },
  { value: 4, label: 'Jueves' },
  { value: 5, label: 'Viernes' },
  { value: 6, label: 'Sábado' },
];

const DEFAULT_DAY = 0;
const DEFAULT_TIME = '22:00';

/** Parsea cron semanal: `minuto hora * * día_semana`. */
export function parseWeeklyCron(cronExpression) {
  const parts = String(cronExpression || '').trim().split(/\s+/);
  if (parts.length < 5 || parts[2] !== '*' || parts[3] !== '*') {
    return { dayOfWeek: DEFAULT_DAY, time: DEFAULT_TIME, valid: false };
  }

  const minute = Number.parseInt(parts[0], 10);
  const hour = Number.parseInt(parts[1], 10);
  const dayOfWeek = Number.parseInt(parts[4], 10);

  if (
    Number.isNaN(minute) || minute < 0 || minute > 59
    || Number.isNaN(hour) || hour < 0 || hour > 23
    || Number.isNaN(dayOfWeek) || dayOfWeek < 0 || dayOfWeek > 6
  ) {
    return { dayOfWeek: DEFAULT_DAY, time: DEFAULT_TIME, valid: false };
  }

  return {
    dayOfWeek,
    time: `${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')}`,
    valid: true,
  };
}

/** Construye cron semanal a partir de día y hora `HH:MM`. */
export function buildWeeklyCron(dayOfWeek, time) {
  const [hourPart, minutePart] = String(time || DEFAULT_TIME).split(':');
  const hour = Number.parseInt(hourPart, 10);
  const minute = Number.parseInt(minutePart, 10);
  const safeHour = Number.isNaN(hour) ? 22 : Math.min(23, Math.max(0, hour));
  const safeMinute = Number.isNaN(minute) ? 0 : Math.min(59, Math.max(0, minute));
  const safeDay = Number.isNaN(Number(dayOfWeek)) ? DEFAULT_DAY : dayOfWeek;
  return `${safeMinute} ${safeHour} * * ${safeDay}`;
}

export function weekdayLabel(dayOfWeek) {
  return CRON_WEEKDAYS.find((d) => d.value === dayOfWeek)?.label || '—';
}

/** Texto legible para UI: "Domingos a las 22:00". */
export function formatWeeklySchedule(dayOfWeek, time, timezone) {
  const day = weekdayLabel(dayOfWeek);
  const pluralDay = dayOfWeek === 0 || dayOfWeek === 6 ? `${day}s` : `${day}`;
  const base = `Cada ${pluralDay.toLowerCase()} a las ${time}`;
  return timezone ? `${base} (${timezone})` : base;
}

/** A partir de una expresión cron semanal. */
export function describeWeeklyCron(cronExpression, timezone) {
  const { dayOfWeek, time } = parseWeeklyCron(cronExpression);
  return formatWeeklySchedule(dayOfWeek, time, timezone);
}
