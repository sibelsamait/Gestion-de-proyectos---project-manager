/** Renderiza un Gantt SVG accesible a partir del endpoint JSON. */
import { escapeText, formatDate, selectedCurrency } from './app.js';

const COLORS = {
  grid: '#E2E8F0', weekend: '#F8FAFC', text: '#0F172A', muted: '#64748B',
  track: '#E0F2FE', bar: '#0284C7', done: '#067647', doneTrack: '#ECFDF3',
  late: '#B42318', lateTrack: '#FEF3F2', milestone: '#0F4C81', today: '#0F4C81'
};
const MONTHS = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic'];
const DAY = 86400000;
const parse = (iso) => new Date(`${iso}T00:00:00`);

function stateOf(task) {
  if (Number(task.progress) >= 100) return 'Completada';
  return task.overdue ? 'Atrasada' : 'En plazo';
}

export async function renderGantt(projectId) {
  const currency = selectedCurrency();
  const response = await fetch(`/api/projects/${encodeURIComponent(projectId)}/gantt?currency=${currency}`, {
    headers: { Accept: 'application/json' }
  });
  if (!response.ok) throw new Error('No fue posible cargar el Gantt.');
  const data = await response.json();
  const container = document.querySelector('#gantt');
  const tableBody = document.querySelector('#gantt-table tbody');
  tableBody.replaceChildren();
  data.tasks.forEach((task) => {
    const row = document.createElement('tr');
    [task.name, formatDate(task.planned_start), formatDate(task.planned_end), `${Number(task.progress).toFixed(0)} %`, stateOf(task)]
      .forEach((value, index) => {
        const cell = document.createElement('td');
        cell.textContent = value;
        if (index > 0) cell.className = index === 3 ? 'num' : 'num nowrap';
        row.append(cell);
      });
    tableBody.append(row);
  });

  const dated = [
    ...data.tasks.flatMap((task) => [task.planned_start, task.planned_end]),
    ...data.milestones.map((milestone) => milestone.date)
  ].filter(Boolean).sort();
  if (!dated.length) {
    container.innerHTML = '<p class="loading">No hay tareas con fechas planificadas. Registre fechas de inicio y término para generar el cronograma.</p>';
    return data;
  }
  const min = parse(dated[0]);
  const max = parse(dated[dated.length - 1]);
  const days = Math.max(1, Math.round((max - min) / DAY) + 1);
  const labelWidth = 220;
  const dayWidth = days > 180 ? 6 : days > 90 ? 10 : days > 45 ? 16 : 24;
  const rows = [...data.tasks.filter((t) => t.planned_start && t.planned_end).map((t) => ({ kind: 'task', item: t })),
    ...data.milestones.filter((m) => m.date).map((m) => ({ kind: 'milestone', item: m }))];
  const rowHeight = 34;
  const header = 36;
  const width = labelWidth + days * dayWidth + 16;
  const height = header + rows.length * rowHeight + 8;
  const x = (iso) => labelWidth + Math.round((parse(iso) - min) / DAY) * dayWidth;
  const svg = [`<svg width="${width}" height="${height}" viewBox="0 0 ${width} ${height}" role="img" ` +
    `aria-label="Gantt con ${rows.length} elementos planificados" font-family="inherit" font-size="12">`];

  // Encabezado mensual y líneas de grilla.
  for (let index = 0; index < days; index += 1) {
    const day = new Date(min.getTime() + index * DAY);
    const left = labelWidth + index * dayWidth;
    if (day.getDay() === 0 || day.getDay() === 6) {
      svg.push(`<rect x="${left}" y="${header}" width="${dayWidth}" height="${height - header}" fill="${COLORS.weekend}"/>`);
    }
    if (day.getDate() === 1 || index === 0) {
      svg.push(`<line x1="${left}" x2="${left}" y1="0" y2="${height}" stroke="${COLORS.grid}"/>`);
      svg.push(`<text x="${left + 6}" y="22" fill="${COLORS.muted}" font-weight="600">${MONTHS[day.getMonth()]} ${day.getFullYear()}</text>`);
    }
  }
  svg.push(`<line x1="0" x2="${width}" y1="${header}" y2="${header}" stroke="${COLORS.grid}"/>`);
  svg.push(`<line x1="${labelWidth}" x2="${labelWidth}" y1="0" y2="${height}" stroke="${COLORS.grid}"/>`);

  rows.forEach(({ kind, item }, index) => {
    const y = header + index * rowHeight;
    const name = escapeText(item.name);
    const short = escapeText(item.name.length > 30 ? `${item.name.slice(0, 29)}…` : item.name);
    svg.push(`<line x1="0" x2="${width}" y1="${y + rowHeight}" y2="${y + rowHeight}" stroke="${COLORS.grid}" stroke-opacity=".6"/>`);
    svg.push(`<text x="4" y="${y + 21}" fill="${kind === 'milestone' ? COLORS.milestone : COLORS.text}">${short}</text>`);
    if (kind === 'task') {
      const left = x(item.planned_start);
      const barWidth = Math.max(dayWidth, x(item.planned_end) - left + dayWidth);
      const progress = Math.max(0, Math.min(100, Number(item.progress)));
      const done = progress >= 100;
      const fill = done ? COLORS.done : item.overdue ? COLORS.late : COLORS.bar;
      const track = done ? COLORS.doneTrack : item.overdue ? COLORS.lateTrack : COLORS.track;
      svg.push(`<g><title>${name} — ${formatDate(item.planned_start)} a ${formatDate(item.planned_end)} — ${progress.toFixed(0)} % — ${stateOf(item)}</title>`);
      svg.push(`<rect x="${left}" y="${y + 9}" width="${barWidth}" height="16" rx="3" fill="${track}" stroke="${fill}" stroke-opacity=".35"/>`);
      svg.push(`<rect x="${left}" y="${y + 9}" width="${Math.round(barWidth * progress / 100)}" height="16" rx="3" fill="${fill}"/>`);
      svg.push('</g>');
    } else {
      const cx = x(item.date) + dayWidth / 2;
      const cy = y + 17;
      svg.push(`<g><title>${name} — ${formatDate(item.date)}</title>`);
      svg.push(`<rect x="${cx - 6}" y="${cy - 6}" width="12" height="12" fill="${COLORS.milestone}" transform="rotate(45 ${cx} ${cy})"/></g>`);
    }
  });

  const today = new Date();
  today.setHours(0, 0, 0, 0);
  if (today >= min && today <= max) {
    const left = labelWidth + Math.round((today - min) / DAY) * dayWidth + dayWidth / 2;
    svg.push(`<line x1="${left}" x2="${left}" y1="${header}" y2="${height}" stroke="${COLORS.today}" stroke-dasharray="3 3"/>`);
    svg.push(`<text x="${left + 4}" y="${header - 4}" fill="${COLORS.today}" font-size="11">Hoy</text>`);
  }
  svg.push('</svg>');
  container.innerHTML = svg.join('');
  return data;
}

const gantt = document.querySelector('#gantt');
const projectId = gantt?.dataset.projectId;
if (projectId) renderGantt(projectId).catch((error) => {
  document.querySelector('#gantt').textContent = error.message;
});
