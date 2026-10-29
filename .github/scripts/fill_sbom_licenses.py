"""Fill licenses Syft could not read for Python packages in docs/SBOM.json.

Syft reads the License-Expression and License fields of a package's METADATA.
A few packages (for example jinja2) declare their license only through a
"License :: OSI Approved :: ..." classifier, so this step reads that classifier
from the installed package in app/.venv and adds it to the component.
"""
import glob
import json
import os
import re
import sys

sbom_path = sys.argv[1] if len(sys.argv) > 1 else "docs/SBOM.json"
site_packages = sys.argv[2] if len(sys.argv) > 2 else "app/.venv/lib/python*/site-packages"


def normalize(name):
    return re.sub(r"[-_.]+", "-", name).lower()


classifiers = {}
for metadata in glob.glob(os.path.join(site_packages, "*.dist-info", "METADATA")):
    name, found = None, []
    with open(metadata, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if not line.strip():
                break  # headers end at the first blank line
            if line.startswith("Name:"):
                name = line.split(":", 1)[1].strip()
            elif line.startswith("Classifier: License ::"):
                found.append(line.split("::")[-1].strip())
    if name and found:
        classifiers[normalize(name)] = found

with open(sbom_path, encoding="utf-8") as fh:
    bom = json.load(fh)

filled = []
for component in bom.get("components", []):
    if component.get("licenses") or not component.get("purl", "").startswith("pkg:pypi/"):
        continue
    names = classifiers.get(normalize(component["name"]))
    if names:
        component["licenses"] = [{"license": {"name": n}} for n in names]
        filled.append(f'{component["name"]}: {", ".join(names)}')

with open(sbom_path, "w", encoding="utf-8") as fh:
    json.dump(bom, fh, indent=2)
    fh.write("\n")

print(f"licenses filled from classifiers: {len(filled)} {filled}")
