import { formatMoney, selectedCurrency } from './app.js';

/** Carga el tablero de seguimiento y muestra texto además de indicadores visuales. */
async function loadTracking(projectId) {
  const currency = selectedCurrency();
  const response = await fetch(`/api/projects/${encodeURIComponent(projectId)}/tracking?currency=${currency}`, {
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
}
const trackingSummary = document.querySelector('#tracking-summary');
const projectId = trackingSummary?.dataset.projectId || document.querySelector('#gantt')?.dataset.projectId;
if (projectId) loadTracking(projectId).catch((error) => {
  document.querySelector('#tracking-summary').textContent = error.message;
});
