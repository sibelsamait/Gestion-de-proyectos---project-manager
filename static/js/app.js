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
