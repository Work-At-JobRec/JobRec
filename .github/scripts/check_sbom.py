"""Sanity-check docs/SBOM.json: CycloneDX, every component versioned, license coverage."""
import collections
import json
import sys

path = sys.argv[1] if len(sys.argv) > 1 else "docs/SBOM.json"
with open(path, encoding="utf-8") as fh:
    bom = json.load(fh)

assert bom.get("bomFormat") == "CycloneDX", "not a CycloneDX document"
components = [c for c in bom.get("components", []) if c.get("type") == "library"]
assert components, "SBOM lists no components"

unversioned = [c["name"] for c in components if not c.get("version")]
unlicensed = [f'{c["name"]}@{c.get("version")}' for c in components if not c.get("licenses")]
ecosystems = collections.Counter(c.get("purl", "").split("/")[0] for c in components)

print(f"{len(components)} components: {dict(ecosystems)}")
print(f"without a version: {len(unversioned)}")
print(f"without a license: {len(unlicensed)} {unlicensed}")
if unversioned:
    sys.exit(f"components without a version: {unversioned}")
