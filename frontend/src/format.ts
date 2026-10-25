/**
 * Display formatting only. These functions format values that came from events; they never compute
 * business numbers.
 */

const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** AED amount with thousands separators: 43529 -> "43,529", 61419.6 -> "61,419.60". */
export function formatAed(value: number): string {
  const whole = Math.round(Math.abs(value) * 100) % 100 === 0;
  return value.toLocaleString("en-GB", {
    minimumFractionDigits: whole ? 0 : 2,
    maximumFractionDigits: 2,
  });
}

/** "AED 43,529" (negative amounts as "-AED 4,929"). */
export function aed(value: number): string {
  return value < 0 ? `-AED ${formatAed(-value)}` : `AED ${formatAed(value)}`;
}

/** A quantity with up to two decimals and separators: 2.02 -> "2.02", 1500 -> "1,500". */
export function formatNumber(value: number): string {
  return value.toLocaleString("en-GB", { maximumFractionDigits: 2 });
}

/** A signed change in quantity: 200 -> "+200", 0 -> "0". */
export function formatDelta(value: number): string {
  return value > 0 ? `+${formatNumber(value)}` : formatNumber(value);
}

/** Working days: 1 -> "1 working day", 8 -> "8 working days". */
export function workingDays(value: number): string {
  return `${formatNumber(value)} working day${value === 1 ? "" : "s"}`;
}

/** ISO date "2027-02-03" -> "Wed 3 Feb 2027". Returns the input when it is not an ISO date. */
export function formatDate(iso: string): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  if (!match) return iso;
  const [, y, m, d] = match;
  const date = new Date(Date.UTC(Number(y), Number(m) - 1, Number(d)));
  return `${WEEKDAYS[date.getUTCDay()]} ${date.getUTCDate()} ${MONTHS[date.getUTCMonth()]} ${date.getUTCFullYear()}`;
}

/** A claim value with its unit, for chips: (43529, "AED") -> "AED 43,529", (8, "wd") -> "8 wd". */
export function formatValue(value: number | string, unit: string): string {
  if (typeof value === "string") return unit ? `${value} ${unit}` : value;
  if (unit.toUpperCase() === "AED") return aed(value);
  return unit ? `${formatNumber(value)} ${unit}` : formatNumber(value);
}

/** A parameter value as the user sees it: (2.5, step 0.1) -> "2.5", (600, step 100) -> "600". */
export function formatParameter(value: number, step: number): string {
  const decimals = step < 1 ? Math.max(0, Math.ceil(-Math.log10(step) - 1e-9)) : 0;
  return value.toFixed(decimals);
}

/** Fill an instruction template such as "Widen by {widen_by_m} m" with the chosen parameters. */
export function fillTemplate(
  template: string,
  values: Record<string, number>,
  steps: Record<string, number> = {},
): string {
  return template.replace(/\{(\w+)\}/g, (whole, name: string) => {
    const value = values[name];
    return value === undefined ? whole : formatParameter(value, steps[name] ?? 1);
  });
}

/** "OPT-A320-A340" -> "Extra crews on A320, A340"; "OPT-NONE" -> "No extra crews". */
export function describeOption(optionId: string): string {
  if (optionId === "OPT-NONE") return "No extra crews";
  return `Extra crews on ${optionId.replace(/^OPT-/, "").split("-").join(", ")}`;
}

/** Plain-English labels for message intents. */
export const INTENT_LABEL: Record<string, string> = {
  ASSESS: "Assessment",
  PROPOSE: "Proposal",
  CHALLENGE: "Challenge",
  AGREE: "Agreement",
  ASK: "Question",
  ANSWER: "Answer",
  VERIFY: "Verification",
  SUMMARISE: "Summary",
};

/** Plain-English labels for change types. */
export const CHANGE_LABEL: Record<string, string> = {
  wall_height: "Raise the boundary wall",
  road_widening: "Widen the internal road",
  paving_area: "Add paving area",
};
