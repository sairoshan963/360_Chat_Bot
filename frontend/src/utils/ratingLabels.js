/**
 * Standard 1–5 scale labels for rating questions.
 */
export const RATING_LABELS = ['Rarely', 'Sometimes', 'Often', 'Mostly', 'Always'];

export function isStandardFivePointScale(min, max) {
  return (min || 1) === 1 && (max || 5) === 5;
}

/** @returns {string|null} Label for integer 1–5, else null */
export function getStandardRatingLabel(value) {
  const n = Number(value);
  if (!Number.isInteger(n) || n < 1 || n > 5) return null;
  return RATING_LABELS[n - 1];
}

/** Marks object for Ant Design Slider (1–5 + labels) */
export function getStandardRatingSliderMarks() {
  return {
    1: RATING_LABELS[0],
    2: RATING_LABELS[1],
    3: RATING_LABELS[2],
    4: RATING_LABELS[3],
    5: RATING_LABELS[4],
  };
}

/** Table / summary: "Often (3)" or plain number for non-standard values */
export function formatRatingTableCell(value) {
  if (value == null || value === '') return null;
  const n = Number(value);
  if (!Number.isFinite(n)) return String(value);
  if (Number.isInteger(n) && n >= 1 && n <= 5) {
    return `${RATING_LABELS[n - 1]} (${n})`;
  }
  return Number.isInteger(n) ? String(n) : n.toFixed(2);
}
