const { getAccessTokenSilently } = useAuth0();

async function loadProfile() {
  const token = await getAccessTokenSilently();

  const res = await fetch("/api/profile", {
    headers: {
      Authorization: `Bearer ${token}`,
    },
  });

  if (!res.ok) {
    throw new Error(`Profile request failed: ${res.status}`);
  }

  return await res.json();
}