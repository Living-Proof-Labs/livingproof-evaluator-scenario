# SPDX-License-Identifier: Apache-2.0
"""write_run checks every trial before it writes anything (issue #12).

A run whose last trial has an unknown observation format stops with ERROR and
leaves no output folder, and an existing folder is left as it was.
"""

import json
import shutil
from pathlib import Path

import pytest

from livingproof_evaluator_scenario.compat.recorded import EvaluationError
from livingproof_evaluator_scenario.result import write_run

FIXTURES = Path(__file__).parent / "fixtures" / "run-43159586597"
EXPECTED = json.loads((FIXTURES / "expected.json").read_text(encoding="utf-8"))
WHEN = "2026-11-12T05:11:41Z"


def _run_with_bad_last_trial(tmp_path: Path) -> Path:
    run = tmp_path / "run"
    shutil.copytree(FIXTURES / "playground", run)
    manifest = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
    last = max(manifest["trials"]["results"], key=lambda item: item["index"])
    path = run / last["path"]
    observation = json.loads(path.read_text(encoding="utf-8"))
    observation["format"] = "livingproof-unknown-observation/9.9.9"
    path.write_text(json.dumps(observation), encoding="utf-8")
    return run / "manifest.json"


def _write(manifest: Path, out: Path):
    thresholds = EXPECTED["configurations"]["playground"]["thresholds"]
    return write_run(manifest, thresholds, out, started_at=WHEN, completed_at=WHEN)


def test_unknown_format_in_the_last_trial_leaves_no_output_folder(tmp_path):
    manifest = _run_with_bad_last_trial(tmp_path)
    out = tmp_path / "out"
    with pytest.raises(EvaluationError, match="unknown observation format"):
        _write(manifest, out)
    assert not out.exists()


def test_unknown_format_leaves_an_existing_folder_unchanged(tmp_path):
    manifest = _run_with_bad_last_trial(tmp_path)
    out = tmp_path / "out"
    out.mkdir()
    (out / "keep.txt").write_text("kept", encoding="utf-8")
    with pytest.raises(EvaluationError, match="unknown observation format"):
        _write(manifest, out)
    assert sorted(p.name for p in out.iterdir()) == ["keep.txt"]


def test_a_good_run_still_writes_every_trial_and_the_thresholds(tmp_path):
    out = tmp_path / "out"
    written = _write(FIXTURES / "playground" / "manifest.json", out)
    names = sorted(p.name for p in out.iterdir())
    assert names == sorted([p.name for p in written] + ["thresholds.json"])


def test_unknown_format_error_names_the_trial(tmp_path):
    """The ERROR says which trial failed: index, observation path and result id (PR #16 review)."""
    manifest = _run_with_bad_last_trial(tmp_path)
    data = json.loads(manifest.read_text(encoding="utf-8"))
    last = max(data["trials"]["results"], key=lambda item: item["index"])
    with pytest.raises(EvaluationError) as raised:
        _write(manifest, tmp_path / "out")
    message = str(raised.value)
    assert message.startswith("ERROR: unknown observation format")
    assert f"(trial {last['index']}" in message
    assert last["path"] in message
