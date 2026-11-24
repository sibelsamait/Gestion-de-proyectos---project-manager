/** Utilidades compartidas de la interfaz. */

/** Formato monetario único para valores ya convertidos por el backend. */
export function formatMoney(value, currency = 'CLP') {
  const decimals = currency === 'CLP' ? 0 : 2;
  const number = Number(value || 0);
  const formatted = new Intl.NumberFormat('es-CL', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals
  }).format(Math.abs(number));
  const sign = number < 0 ? '-' : '';
  return sign + (currency === 'USD' ? `US$ ${formatted}` : currency === 'UF' ? `UF ${formatted}` : `$${formatted}`);
}

export function formatNumber(value, decimals = 0) {
  return new Intl.NumberFormat('es-CL', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals
  }).format(Number(value || 0));
}

/** Convierte AAAA-MM-DD a DD-MM-AAAA sin pasar por zonas horarias. */
export function formatDate(iso) {
  if (!iso) return '—';
  const [year, month, day] = iso.slice(0, 10).split('-');
  return `${day}-${month}-${year}`;
}

export function selectedCurrency() {
  return document.querySelector('#currency-selector')?.value || 'CLP';
}

export const escapeText = (value) => String(value ?? '').replace(/[&<>"']/g, (char) => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;'
}[char]));

/** Crea un elemento con clase y texto, evitando innerHTML con datos del servidor. */
export function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

/** POST que devuelve { ok, data } con el JSON de la respuesta. */
export async function postJson(url, body, { form = false } = {}) {
  const headers = { Accept: 'application/json' };
  if (!form) headers['Content-Type'] = 'application/json';
  const response = await fetch(url, {
    method: 'POST',
    headers,
    body: form ? body : JSON.stringify(body),
    credentials: 'same-origin'
  });
  let data = {};
  try { data = await response.json(); } catch { data = {}; }
  if (!response.ok && !data.error) {
    data.error = 'No fue posible completar la operación.';
  }
  return { ok: response.ok, data };
}

export function setFeedback(node, message, tone) {
  if (!node) return;
  node.textContent = message;
  node.classList.remove('is-error', 'is-success');
  if (tone) node.classList.add(`is-${tone}`);
}

document.querySelectorAll('select[data-autosubmit]').forEach((select) => {
  select.addEventListener('change', () => select.form?.requestSubmit());
});

document.querySelectorAll('form[data-confirm]').forEach((form) => {
  form.addEventListener('submit', (event) => {
    if (!window.confirm(form.dataset.confirm)) event.preventDefault();
  });
});
