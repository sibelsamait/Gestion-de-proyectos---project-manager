import { formatMoney, selectedCurrency } from './app.js';

/** Carga el tablero de cambios con tablas accesibles. */
async function loadChanges(projectId) {
  const currency = selectedCurrency();
  const response = await fetch(`/api/projects/${encodeURIComponent(projectId)}/changes-dashboard?currency=${currency}`, {
    headers: { Accept: 'application/json' }
  });
  if (!response.ok) throw new Error('No fue posible cargar el tablero de cambios.');
  const data = await response.json();
  const summary = document.querySelector('#change-summary');
  summary.replaceChildren();
  [
    `Total: ${data.total}`,
    `Costo estimado: ${formatMoney(data.estimated_cost, data.currency)}; costo real: ${formatMoney(data.actual_cost, data.currency)}`,
    `Cambios atrasados: ${data.overdue.length}; riesgos críticos: ${data.critical_risks.length}`
  ].forEach((text) => {
    const paragraph = document.createElement('p');
    paragraph.textContent = text;
    summary.append(paragraph);
  });
  const changeBody = document.querySelector('#change-list-table tbody');
  data.changes.forEach((change) => {
    const row = document.createElement('tr');
    [change.code, change.status, change.stage, change.priority].forEach((value) => {
      const cell = document.createElement('td');
      cell.textContent = value;
      row.append(cell);
    });
    const actionCell = document.createElement('td');
    const editLink = document.createElement('a');
    editLink.href = `/api/projects/${encodeURIComponent(projectId)}/changes/${encodeURIComponent(change.id)}/edit`;
    editLink.textContent = 'Editar';
    actionCell.append(editLink);
    row.append(actionCell);
    changeBody.append(row);
  });
  const body = document.querySelector('#change-status-table tbody');
  Object.entries(data.by_status).forEach(([status, count]) => {
    const row = document.createElement('tr');
    const statusCell = document.createElement('td');
    statusCell.textContent = status;
    const countCell = document.createElement('td');
    countCell.textContent = String(count);
    row.append(statusCell, countCell);
    body.append(row);
  });
  const stageBody = document.querySelector('#change-stage-table tbody');
  Object.entries(data.stage_completion).forEach(([stage, count]) => {
    const row = document.createElement('tr');
    const stageCell = document.createElement('td');
    stageCell.textContent = stage;
    const countCell = document.createElement('td');
    countCell.textContent = String(count);
    row.append(stageCell, countCell);
    stageBody.append(row);
  });
  const metricBody = document.querySelector('#change-metrics-table tbody');
  [
    ['Tiempo promedio de implementación (días)', data.implementation.average_days],
    ['Cambios completados', data.implementation.completed],
    ['Efectividad (%)', data.effectiveness.percent],
    ['Adopción (escala 1-5)', data.adoption.score],
    ['Acciones correctivas registradas', data.corrective_actions.length],
  ].forEach(([label, value]) => {
    const row = document.createElement('tr');
    const labelCell = document.createElement('td');
    labelCell.textContent = label;
    const valueCell = document.createElement('td');
    valueCell.textContent = String(value);
    row.append(labelCell, valueCell);
    metricBody.append(row);
  });
  const alertBody = document.querySelector('#change-alerts-table tbody');
  [
    ['Cambios atrasados', data.alerts.overdue],
    ['Riesgos críticos', data.alerts.critical_risks],
    ['Metas KPI incumplidas', data.alerts.unmet_kpis],
  ].forEach(([label, values]) => {
    const row = document.createElement('tr');
    const labelCell = document.createElement('td');
    labelCell.textContent = label;
    const valueCell = document.createElement('td');
    valueCell.textContent = values.join(', ') || 'Ninguno';
    row.append(labelCell, valueCell);
    alertBody.append(row);
  });
}
const changeSummary = document.querySelector('#change-summary');
const projectId = changeSummary?.dataset.projectId;
if (projectId) loadChanges(projectId).catch((error) => {
  document.querySelector('#change-summary').textContent = error.message;
});
