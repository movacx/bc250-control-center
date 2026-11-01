/** Only a successful job response may replace the current operation. */
export function jobState(response) {
  if (!response || response.status !== 200 || response.error) return "unavailable";
  if (response.id === 0) return "idle";
  return Number.isInteger(response.id) && response.id > 0 && typeof response.done === "boolean"
    ? "job" : "unavailable";
}
