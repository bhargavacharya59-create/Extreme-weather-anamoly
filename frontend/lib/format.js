// Formatting helpers: Indian digit grouping, lakh/crore, labels, colours.

export function inr(n) {
  if (n == null || Number.isNaN(n)) return '—';
  const neg = n < 0;
  const s = String(Math.round(Math.abs(n)));
  if (s.length <= 3) return (neg ? '-' : '') + s;
  const head = s.slice(0, -3).replace(/\B(?=(\d{2})+(?!\d))/g, ',');
  return (neg ? '-' : '') + head + ',' + s.slice(-3);
}

export function compact(n) {
  if (n == null) return '—';
  if (n >= 1e7) return `${(n / 1e7).toFixed(n >= 1e8 ? 1 : 2)} crore`;
  if (n >= 1e5) return `${(n / 1e5).toFixed(n >= 1e6 ? 1 : 2)} lakh`;
  return inr(n);
}

export function pct(x, digits = 0) {
  return x == null ? '—' : `${(x * 100).toFixed(digits)}%`;
}

export const TYPE_LABEL = {
  heavy_rainfall: 'Extreme rainfall',
  cyclone: 'Cyclonic storm',
  heatwave: 'Heatwave',
  coldwave: 'Cold wave',
  noise: 'Noise',
};

export const KIND_LABEL = {
  school: 'School / college',
  hospital: 'Hospital',
  rescue_team: 'Rescue unit',
  bus: 'Bus',
  car: 'Car',
  truck: 'Truck',
  two_wheeler: 'Two-wheeler',
};

export const ROLE_LABEL = {
  official: 'Officials',
  school: 'Schools & colleges',
  hospital: 'Hospitals',
  rescue: 'Rescue teams',
  citizen: 'Citizens',
  traveller: 'Travellers',
};

// Risk scale: ordinal yellow -> orange -> dark red (validated: monotone lightness,
// adjacent dL >= 0.06). Always shown with a text label, never colour alone.
export const RISK = {
  high: { fill: '#9e1b1b', tint: '#f8e1de', ink: '#7d1414', label: 'High', range: '0–3 km' },
  moderate: { fill: '#dd6b27', tint: '#fbe6d6', ink: '#8a3d05', label: 'Moderate', range: '3–5 km' },
  low: { fill: '#d9a82e', tint: '#f8efcf', ink: '#6b5200', label: 'Lower', range: '5–8 km' },
};
export const SEV_TO_RING = { High: 'high', Moderate: 'moderate', Low: 'low' };

export function hoursLabel(h) {
  if (h == null) return 'Peak impact';
  if (h === 0) return 'Now';
  if (h % 24 === 0) return `+${h / 24} day${h === 24 ? '' : 's'}`;
  return `+${h} h`;
}

export function leadToDate(issueIso, leadH) {
  const d = new Date(new Date(issueIso).getTime() + leadH * 3600 * 1000);
  return d.toLocaleString('en-IN', { weekday: 'short', day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit', hour12: false, timeZone: 'Asia/Kolkata' });
}

export function timeAgo(iso) {
  if (!iso) return '';
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (s < 60) return 'just now';
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
  return new Date(iso).toLocaleDateString('en-IN', { day: '2-digit', month: 'short' });
}

export function directionWord(d) {
  const map = { N: 'north', NNE: 'north-northeast', NE: 'northeast', ENE: 'east-northeast', E: 'east', ESE: 'east-southeast', SE: 'southeast', SSE: 'south-southeast', S: 'south', SSW: 'south-southwest', SW: 'southwest', WSW: 'west-southwest', W: 'west', WNW: 'west-northwest', NW: 'northwest', NNW: 'north-northwest' };
  return map[d] || d;
}

export function countdown(issueIso, leadH) {
  const target = new Date(issueIso).getTime() + leadH * 3600 * 1000;
  const ms = target - Date.now();
  if (ms <= 0) return 'Now';
  const h = Math.floor(ms / 3600000);
  const d = Math.floor(h / 24);
  return d > 0 ? `${d} d ${h % 24} h` : `${h} h ${Math.floor((ms % 3600000) / 60000)} min`;
}
