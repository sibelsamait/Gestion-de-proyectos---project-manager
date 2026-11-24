/** Acciones de gestión dentro del detalle de proyecto conectadas a endpoints JSON existentes. */
import { postJson, setFeedback } from './app.js';

const reloadSoon = () => window.setTimeout(() => window.location.reload(), 700);

// Dependencias entre tareas: POST /projects/<id>/tasks/<sucesora>/dependencies
document.querySelectorAll('form[data-dependency-form]').forEach((form) => {
  const feedback = form.parentElement.querySelector('[data-feedback]');
  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    const data = new FormData(form);
    const successor = data.get('successor_id');
    if (successor === data.get('predecessor_id')) {
      setFeedback(feedback, 'Una tarea no puede depender de sí misma.', 'error');
      return;
    }
    data.delete('successor_id');
    const url = form.dataset.endpointTemplate.replace('__TASK__', encodeURIComponent(successor));
    const button = form.querySelector('button[type="submit"]');
    button.disabled = true;
    const { ok, data: body } = await postJson(url, data, { form: true });
    button.disabled = false;
    setFeedback(feedback, ok ? `${body.message} Actualizando…` : body.error, ok ? 'success' : 'error');
    if (ok) reloadSoon();
  });
});

// Medición de KPI: POST /api/projects/<id>/kpis/<kpi>/measure con las variables declaradas.
document.querySelectorAll('[data-kpi-form]').forEach((details) => {
  const form = details.querySelector('form');
  const feedback = form.querySelector('[data-feedback]');
  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    const values = {};
    for (const input of form.querySelectorAll('input[name]')) {
      if (input.value === '' || Number.isNaN(Number(input.value))) {
        setFeedback(feedback, `Ingrese un valor numérico para ${input.name}.`, 'error');
        input.focus();
        return;
      }
      values[input.name] = Number(input.value);
    }
    const { ok, data } = await postJson(details.dataset.endpoint, values);
    setFeedback(
      feedback,
      ok ? `Resultado registrado: ${data.result}. Actualizando…` : data.error,
      ok ? 'success' : 'error'
    );
    if (ok) reloadSoon();
  });
});

// Aprobación de cambios: POST /api/projects/<id>/changes/<cambio>/approve
const approveFeedback = document.querySelector('[data-approve-feedback]');
document.querySelectorAll('button[data-approve]').forEach((button) => {
  button.addEventListener('click', async () => {
    const message = `¿Aprobar la solicitud ${button.dataset.label}? Se aplicará su impacto en presupuesto y fechas, y se registrará una línea base.`;
    if (!window.confirm(message)) return;
    button.disabled = true;
    const { ok, data } = await postJson(button.dataset.approve, {});
    setFeedback(
      approveFeedback,
      ok ? `Solicitud ${button.dataset.label} aprobada (${data.applications} cambio(s) aplicado(s)). Actualizando…` : data.error,
      ok ? 'success' : 'error'
    );
    if (ok) reloadSoon(); else button.disabled = false;
  });
});

// Formulario de recursos: muestra solo los campos que usa la fórmula del tipo elegido.
const typeSelect = document.querySelector('select[data-resource-type]');
if (typeSelect) {
  const sync = () => {
    const professional = typeSelect.value === 'Profesional';
    document.querySelectorAll('[data-resource-group]').forEach((group) => {
      const visible = (group.dataset.resourceGroup === 'Profesional') === professional;
      group.hidden = !visible;
    });
  };
  typeSelect.addEventListener('change', sync);
  sync();
}
