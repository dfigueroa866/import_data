const inactivityMinutes = Number(import.meta.env.VITE_SESSION_INACTIVITY_MINUTES) || 15;

export const SESSION_INACTIVITY_MS = inactivityMinutes * 60 * 1000;
export const SESSION_CHECK_INTERVAL_MS = 30 * 1000;
export const SESSION_ACTIVITY_THROTTLE_MS = 15 * 1000;
