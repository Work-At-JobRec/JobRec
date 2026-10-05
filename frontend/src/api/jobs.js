// Job listings come from the Flask API (app/src/jobs.py documents the job shape).

export async function fetchJobs() {
  const res = await fetch("/api/jobs");
  if (!res.ok) throw new Error(`Failed to load jobs (${res.status})`);
  return res.json();
}

// Resolves to null when the job doesn't exist.
export async function fetchJob(id) {
  const res = await fetch(`/api/jobs/${encodeURIComponent(id)}`);
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`Failed to load job (${res.status})`);
  return res.json();
}

export function compatibilityColor(score) {
  if (score >= 90) return "text-[#5E9A4E]";
  if (score >= 70) return "text-[#9C9A2E]";
  return "text-[#C0504D]";
}