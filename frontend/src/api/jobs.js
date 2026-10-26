// Job listings come from the Flask API (app/src/jobs.py documents the job shape).

export async function fetchJobs(accessToken, params = {}) {
  const query = new URLSearchParams();
  if (params.desiredSalary != null) query.set("desired_salary", params.desiredSalary);
  if (params.location) query.set("location", params.location);
  const suffix = query.size ? `?${query}` : "";
  const res = await fetch(`/api/jobs${suffix}`, {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
  if (!res.ok) throw new Error(`Failed to load jobs (${res.status})`);
  return res.json();
}

// Resolves to null when the job doesn't exist.
export async function fetchJob(id, accessToken) {
  const res = await fetch(`/api/jobs/${encodeURIComponent(id)}`, {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`Failed to load job (${res.status})`);
  return res.json();
}

// Reasons a user can pick when reporting a listing. `code` is what gets sent to the
// backend (stable, safe to store in a DB column); `label` is only for display.
export const REPORT_REASONS = [
  { code: "closed", label: "Listing is no longer open." },
  { code: "inaccurate", label: "Listing contains inaccuracies." },
  { code: "harmful", label: "Listing contains harmful content." },
  { code: "compatibility", label: "Listing's compatibility rating is inaccurate." },
  { code: "other", label: "Other:" },
];

// Sends a user's report about a job listing.
//
// Backend contract (TODO: not implemented in Flask yet):
//   POST /api/jobs/<job_id>/report
//   Authorization: Bearer <token>   -> identifies the reporting user
//   Body: { "reason": "<one of REPORT_REASONS codes>", "details": "<free text, or null>" }
//   `details` holds the text typed into the "Other" box and is only set when reason is "other".
//   Respond 201 on success. Suggested table: reports(id, job_id, user_id, reason, details, created_at).
export async function reportJob(id, { reason, details }, accessToken) {
  const res = await fetch(`/api/jobs/${encodeURIComponent(id)}/report`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${accessToken}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ reason, details: details ?? null }),
  });
  // TODO: remove once the endpoint exists. Until then Flask answers 404/405, and we
  // let the report "succeed" so the UI flow still works.
  if (res.status === 404 || res.status === 405) {
    console.warn("POST /api/jobs/:id/report is not implemented yet; report not saved.", { id, reason, details });
    return;
  }
  if (!res.ok) throw new Error(`Failed to report job (${res.status})`);
}

export function compatibilityColor(score) {
  if (score >= 90) return "text-[#5E9A4E]";
  if (score >= 70) return "text-[#9C9A2E]";
  return "text-[#C0504D]";
}