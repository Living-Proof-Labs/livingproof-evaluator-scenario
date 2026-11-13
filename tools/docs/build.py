# SPDX-License-Identifier: Apache-2.0
"""Stage authored pages and references generated from the installed checkout."""

import hashlib
import inspect
import json
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

from livingproof_evaluator_scenario import checks, result


def output(*args):
    return subprocess.check_output(args, text=True).strip()


root = Path("artifacts/docs-source")
if root.exists():
    shutil.rmtree(root)
shutil.copytree("docs", root)
lock = json.loads(Path("docs-brand.lock.json").read_text())
url = f"https://raw.githubusercontent.com/{lock['repository']}/{lock['commit']}/{lock['path']}"
with urllib.request.urlopen(url, timeout=30) as response:
    brand = response.read()
if hashlib.sha256(brand).hexdigest() != lock["sha256"]:
    raise ValueError("Shared brand checksum mismatch")
(root / "assets").mkdir()
(root / "assets/brand.css").write_bytes(brand)
sha = output("git", "rev-parse", "HEAD")
source = f"https://github.com/Living-Proof-Labs/livingproof-evaluator-scenario/tree/{sha}"
identity = {"source_commit": sha, "package_version": result.package_version(), "brand": lock}
(root / "build.json").write_text(json.dumps(identity, indent=2) + "\n")
(root / "version.md").write_text(
    "# Version and source\n\n"
    f"Docs: development · [{sha[:12]}]({source})\n\n"
    f"Full source revision: `{sha}`. Installed package version: `{result.package_version()}`.\n\n"
    "This manual follows the built checkout, not an independently claimed stable release. "
    "Only the current manual is maintained; historical releases remain available as "
    "[source tags](https://github.com/Living-Proof-Labs/livingproof-evaluator-scenario/tags).\n\n"
    "[Machine-readable build identity](build.json). Local uncommitted changes are not "
    "represented by the commit identity; use the CI artifact for review evidence.\n"
)
license_text = Path("LICENSE").read_text()
(root / "license.md").write_text(
    "# License\n\nRepository content is Apache-2.0. "
    "The fetched shared brand retains its upstream license notice.\n\n```text\n"
    + license_text
    + "\n```\n"
)
help_text = output(sys.executable, "-m", "livingproof_evaluator_scenario", "--help")
reference = "# Reference\n\n## Commands\n\nGenerated from native help.\n\n```text\n"
reference += help_text + "\n```\n\n## API\n\nGenerated from installed public functions.\n"
for module in (checks, result):
    reference += f"\n### {module.__name__}\n"
    for name, function in inspect.getmembers(module, inspect.isfunction):
        if not name.startswith("_") and function.__module__ == module.__name__:
            reference += f"\n#### `{name}{inspect.signature(function)}`\n\n"
            reference += (inspect.getdoc(function) or "No function docstring supplied.") + "\n"
reference += "\n## Tasks\n\nRun from the prepared repository checkout, not a Docker wrapper.\n"
tasks = json.loads(output("task", "--list", "--json"))["tasks"]
for task in tasks:
    name = task["name"]
    reference += f"\n### {name}\n\n```text\n" + output("task", name, "--summary") + "\n```\n"
(root / "reference.md").write_text(reference)
