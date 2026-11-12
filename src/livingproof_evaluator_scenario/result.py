# SPDX-License-Identifier: Apache-2.0
"""One ``livingproof-evaluator-result/1.1.0`` document per trial.

The descriptor is this evaluator's own entry. Findings stay empty in this
slice: a failed trial keeps the assessment sentence on the report, and a
later issue copies failed-step rationales into ``descriptor.findings``.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from livingproof_evaluator_scenario.checks import EVALUATE, EVALUATORS, INSUFFICIENT

# Distribution version declared in pyproject.toml. Semantic-release tags the
# repository and does not rewrite this string.
PACKAGE_VERSION = "0.0.0"
EVALUATOR_ID = "livingproof-scenario"
DISPLAY_NAME = "Scenario evaluator"
SHORT_TITLE = "Scenario eval"
PUBLISHER = "Living Proof Labs"
TIER = "verdict"
PURPOSE = "Checks one trial's hallway steps against its stored observation."
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
EVIDENCE_V2 = "livingproof-hallway-evidence/2.0.0"
_VERDICT = {"PASS": "PASS", "FAIL": "FAIL", INSUFFICIENT: "INCONCLUSIVE"}


def trial_id(configuration: str, index: int) -> str:
    """Result id ``verify`` already assigns: ``{configuration}-seed-{index:02d}``."""
    if not isinstance(index, int) or isinstance(index, bool) or index < 1:
        raise ValueError(f"trial index must be an integer >= 1, got {index!r}")
    if not isinstance(configuration, str) or not configuration:
        raise ValueError("configuration name is missing")
    return f"{configuration}-seed-{index:02d}"


def assess(observation: dict, thresholds: dict, trial_id: str, seed=None) -> list[dict]:
    """The four check records, in ``EVALUATORS`` order."""
    return [EVALUATE[name](observation, thresholds, trial_id, seed) for name in EVALUATORS]


def trial_result(
    observation: dict,
    thresholds: dict,
    trial_id: str,
    *,
    seed=None,
    inputs: list[dict],
    started_at: str,
    completed_at: str,
) -> dict:
    """The result document for one trial. Findings are empty."""
    if not isinstance(trial_id, str) or not trial_id:
        raise ValueError("trial_id is missing")
    _timestamp(started_at, "started_at")
    _timestamp(completed_at, "completed_at")
    _inputs(inputs)
    steps = []
    for item in assess(observation, thresholds, trial_id, seed):
        verdict = _VERDICT.get(item["status"])
        if verdict is None:
            raise ValueError(f"check {item['evaluator']} returned {item['status']!r}")
        steps.append({"id": item["evaluator"], "verdict": verdict, "summary": item["rationale"]})
    return {
        "format": "livingproof-evaluator-result/1.1.0",
        "evaluator": {
            "id": EVALUATOR_ID,
            "version": PACKAGE_VERSION,
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
            "version": PACKAGE_VERSION,
            "tier": TIER,
            "findings": [],
        },
    }


def write_run(
    manifest_path: Path,
    thresholds: dict,
    out_dir: Path,
    *,
    started_at: str,
    completed_at: str,
) -> list[Path]:
    """Write one result file per trial. The file name is the result id."""
    manifest_path = Path(manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("format") != EVIDENCE_V2:
        raise ValueError(
            "this slice reads a livingproof-hallway-evidence/2.0.0 manifest, "
            f"got {manifest.get('format')!r}"
        )
    configuration = manifest["configuration"]["name"]
    manifest_bytes = manifest_path.read_bytes()
    written = []
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    ordered = sorted(manifest["trials"]["results"], key=lambda item: item["index"])
    for trial in ordered:
        index = trial["index"]
        ident = trial_id(configuration, index)
        observation_path = manifest_path.parent / trial["path"]
        observation_bytes = observation_path.read_bytes()
        observation = json.loads(observation_bytes)
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
        )
        path = out_dir / f"{ident}.json"
        path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
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
