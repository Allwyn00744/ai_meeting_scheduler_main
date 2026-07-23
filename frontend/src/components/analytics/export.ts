/** Turns a Blob into a browser download without navigating away - used for both the client-built CSV and the server-built XLSX. */
export function triggerBlobDownload(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  document.body.removeChild(anchor);
  URL.revokeObjectURL(url);
}

/**
 * Client-side CSV export of the daily trend + summary - built from
 * data already fetched for the Overview section, so this needs no
 * round-trip to the server (the server-built export is only needed
 * for the Excel/XLSX case, which requires a real .xlsx binary).
 */
export function buildTrendCsv(
  trend: { date: string; upcoming: number; completed: number; cancelled: number; rescheduled: number }[],
  summaryRows: [string, string | number][]
): string {
  const lines: string[] = ["Date,Upcoming,Completed,Cancelled,Rescheduled"];
  for (const row of trend) {
    lines.push([row.date, row.upcoming, row.completed, row.cancelled, row.rescheduled].join(","));
  }
  lines.push("");
  lines.push("Summary metric,Value");
  for (const [label, value] of summaryRows) {
    const escaped = label.includes(",") ? `"${label}"` : label;
    lines.push(`${escaped},${value}`);
  }
  return lines.join("\n");
}
