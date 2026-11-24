import { el, formatMoney, formatNumber, selectedCurrency } from './app.js';

function stat(label, value, sub, alert = false) {
  const wrap = el('div', `stat${alert ? ' is-alert' : ''}`);
  wrap.append(el('dt', 'stat-label', label), el('dd', 'stat-value num', value));
  if (sub) wrap.append(el('dd', 'stat-sub', sub));
  return wrap;
}

/** Carga el tablero de seguimiento y lo presenta como indicadores y tabla de costos. */
async function loadTracking(projectId) {
  const currency = selectedCurrency();
  const response = await fetch(`/api/projects/${encodeURIComponent(projectId)}/tracking?currency=${currency}`, {
    headers: { Accept: 'application/json' }
  });
  if (!response.ok) throw new Error('No fue posible cargar el tablero.');
  const data = await response.json();
  const target = document.querySelector('#tracking-summary');
  target.replaceChildren();

  const stats = el('dl', 'stats');
  const utilization = data.professional_utilization;
  stats.append(
    stat('Avance promedio', `${formatNumber(data.progress, 1)} %`),
    stat('Tareas atrasadas', `${data.task_counts.overdue} de ${data.task_counts.total}`,
      `${data.task_counts.evaluated} con fecha de término`, data.task_counts.overdue > 0),
    stat('Hitos', `${data.milestones.on_time} cumplidos`, `${data.milestones.overdue} vencidos`, data.milestones.overdue > 0),
    stat('Utilización profesional', `${formatNumber(utilization.percent, 1)} %`,
      utilization.overallocated ? 'Sobreasignación detectada' : 'Dentro de capacidad', utilization.overallocated)
  );
  target.append(stats);

  const entries = Object.entries(data.costs_by_category);
  const card = el('section', 'card');
  const header = el('div', 'card-header');
  const titleWrap = el('div');
  titleWrap.append(el('h2', '', 'Costo planificado por categoría'), el('p', '', `Montos en ${data.currency}.`));
  header.append(titleWrap);
  card.append(header);
  if (!entries.length) {
    card.append(el('p', 'loading', 'Sin recursos asignados a tareas.'));
  } else {
    const total = entries.reduce((sum, [, value]) => sum + Number(value), 0);
    const body = el('div', 'card-body');
    entries.sort((a, b) => Number(b[1]) - Number(a[1])).forEach(([category, value]) => {
      const row = el('div', 'bar-row');
      const share = total ? (Number(value) / total) * 100 : 0;
      const bar = document.createElement('progress');
      bar.className = 'progress';
      bar.max = 100;
      bar.value = share;
      bar.setAttribute('aria-label', `${category}: ${formatNumber(share, 0)} %`);
      const label = el('span', '', category);
      label.title = `${formatNumber(share, 1)} % del total`;
      row.append(label, bar, el('span', 'num', formatMoney(value, data.currency)));
      body.append(row);
    });
    const totalRow = el('p', 'stat-sub num', `Total: ${formatMoney(total, data.currency)}`);
    body.append(totalRow);
    card.append(body);
  }
  target.append(card);
}

const trackingSummary = document.querySelector('#tracking-summary');
const projectId = trackingSummary?.dataset.projectId || document.querySelector('#gantt')?.dataset.projectId;
if (projectId) loadTracking(projectId).catch((error) => {
  document.querySelector('#tracking-summary').textContent = error.message;
});
