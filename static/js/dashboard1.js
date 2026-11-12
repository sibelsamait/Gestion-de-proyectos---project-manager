import { formatMoney, selectedCurrency } from './app.js';

/** Carga el tablero de seguimiento y muestra texto además de indicadores visuales. */
function filterQuery() {
  const form = document.querySelector('#tracking-filters');
  if (!form) return '';
  return new URLSearchParams(new FormData(form)).toString();
}

export async function loadTracking(projectId) {
  const currency = selectedCurrency();
  const query = filterQuery();
  const response = await fetch(`/api/projects/${encodeURIComponent(projectId)}/tracking?currency=${currency}&${query}`, {
    headers: { Accept: 'application/json' }
  });
  if (!response.ok) throw new Error('No fue posible cargar el tablero.');
  const data = await response.json();
  document.querySelector('#tracking-summary').innerHTML =
    `<p>Avance: <strong>${Number(data.progress).toFixed(2)}%</strong></p>` +
    `<p>Tareas: ${data.task_counts.total}; atrasadas: ${data.task_counts.overdue}</p>` +
    `<p>Hitos cumplidos: ${data.milestones.on_time}; vencidos: ${data.milestones.overdue}</p>` +
    `<p>Costos (${data.currency}): ${Object.entries(data.costs_by_category).map(([key, value]) => `${key}: ${formatMoney(value, data.currency)}`).join(' · ')}</p>` +
    `<p>Utilización profesional: ${Number(data.professional_utilization.percent).toFixed(2)}%` +
    `${data.professional_utilization.overallocated ? ' — ⚠ Sobreasignación' : ' — En capacidad'}</p>`;
  const costBody = document.querySelector('#tracking-cost-table tbody');
  costBody.replaceChildren();
  Object.entries(data.costs_by_category).forEach(([category, value]) => {
    const row = document.createElement('tr');
    row.innerHTML = `<td>${category}</td><td>${formatMoney(value, data.currency)}</td>`;
    costBody.append(row);
  });
  const kpiBody = document.querySelector('#tracking-kpi-table tbody');
  kpiBody.replaceChildren();
  data.kpis.forEach((kpi) => {
    const row = document.createElement('tr');
    row.innerHTML = `<td>${kpi.name}</td><td>${kpi.result ?? 'Sin medir'}</td><td>${kpi.status}</td>`;
    kpiBody.append(row);
  });
  const taskBody = document.querySelector('#tracking-task-table tbody');
  taskBody.replaceChildren();
  data.tasks.forEach((task) => {
    const row = document.createElement('tr');
    row.innerHTML = `<td>${task.name}</td><td>${task.etapa ?? 'Sin etapa'}</td>` +
      `<td>${task.planned_start ?? '—'}</td><td>${task.planned_end ?? '—'}</td><td>${task.progress}%</td>`;
    taskBody.append(row);
  });
}
const trackingSummary = document.querySelector('#tracking-summary');
const projectId = trackingSummary?.dataset.projectId || document.querySelector('#gantt')?.dataset.projectId;
if (projectId) loadTracking(projectId).catch((error) => {
  document.querySelector('#tracking-summary').textContent = error.message;
});

document.querySelector('#tracking-filters')?.addEventListener('submit', (event) => {
  event.preventDefault();
  if (projectId) {
    loadTracking(projectId).then(() => {
      window.dispatchEvent(new CustomEvent('dashboard-filters-changed'));
    }).catch((error) => {
      document.querySelector('#tracking-summary').textContent = error.message;
    });
  }
});
