// The signed-in user's saved job lists (app/jobrec/saved_jobs.py).
// `list` is "bookmarks" or "applied".

export async function fetchSavedJobs(list, accessToken) {
  const res = await fetch(`/api/${list}`, {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
  if (!res.ok) throw new Error(`Failed to load ${list} (${res.status})`);
  return res.json();
}

export async function fetchIsSaved(list, id, accessToken) {
  const res = await fetch(`/api/${list}/${encodeURIComponent(id)}`, {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
  if (!res.ok) throw new Error(`Failed to load ${list} (${res.status})`);
  return (await res.json()).saved;
}

// Adds the job to the list, or removes it; resolves to the saved state.
export async function setSaved(list, id, saved, accessToken) {
  const res = await fetch(`/api/${list}/${encodeURIComponent(id)}`, {
    method: saved ? "PUT" : "DELETE",
    headers: { Authorization: `Bearer ${accessToken}` },
  });
  if (!res.ok) throw new Error(`Failed to save to ${list} (${res.status})`);
  return (await res.json()).saved;
}
