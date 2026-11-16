# SPDX-License-Identifier: Apache-2.0
"""One ``livingproof-evaluator-result/1.1.0`` document per trial.

The descriptor is this evaluator's own entry. Findings stay empty in this
slice: a failed trial keeps the assessment sentence on the report, and a
later issue copies failed-step rationales into ``descriptor.findings``.

Each result cites the limits it graded. The citation is a contract input
reference, ``role`` ``thresholds`` plus a URI and sha256. ``write_run`` writes
those bytes as ``thresholds.json`` in the output directory, so a copy of that
directory keeps the file the digest names.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
from pathlib import Path

from livingproof_evaluator_scenario.checks import INSUFFICIENT, assess, limits_from_thresholds
from livingproof_evaluator_scenario.compat import require_evidence_format
from livingproof_evaluator_scenario.errors import EvaluationError
from livingproof_evaluator_scenario.compat.recorded import (
    PARAMETERS_COMMIT,
    PARAMETERS_PATH,
    PARAMETERS_REPOSITORY,
    PARAMETERS_SHA256,
    PARAMETERS_TAG,
    parameters_document,
)

DISTRIBUTION = "livingproof-evaluator-scenario"
EVALUATOR_ID = "livingproof-scenario"
DISPLAY_NAME = "Scenario"
SHORT_TITLE = "Scenario"
PUBLISHER = "Living Proof Labs"
TIER = "verdict"
PURPOSE = "Checks each step of the scenario against the limits in its spec."
# Subset-legal redraw from livingproof-evaluator
# examples/descriptor/scenario-with-icon/result.json. Same paths, currentColor, no title.
ICON = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none">'
    '<g stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
    '<path d="M6.5 7L10.5 11L17.5 4"/>'
    '<rect x="4" y="9" width="16" height="11" rx="4"/>'
    "</g>"
    '<g fill="currentColor">'
    '<circle cx="8.5" cy="14.5" r="1.5"/>'
    '<circle cx="15.5" cy="14.5" r="1.5"/>'
    "</g></svg>"
)
_VERDICT = {"PASS": "PASS", "FAIL": "FAIL", INSUFFICIENT: "INCONCLUSIVE"}
THRESHOLDS_ROLE = "thresholds"
THRESHOLDS_FILENAME = "thresholds.json"


def package_version() -> str:
    """Installed distribution version. hatch-vcs fills it from the git tag."""
    return importlib.metadata.version(DISTRIBUTION)


def trial_id(configuration: str, index: int) -> str:
    """Result id ``verify`` already assigns: ``{configuration}-seed-{index:02d}``."""
    if not isinstance(index, int) or isinstance(index, bool) or index < 1:
        raise ValueError(f"trial index must be an integer >= 1, got {index!r}")
    if not isinstance(configuration, str) or not configuration:
        raise ValueError("configuration name is missing")
    return f"{configuration}-seed-{index:02d}"


def grade_trial(steps: list[dict]) -> str:
    """Trial outcome from its step verdicts. Every step must pass."""
    if any(step["verdict"] == "INCONCLUSIVE" for step in steps):
        return "INCONCLUSIVE"
    if any(step["verdict"] != "PASS" for step in steps):
        return "FAIL"
    return "PASS"


def canonical_json(value) -> bytes:
    """UTF-8 JSON with sorted keys, no insignificant whitespace, and one trailing newline.

    The sha256 on a thresholds input is the digest of these bytes. The same
    value always produces the same bytes. ``NaN`` and ``Infinity`` are rejected.
    """
    text = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )
    return (text + "\n").encode("utf-8")


def parameters_source(parameters: dict | None = None) -> dict:
    """Specification identity for the parameter document that selected the limits.

    The vendored ``parameters.json`` records its repository, tag, commit, path,
    and file sha256. Any other document records only the sha256 of its canonical
    JSON, because no tag or commit is known for it.
    """
    known = parameters_document()
    document = known if parameters is None else parameters
    if document == known:
        return {
            "repository": PARAMETERS_REPOSITORY,
            "tag": PARAMETERS_TAG,
            "commit": PARAMETERS_COMMIT,
            "path": PARAMETERS_PATH,
            "sha256": PARAMETERS_SHA256,
        }
    return {"sha256": hashlib.sha256(canonical_json(document)).hexdigest()}


def thresholds_document(thresholds: dict, parameters: dict | None = None) -> dict:
    """The exact limits graded, plus the parameter-file source when it is known.

    Limit names are the parameter file's names. ``half_width`` is recorded as
    ``exit_segment``. Keys that grading ignores are omitted, so two objects
    that grade as the same limits have one document.
    """
    document = parameters_document() if parameters is None else parameters
    return {
        "limits": limits_from_thresholds(document, thresholds),
        "parameters": parameters_source(parameters),
    }


def thresholds_bytes(thresholds: dict, parameters: dict | None = None) -> bytes:
    """Canonical bytes of :func:`thresholds_document`. This is the digest input."""
    return canonical_json(thresholds_document(thresholds, parameters))


def thresholds_input(
    thresholds: dict, parameters: dict | None = None, *, uri: str = THRESHOLDS_FILENAME
) -> dict:
    """Contract input reference for the limits that will be graded.

    ``role``, ``uri``, and ``sha256`` are the only fields. ``uri`` is the file
    name :func:`write_run` writes beside the results.
    """
    raw = thresholds_bytes(thresholds, parameters)
    return {"role": THRESHOLDS_ROLE, "uri": uri, "sha256": hashlib.sha256(raw).hexdigest()}


def trial_result(
    observation: dict,
    thresholds: dict,
    trial_id: str,
    *,
    seed=None,
    inputs: list[dict],
    started_at: str,
    completed_at: str,
    world: dict | None = None,
    parameters: dict | None = None,
) -> dict:
    """The result document for one trial. Findings are empty.

    ``inputs`` gains the thresholds reference for the limits this call grades.
    A caller-supplied entry with that role is replaced, so the digest is the
    canonical limits rather than a digest the caller asserted.
    """
    if not isinstance(trial_id, str) or not trial_id:
        raise ValueError("trial_id is missing")
    _timestamp(started_at, "started_at")
    _timestamp(completed_at, "completed_at")
    if not isinstance(inputs, list) or not inputs:
        raise ValueError("inputs must list at least one artifact")
    inputs = [
        item
        for item in inputs
        if not (isinstance(item, dict) and item.get("role") == THRESHOLDS_ROLE)
    ]
    inputs.append(thresholds_input(thresholds, parameters))
    _inputs(inputs)
    steps = []
    for item in assess(observation, thresholds, trial_id, seed, world=world, parameters=parameters):
        verdict = _VERDICT.get(item["status"])
        if verdict is None:
            raise ValueError(f"check {item['evaluator']} returned {item['status']!r}")
        steps.append({"id": item["evaluator"], "verdict": verdict, "summary": item["rationale"]})
    version = package_version()
    return {
        "format": "livingproof-evaluator-result/1.1.0",
        "evaluator": {
            "id": EVALUATOR_ID,
            "version": version,
            "kind": "scenario",
            "execution": "deterministic",
            "display_name": DISPLAY_NAME,
            "publisher": PUBLISHER,
            "icon": ICON,
        },
        "inputs": inputs,
        "timestamps": {"started_at": started_at, "completed_at": completed_at},
        "scenario": {"trial_id": trial_id, "steps": steps},
        "descriptor": {
            "title": DISPLAY_NAME,
            "short_title": SHORT_TITLE,
            "icon": ICON,
            "icon_accessible_name": DISPLAY_NAME,
            "purpose": PURPOSE,
            "version": version,
            "tier": TIER,
            "findings": [],
        },
    }


def _with_trial(message: str, index, path: str, ident: str) -> str:
    """``message`` with the failing trial named after its first sentence."""
    where = f"(trial {index}: {path}, result {ident})"
    first, sep, rest = message.partition(". ")
    if not sep:
        return f"{message.rstrip('.')} {where}."
    return f"{first} {where}. {rest}"


def write_run(
    manifest_path: Path,
    thresholds: dict,
    out_dir: Path,
    *,
    started_at: str,
    completed_at: str,
    world: dict | None = None,
    parameters: dict | None = None,
) -> list[Path]:
    """Write one result file per trial, and ``thresholds.json`` beside them.

    The file name of each result is the result id. ``thresholds.json`` is the
    canonical limits every result in this call cites. Its bytes are what the
    thresholds input's sha256 names, so keeping the output directory keeps the
    referenced input.

    Every trial is read and graded before anything is written. A trial that cannot
    be graded (for example an unknown observation format) raises before the output
    directory is created or changed, so a failed run leaves no partial results.
    """
    manifest_path = Path(manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    require_evidence_format(manifest.get("format"))
    bound = thresholds_bytes(thresholds, parameters)
    configuration = manifest["configuration"]["name"]
    manifest_bytes = manifest_path.read_bytes()
    documents = []
    ordered = sorted(manifest["trials"]["results"], key=lambda item: item["index"])
    for trial in ordered:
        index = trial["index"]
        ident = trial_id(configuration, index)
        observation_path = manifest_path.parent / trial["path"]
        observation_bytes = observation_path.read_bytes()
        observation = json.loads(observation_bytes)
        try:
            document = trial_result(
                observation,
                thresholds,
                ident,
                seed=("trial", index),
                inputs=[
                    {
                        "role": "observation",
                        "uri": trial["path"],
                        "sha256": hashlib.sha256(observation_bytes).hexdigest(),
                    },
                    {
                        "role": "manifest",
                        "uri": manifest_path.name,
                        "sha256": hashlib.sha256(manifest_bytes).hexdigest(),
                    },
                ],
                started_at=started_at,
                completed_at=completed_at,
                world=world,
                parameters=parameters,
            )
        except EvaluationError as exc:
            raise EvaluationError(_with_trial(str(exc), index, trial["path"], ident)) from exc
        documents.append((f"{ident}.json", json.dumps(document, indent=2) + "\n"))
    written = []
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / THRESHOLDS_FILENAME).write_bytes(bound)
    for name, text in documents:
        path = out_dir / name
        path.write_text(text, encoding="utf-8")
        written.append(path)
    return written


def _timestamp(value: str, name: str) -> None:
    if not isinstance(value, str) or len(value) != 20 or not value.endswith("Z"):
        raise ValueError(f"{name} must be a UTC timestamp like 2026-11-12T05:11:41Z, got {value!r}")


def _inputs(inputs: list[dict]) -> None:
    if not isinstance(inputs, list) or not inputs:
        raise ValueError("inputs must list at least one artifact")
    for item in inputs:
        if not isinstance(item, dict) or not {"role", "uri", "sha256"} <= item.keys():
            raise ValueError("each input needs role, uri, and sha256")
        digest = item["sha256"]
        if not isinstance(digest, str) or len(digest) != 64:
            raise ValueError(f"sha256 must be 64 hex characters, got {digest!r}")
