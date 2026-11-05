/** Carga el tablero de cambios con tablas accesibles. */
async function loadChanges(projectId) {
  const response = await fetch(`/api/projects/${encodeURIComponent(projectId)}/changes-dashboard`, {
    headers: { Accept: 'application/json' }
  });
  if (!response.ok) throw new Error('No fue posible cargar el tablero de cambios.');
  const data = await response.json();
  const summary = document.querySelector('#change-summary');
  summary.replaceChildren();
  [
    `Total: ${data.total}`,
    `Costo estimado: ${data.estimated_cost}; costo real: ${data.actual_cost}`,
    `Cambios atrasados: ${data.overdue.length}; riesgos críticos: ${data.critical_risks.length}`
  ].forEach((text) => {
    const paragraph = document.createElement('p');
    paragraph.textContent = text;
    summary.append(paragraph);
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
}
const changeSummary = document.querySelector('#change-summary');
const projectId = changeSummary?.dataset.projectId;
if (projectId) loadChanges(projectId).catch((error) => {
  document.querySelector('#change-summary').textContent = error.message;
});
