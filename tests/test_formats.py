# SPDX-License-Identifier: Apache-2.0
"""Unknown input formats are a test-system ERROR. A missing format is not one."""

import json

import pytest

from livingproof_evaluator_scenario.checks import INSUFFICIENT, assess
from livingproof_evaluator_scenario.errors import EvaluationError
from livingproof_evaluator_scenario.result import trial_result, write_run

WHEN = "2026-11-13T00:00:00Z"
THRESHOLDS = {"time_limit": 27.0, "lateral_limit": 0.49, "half_width": 0.75, "fall_height": 0.5}


def test_unknown_evidence_format_is_an_error(tmp_path):
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"format": "livingproof-evidence/9.9.9"}), encoding="utf-8")
    with pytest.raises(EvaluationError) as caught:
        write_run(manifest, THRESHOLDS, tmp_path / "out", started_at=WHEN, completed_at=WHEN)
    assert caught.value.status == "ERROR"
    message = str(caught.value)
    assert message.startswith("ERROR:")
    assert "livingproof-evidence/9.9.9" in message
    assert "Example:" in message


def test_unknown_observation_format_is_an_error():
    with pytest.raises(EvaluationError) as caught:
        assess(
            {"format": "livingproof-observation/9.9.9", "end": "time_limit", "exit_time": None},
            THRESHOLDS,
            "trial-01",
            ("trial", 1),
        )
    assert caught.value.status == "ERROR"
    assert str(caught.value).startswith("ERROR:")
    assert "livingproof-observation/9.9.9" in str(caught.value)


def test_a_missing_observation_format_stays_insufficient_evidence():
    document = trial_result(
        {},
        THRESHOLDS,
        "trial-01",
        seed=("trial", 1),
        inputs=[{"role": "observation", "uri": "trials/trial-01.json", "sha256": "ab" * 32}],
        started_at=WHEN,
        completed_at=WHEN,
    )
    assert [step["verdict"] for step in document["scenario"]["steps"]] == ["INCONCLUSIVE"] * 4
    assert INSUFFICIENT == "INSUFFICIENT_EVIDENCE"


def test_the_command_prints_the_error(tmp_path, capsys):
    from livingproof_evaluator_scenario.__main__ import main

    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"format": "not-a-format"}), encoding="utf-8")
    thresholds = tmp_path / "thresholds.json"
    thresholds.write_text(json.dumps(THRESHOLDS), encoding="utf-8")
    code = main(
        [
            str(manifest),
            "--thresholds",
            str(thresholds),
            "--out",
            str(tmp_path / "out"),
            "--started-at",
            WHEN,
            "--completed-at",
            WHEN,
        ]
    )
    assert code == 1
    captured = capsys.readouterr()
    assert captured.err.startswith("ERROR:")
    assert "not-a-format" in captured.err
