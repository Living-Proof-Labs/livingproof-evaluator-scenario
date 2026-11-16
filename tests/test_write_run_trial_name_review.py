# SPDX-License-Identifier: Apache-2.0
"""An ungradable trial is named in write_run's ERROR (Vera review of PR #16, issue #12).

The failing trial is a middle one, so the message must name that trial and not
the last one or the run as a whole. The result id is taken from a good run of
the same fixture, so the test does not depend on how ids are spelled.
"""

import json
import shutil
from pathlib import Path

import pytest

from livingproof_evaluator_scenario.errors import EvaluationError
from livingproof_evaluator_scenario.result import write_run

FIXTURES = Path(__file__).parent / "fixtures" / "run-43159586597"
EXPECTED = json.loads((FIXTURES / "expected.json").read_text(encoding="utf-8"))
THRESHOLDS = EXPECTED["configurations"]["playground"]["thresholds"]
WHEN = "2026-11-12T05:11:41Z"
UNKNOWN = "livingproof-unknown-observation/9.9.9"


def _write(manifest: Path, out: Path):
    return write_run(manifest, THRESHOLDS, out, started_at=WHEN, completed_at=WHEN)


def _result_ids(tmp_path: Path) -> dict:
    """Observation path -> result id, from a good run of the unchanged fixture."""
    written = _write(FIXTURES / "playground" / "manifest.json", tmp_path / "good")
    ids = {}
    for path in written:
        document = json.loads(path.read_text(encoding="utf-8"))
        for item in document["inputs"]:
            if item["role"] == "observation":
                ids[item["uri"]] = path.stem
    return ids


def test_error_names_the_middle_trial_that_failed(tmp_path):
    ids = _result_ids(tmp_path)
    run = tmp_path / "run"
    shutil.copytree(FIXTURES / "playground", run)
    manifest = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
    trials = sorted(manifest["trials"]["results"], key=lambda item: item["index"])
    assert len(trials) >= 3, "the fixture needs a trial before and after the bad one"
    bad, others = trials[1], trials[:1] + trials[2:]
    observation_path = run / bad["path"]
    observation = json.loads(observation_path.read_text(encoding="utf-8"))
    observation["format"] = UNKNOWN
    observation_path.write_text(json.dumps(observation), encoding="utf-8")

    out = tmp_path / "out"
    with pytest.raises(EvaluationError) as raised:
        _write(run / "manifest.json", out)
    error = raised.value
    message = str(error)

    assert error.status == "ERROR"
    assert message.startswith("ERROR: unknown observation format")
    assert UNKNOWN in message
    assert f"(trial {bad['index']}:" in message
    assert bad["path"] in message
    assert ids[bad["path"]] in message
    for other in others:
        assert f"(trial {other['index']}:" not in message
        assert other["path"] not in message
        assert ids[other["path"]] not in message
    assert isinstance(error.__cause__, EvaluationError)
    assert str(error.__cause__).startswith("ERROR: unknown observation format")
    assert not out.exists()
