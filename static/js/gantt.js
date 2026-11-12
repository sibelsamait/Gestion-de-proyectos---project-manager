/** Renderiza un Gantt SVG accesible a partir del endpoint JSON. */
import { selectedCurrency } from './app.js';
const escapeText = (value) => String(value ?? '').replace(/[&<>"']/g, (char) => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;'
}[char]));

export async function renderGantt(projectId) {
  const currency = selectedCurrency();
  const scale = document.querySelector('#gantt-scale')?.value || 'day';
  const response = await fetch(`/api/projects/${encodeURIComponent(projectId)}/gantt?currency=${currency}&scale=${scale}`, {
    headers: { Accept: 'application/json' }
  });
  if (!response.ok) throw new Error('No fue posible cargar el Gantt.');
  const data = await response.json();
  const container = document.querySelector('#gantt');
  const tableBody = document.querySelector('#gantt-table tbody');
  tableBody.replaceChildren();
  data.tasks.forEach((task) => {
    const row = document.createElement('tr');
    row.innerHTML = `<td>${escapeText(task.name)}</td><td>${escapeText(task.planned_start)}</td>` +
      `<td>${escapeText(task.planned_end)}</td><td>${escapeText(task.progress)}%</td>` +
      `<td>${task.overdue ? '⚠ Atrasada' : 'En plazo'}</td>`;
    tableBody.append(row);
  });
  data.milestones.forEach((milestone) => {
    const row = document.createElement('tr');
    row.innerHTML = `<td>${escapeText(milestone.name)} (hito)</td><td>${escapeText(milestone.date)}</td>` +
      `<td>${escapeText(milestone.date)}</td><td>—</td><td>${escapeText(milestone.status)}</td>`;
    tableBody.append(row);
  });
  const dated = [
    ...data.tasks.flatMap((task) => [task.planned_start, task.planned_end].filter(Boolean)),
    ...data.milestones.map((milestone) => milestone.date).filter(Boolean)
  ];
  if (!dated.length) {
    container.textContent = 'No hay fechas planificadas para dibujar.';
    return data;
  }
  const min = new Date(`${dated.sort()[0]}T00:00:00`);
  const max = new Date(`${dated[dated.length - 1]}T00:00:00`);
  const days = Math.max(1, Math.round((max - min) / 86400000) + 1);
  const unit = scale === 'month' ? 6 : scale === 'week' ? 12 : 24;
  const width = Math.max(720, days * unit);
  const rowHeight = 32;
  const svg = [`<svg viewBox="0 0 ${width} ${Math.max(50, (data.tasks.length + data.milestones.length) * rowHeight)}" ` +
    'role="img" aria-label="Gantt con tareas planificadas">' +
    '<defs><marker id="gantt-arrow" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto">' +
    '<path d="M0,0 L0,6 L7,3 z" fill="#555"></path></marker></defs>'];
  const positions = new Map();
  data.tasks.forEach((task, index) => {
    if (!task.planned_start || !task.planned_end) return;
    const start = new Date(`${task.planned_start}T00:00:00`);
    const end = new Date(`${task.planned_end}T00:00:00`);
    const x = Math.round((start - min) / 86400000) * unit;
    const barWidth = Math.max(8, (Math.round((end - start) / 86400000) + 1) * unit);
    const y = index * rowHeight + 8;
    const color = task.overdue ? '#a61b1b' : '#176b87';
    positions.set(task.id, { x, y: y + 9 });
    svg.push(`<text x="2" y="${y + 14}" font-size="11">${escapeText(task.name)}</text>`);
    svg.push(`<rect x="${x}" y="${y}" width="${barWidth}" height="18" fill="${color}">`);
    svg.push(`<title>${escapeText(task.name)} — ${task.overdue ? 'Atrasada' : 'En plazo'}</title></rect>`);
    const progressWidth = Math.max(0, barWidth * Number(task.progress || 0) / 100);
    svg.push(`<rect x="${x}" y="${y + 4}" width="${progressWidth}" height="10" fill="#58a6a6" aria-label="Avance ${escapeText(task.progress)}%"></rect>`);
    if (task.actual_start && task.actual_end) {
      const actualStart = new Date(`${task.actual_start}T00:00:00`);
      const actualEnd = new Date(`${task.actual_end}T00:00:00`);
      const actualX = Math.round((actualStart - min) / 86400000) * unit;
      const actualWidth = Math.max(6, (Math.round((actualEnd - actualStart) / 86400000) + 1) * unit);
      svg.push(`<rect x="${actualX}" y="${y + 20}" width="${actualWidth}" height="4" fill="#e67e22">` +
        `<title>Avance real: ${escapeText(task.actual_start)} a ${escapeText(task.actual_end)}</title></rect>`);
    }
  });
  data.dependencies.forEach((dependency) => {
    const from = positions.get(dependency.predecessor_id);
    const to = positions.get(dependency.successor_id);
    if (from && to) {
      svg.push(`<line x1="${from.x}" y1="${from.y}" x2="${to.x}" y2="${to.y}" stroke="#555" stroke-width="1" marker-end="url(#gantt-arrow)">` +
        `<title>${escapeText(dependency.type)} ${escapeText(dependency.lag_days)} días</title></line>`);
    }
  });
  data.milestones.forEach((milestone, index) => {
    if (!milestone.date) return;
    const day = new Date(`${milestone.date}T00:00:00`);
    const x = Math.round((day - min) / 86400000) * unit;
    const y = (data.tasks.length + index) * rowHeight + 12;
    svg.push(`<polygon points="${x},${y - 8} ${x + 8},${y} ${x},${y + 8} ${x - 8},${y}" fill="#d35400">` +
      `<title>${escapeText(milestone.name)} — hito</title></polygon>`);
  });
  svg.push('</svg>');
  container.innerHTML = svg.join('');
  return data;
}

const gantt = document.querySelector('#gantt');
const projectId = gantt?.dataset.projectId;
if (projectId) renderGantt(projectId).catch((error) => {
  document.querySelector('#gantt').textContent = error.message;
});

document.querySelector('#gantt-scale')?.addEventListener('change', () => {
  if (projectId) renderGantt(projectId).catch((error) => {
    document.querySelector('#gantt').textContent = error.message;
  });
});
