import { el, formatMoney, selectedCurrency } from './app.js';

const STATUS = { pending: 'Pendiente', approved: 'Aprobado', rejected: 'Rechazado' };
const RISK = { bajo: 'Bajo', medio: 'Medio', alto: 'Alto', critico: 'Crítico' };

function stat(label, value, sub, alert = false) {
  const wrap = el('div', `stat${alert ? ' is-alert' : ''}`);
  wrap.append(el('dt', 'stat-label', label), el('dd', 'stat-value num', value));
  if (sub) wrap.append(el('dd', 'stat-sub', sub));
  return wrap;
}

function fillTable(selector, entries, labels) {
  const body = document.querySelector(`${selector} tbody`);
  body.replaceChildren();
  if (!entries.length) {
    const row = el('tr');
    const cell = el('td', 'muted', 'Sin solicitudes registradas.');
    cell.colSpan = 2;
    row.append(cell);
    body.append(row);
    return;
  }
  entries.forEach(([key, count]) => {
    const row = el('tr');
    row.append(el('td', '', labels[key] || key), el('td', 'num', String(count)));
    body.append(row);
  });
}

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
  const stats = el('dl', 'stats');
  const deviation = Number(data.actual_cost) - Number(data.estimated_cost);
  stats.append(
    stat('Solicitudes', String(data.total)),
    stat('Costo estimado', formatMoney(data.estimated_cost, data.currency), `Real: ${formatMoney(data.actual_cost, data.currency)}`),
    stat('Desviación de costo', formatMoney(deviation, data.currency), deviation > 0 ? 'Sobre lo estimado' : 'Dentro de lo estimado', deviation > 0),
    stat('Atrasadas / riesgo crítico', `${data.overdue.length} / ${data.critical_risks.length}`,
      data.critical_risks.length ? data.critical_risks.join(', ') : 'Sin riesgos críticos',
      data.overdue.length > 0 || data.critical_risks.length > 0)
  );
  summary.append(stats);

  fillTable('#change-status-table', Object.entries(data.by_status), STATUS);
  fillTable('#change-risk-table', Object.entries(data.by_risk), RISK);

  const stages = document.querySelector('#change-stages');
  stages.replaceChildren();
  const max = Math.max(1, ...Object.values(data.stage_completion));
  Object.entries(data.stage_completion).forEach(([stage, count]) => {
    const row = el('div', 'bar-row');
    const bar = document.createElement('progress');
    bar.className = 'progress';
    bar.max = max;
    bar.value = count;
    bar.setAttribute('aria-label', `${stage}: ${count}`);
    row.append(el('span', '', stage), bar, el('span', 'num', String(count)));
    stages.append(row);
  });
}

const changeSummary = document.querySelector('#change-summary');
const projectId = changeSummary?.dataset.projectId;
if (projectId) loadChanges(projectId).catch((error) => {
  document.querySelector('#change-summary').textContent = error.message;
});
