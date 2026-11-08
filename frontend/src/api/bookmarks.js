// The signed-in user's bookmarked jobs (app/jobrec/bookmarks.py).

export async function fetchBookmarks(accessToken) {
  const res = await fetch("/api/bookmarks", {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
  if (!res.ok) throw new Error(`Failed to load bookmarks (${res.status})`);
  return res.json();
}

export async function fetchIsBookmarked(id, accessToken) {
  const res = await fetch(`/api/bookmarks/${encodeURIComponent(id)}`, {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
  if (!res.ok) throw new Error(`Failed to load bookmark (${res.status})`);
  return (await res.json()).bookmarked;
}

// Bookmarks the job, or removes its bookmark; resolves to the saved state.
export async function setBookmarked(id, bookmarked, accessToken) {
  const res = await fetch(`/api/bookmarks/${encodeURIComponent(id)}`, {
    method: bookmarked ? "PUT" : "DELETE",
    headers: { Authorization: `Bearer ${accessToken}` },
  });
  if (!res.ok) throw new Error(`Failed to save bookmark (${res.status})`);
  return (await res.json()).bookmarked;
}
