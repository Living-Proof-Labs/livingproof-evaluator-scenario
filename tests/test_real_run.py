# SPDX-License-Identifier: Apache-2.0
"""Parity with capability-verifier v1.18.5 output from livingproof-verification run 43402628666.

One trial per definition. The three trials in each evidence artifact are byte-identical.
Digests are in PROVENANCE.json, copied from that run's MANIFEST.json.
"""

import hashlib
import json
from pathlib import Path

import pytest

from livingproof_evaluator_scenario.checks import assess
from livingproof_evaluator_scenario.result import grade_trial, trial_result

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests/fixtures/lpv-run-43402628666"
PROVENANCE = json.loads((FIXTURES / "PROVENANCE.json").read_text(encoding="utf-8"))
WHEN = "2026-11-13T00:00:00Z"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _definition(definition_id):
    return next(item for item in PROVENANCE["definitions"] if item["id"] == definition_id)


@pytest.mark.parametrize("definition_id", [item["id"] for item in PROVENANCE["definitions"]])
def test_real_run_parity(definition_id):
    assert PROVENANCE["run_id"] == 43402628666
    item = _definition(definition_id)
    assert item["trials_identical"] is True
    assert item["trial_count"] == 3
    files = item["files"]
    for record in files.values():
        assert _sha(FIXTURES / record["file"]) == record["file_sha256"]
        assert record["artifact_digest"].startswith("sha256:")
    observation = json.loads((FIXTURES / files["observation"]["file"]).read_text(encoding="utf-8"))
    stored_result = json.loads((FIXTURES / files["result"]["file"]).read_text(encoding="utf-8"))
    verification = json.loads(
        (FIXTURES / files["verification"]["file"]).read_text(encoding="utf-8")
    )
    trial = verification["trials"][0]
    got = assess(
        observation,
        verification["thresholds"],
        trial["id"],
        ("trial", trial["index"]),
    )
    assert got == trial["assessments"]
    document = trial_result(
        observation,
        verification["thresholds"],
        trial["id"],
        seed=("trial", trial["index"]),
        inputs=[{"role": "observation", "uri": "trials/trial-01.json", "sha256": "ab" * 32}],
        started_at=WHEN,
        completed_at=WHEN,
    )
    stored_steps = stored_result["scenario"]["steps"]
    assert document["scenario"]["steps"] == [
        {"id": step["id"], "verdict": step["verdict"], "summary": step["summary"]}
        for step in stored_steps
    ]
    for produced, stored in zip(got, stored_steps, strict=True):
        assert produced["details"]["observed"] == next(
            assessment["details"]["observed"]
            for assessment in trial["assessments"]
            if assessment["evaluator"] == stored["id"]
        )
        assert stored["verdict"] == {"PASS": "PASS", "FAIL": "FAIL"}[produced["status"]]
    grade = grade_trial(document["scenario"]["steps"])
    assert [entry["status"] for entry in verification["trials"]] == [grade] * 3
    assert verification["summary"]["grade"] == grade
