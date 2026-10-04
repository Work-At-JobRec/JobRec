export async function getVersion() {
  const res = await fetch("/api/version");
  console.log(`result status: ${res.status}`)
  console.log(`result okay?: ${res.ok}`)
  if (!(res.ok)) throw new Error(`Failed to get API version: ${res.status}`);
  return res.json();
}