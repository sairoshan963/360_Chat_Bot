/**
 * Maps numeric rating values (1–5) to descriptive labels.
 * Used on feedback forms and report pages.
 */
export const RATING_LABELS = {
  1: 'Rarely',
  2: 'Sometimes',
  3: 'Often',
  4: 'Usually',
  5: 'Always',
};

/**
 * Returns the label for a given rating value.
 * Falls back to the raw value if not found.
 */
export function getRatingLabel(value) {
  return RATING_LABELS[value] ?? String(value);
}

/**
 * Returns a formatted string like "4 – Usually"
 */
export function formatRating(value) {
  if (value == null) return '—';
  const label = RATING_LABELS[Math.round(value)];
  return label ? `${value} – ${label}` : String(value);
}
