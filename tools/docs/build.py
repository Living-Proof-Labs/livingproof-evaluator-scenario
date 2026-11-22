# SPDX-License-Identifier: Apache-2.0
"""Stage authored pages and references generated from the installed checkout."""

import hashlib
import inspect
import json
import os
import re
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
version = os.environ.get("MANUAL_VERSION", "development")
run_id = os.environ.get("MANUAL_RUN_ID", "")
run_attempt = os.environ.get("MANUAL_RUN_ATTEMPT", "")
dirty = bool(output("git", "status", "--porcelain"))
if run_id or run_attempt or version != "development":
    number = r"(?:0|[1-9][0-9]*)"
    # The resolver emits stable X.Y.Z, X.Y.Z-pr.PR.RUN.ATTEMPT, or
    # X.Y.Z-main.RUN.ATTEMPT when main has no pending release.
    version_pattern = (
        rf"{number}\.{number}\.{number}(?:-(?:pr\.[1-9][0-9]*\.|main\.)"
        r"[1-9][0-9]*\.[1-9][0-9]*)?"
    )
    if not re.fullmatch(version_pattern, version):
        raise ValueError("Invalid planned documentation version")
    if dirty or os.environ.get("SOURCE_COMMIT") != sha:
        raise ValueError("Planned documentation requires the exact clean source checkout")
    if not all(re.fullmatch(r"[1-9][0-9]*", value) for value in (run_id, run_attempt)):
        raise ValueError("Planned documentation requires the current CI run and attempt")
package_version = result.package_version()
identity = {
    "source_commit": sha,
    "source_dirty": dirty,
    "version": version,
    "run_id": run_id,
    "run_attempt": run_attempt,
    "package_version": package_version,
    "brand": lock,
}
(root / "build.json").write_text(json.dumps(identity, indent=2) + "\n")
(root / "version.md").write_text(
    "# Version and source\n\n"
    f"Documentation version: **{version}**. [Source revision]({source}).\n\n"
    f"Builder package metadata: `{package_version}`. For a release, the manual is built from "
    "the selected commit before tagging. The package still derives its installed release version "
    "from the tag.\n\n"
    "Only the current manual is maintained; historical versions remain available as "
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
