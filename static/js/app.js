/** Utilidad única de formato monetario para valores ya convertidos por backend. */
export function formatMoney(value, currency = 'CLP') {
  const decimals = currency === 'CLP' ? 0 : 2;
  const number = Number(value || 0);
  const formatted = new Intl.NumberFormat('es-CL', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals
  }).format(number);
  return currency === 'USD' ? `US$ ${formatted}` : currency === 'UF' ? `UF ${formatted}` : `$${formatted}`;
}

export function selectedCurrency() {
  return document.querySelector('#currency-selector')?.value || 'CLP';
}

function setupPasswordToggles() {
  document.querySelectorAll('[data-password-toggle]').forEach((toggle) => {
    const input = document.getElementById(toggle.dataset.passwordToggle);
    if (!input) return;
    toggle.addEventListener('click', () => {
      const visible = input.type === 'text';
      input.type = visible ? 'password' : 'text';
      toggle.setAttribute('aria-pressed', String(!visible));
      toggle.setAttribute('aria-label', visible ? 'Mostrar contraseña' : 'Ocultar contraseña');
      toggle.querySelector('i')?.classList.toggle('bi-eye', visible);
      toggle.querySelector('i')?.classList.toggle('bi-eye-slash', !visible);
    });
  });
}

function setupPasswordStrength() {
  const input = document.querySelector('[data-password-strength]');
  const meter = document.querySelector('[data-strength-meter] span');
  const help = document.querySelector('[data-strength-help]');
  if (!input || !meter) return;
  input.addEventListener('input', () => {
    const value = input.value;
    const score = [value.length >= 12, /[A-Z]/.test(value), /[a-z]/.test(value), /\d/.test(value), /[^A-Za-z0-9]/.test(value)].filter(Boolean).length;
    meter.style.width = `${Math.min(score * 20, 100)}%`;
    meter.style.background = score < 3 ? 'var(--danger)' : score < 5 ? '#d99a00' : 'var(--success)';
    if (help) help.textContent = score < 3 ? 'Usa al menos 12 caracteres y combina letras, números y símbolos.' : score < 5 ? 'Contraseña aceptable. Agrega una combinación más para mejorarla.' : 'Contraseña fuerte.';
  });
}

function setupConfirmations() {
  document.addEventListener('submit', (event) => {
    const message = event.target.dataset.confirm;
    if (message && !window.confirm(message)) event.preventDefault();
  });
}

setupPasswordToggles();
setupPasswordStrength();
setupConfirmations();
