// Number formatting for screen display. Money strings themselves come from the API (the engine's own
// format_money / format_money_compact), so they read exactly as in the Streamlit app.

const integer = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });

export function int(value: number | null | undefined): string {
  return value === null || value === undefined ? "n/a" : integer.format(value);
}

/** 0.2919 -> "29.2%" (one decimal by default, as on the Streamlit pages). */
export function pct(share: number | null | undefined, decimals = 1): string {
  if (share === null || share === undefined || Number.isNaN(share)) return "n/a";
  return `${(share * 100).toFixed(decimals)}%`;
}

export function score(value: number): string {
  return value.toFixed(1);
}

export function ratio(value: number): string {
  return value.toFixed(2);
}

/** "2025-12-20 16:56:18" -> "20 Dec 2025, 16:56" */
export function dateTime(value: string): string {
  const [day, time] = value.split(/[ T]/);
  return `${date(day)}${time ? `, ${time.slice(0, 5)}` : ""}`;
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

export function date(value: string): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(value ?? "");
  if (!match) return value ?? "";
  return `${Number(match[3])} ${MONTHS[Number(match[2]) - 1]} ${match[1]}`;
}

export function titleCase(value: string): string {
  return value.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());
}
