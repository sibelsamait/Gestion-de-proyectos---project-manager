/** Renderiza un Gantt SVG accesible a partir del endpoint JSON. */
import { selectedCurrency } from './app.js';
const escapeText = (value) => String(value ?? '').replace(/[&<>"']/g, (char) => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;'
}[char]));

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
    row.innerHTML = `<td>${escapeText(task.name)}</td><td>${escapeText(task.planned_start)}</td>` +
      `<td>${escapeText(task.planned_end)}</td><td>${escapeText(task.progress)}%</td>` +
      `<td>${task.overdue ? '⚠ Atrasada' : 'En plazo'}</td>`;
    tableBody.append(row);
  });
  const dated = data.tasks.flatMap((task) => [task.planned_start, task.planned_end].filter(Boolean));
  if (!dated.length) {
    container.textContent = 'No hay fechas planificadas para dibujar.';
    return data;
  }
  const min = new Date(`${dated.sort()[0]}T00:00:00`);
  const max = new Date(`${dated[dated.length - 1]}T00:00:00`);
  const days = Math.max(1, Math.round((max - min) / 86400000) + 1);
  const width = Math.max(720, days * 24);
  const rowHeight = 32;
  const svg = [`<svg viewBox="0 0 ${width} ${Math.max(50, data.tasks.length * rowHeight)}" ` +
    'role="img" aria-label="Gantt con tareas planificadas">'];
  data.tasks.forEach((task, index) => {
    if (!task.planned_start || !task.planned_end) return;
    const start = new Date(`${task.planned_start}T00:00:00`);
    const end = new Date(`${task.planned_end}T00:00:00`);
    const x = Math.round((start - min) / 86400000) * 24;
    const barWidth = Math.max(8, (Math.round((end - start) / 86400000) + 1) * 24);
    const y = index * rowHeight + 8;
    const color = task.overdue ? '#a61b1b' : '#176b87';
    svg.push(`<text x="2" y="${y + 14}" font-size="11">${escapeText(task.name)}</text>`);
    svg.push(`<rect x="${x}" y="${y}" width="${barWidth}" height="18" fill="${color}">`);
    svg.push(`<title>${escapeText(task.name)} — ${task.overdue ? 'Atrasada' : 'En plazo'}</title></rect>`);
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
