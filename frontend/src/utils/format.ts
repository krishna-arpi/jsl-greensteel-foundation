export function formatNumber(value: number, decimals = 2): string {
  return value.toLocaleString(undefined, {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

export function formatTco2e(value: number): string {
  return `${formatNumber(value, 3)} tCO2e/t`;
}

export function formatPct(value: number): string {
  return `${formatNumber(value, 1)}%`;
}

export function titleCase(id: string): string {
  return id
    .toLowerCase()
    .split("_")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}
