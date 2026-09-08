// weekly_menu.ingredients / .full_recipe are stored as JSON string arrays (one
// ingredient / one method step per entry). Older rows may hold a bare string
// ("a, b, c" for ingredients, a "1. ...\n2. ..." blob for a recipe) - fall back to
// splitting those so the UI keeps working through the migration.

const ENUM_PREFIX = /^\s*(?:\d+[.)]|[-*•])\s+/;

export function parseLines(value) {
  if (Array.isArray(value)) return clean(value);
  if (typeof value !== 'string') return [];
  const text = value.trim();
  if (!text) return [];
  try {
    const parsed = JSON.parse(text);
    if (Array.isArray(parsed)) return clean(parsed);
  } catch {
    // not JSON - fall through to legacy split
  }
  const byLine = text.split('\n').map((s) => s.trim()).filter(Boolean);
  return clean(byLine.length > 1 ? byLine : text.split(',').map((s) => s.trim()).filter(Boolean));
}

function clean(items) {
  return items
    .map((item) => String(item).replace(ENUM_PREFIX, '').trim())
    .filter(Boolean);
}

// A short one-line preview for cards where a list would be too tall.
export function previewLine(value, fallback = '') {
  const lines = parseLines(value);
  return lines.length ? lines.join(', ') : fallback;
}

// detailed_prep_schedule.ingredients_used is a JSON array of {item_name, quantity, unit}
// objects (see dbmcp's add_detailed_prep_schedule docstring) - distinct from the plain
// string-line arrays above.
export function parseIngredientsUsed(value) {
  let parsed = value;
  if (typeof value === 'string') {
    const text = value.trim();
    if (!text) return [];
    try { parsed = JSON.parse(text); } catch { return []; }
  }
  if (!Array.isArray(parsed)) return [];
  return parsed
    .filter((item) => item && typeof item === 'object' && item.item_name)
    .map((item) => ({ item_name: String(item.item_name), quantity: item.quantity, unit: item.unit || '' }));
}

export function formatIngredientLine(item) {
  const qty = [item.quantity, item.unit].filter((part) => part !== undefined && part !== null && part !== '').join(' ');
  return qty ? `${item.item_name} (${qty})` : item.item_name;
}

export function formatMenuDate(value) {
  if (!value) return '';
  const parsed = new Date(String(value).replace(' ', 'T'));
  if (Number.isNaN(parsed.getTime())) return '';
  return parsed.toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' });
}
