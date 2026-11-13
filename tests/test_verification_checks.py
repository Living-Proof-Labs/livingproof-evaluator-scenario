# SPDX-License-Identifier: Apache-2.0
"""Verification hand checks for PR 11, kept as tests.

Checks come only from the parameter file, a malformed check is an ERROR, the
evaluator applies the exit sample rule (not the meeting point) on the frozen
route, the frozen route is (-3, 0) to (3, 0), and format handling stays strict.
"""

import copy
import json

import pytest

from livingproof_evaluator_scenario.checks import EVALUATORS, INSUFFICIENT, PASS, assess
from livingproof_evaluator_scenario.compat import (
    frozen_observation_format,
    parameters_document,
    straight_route,
)
from livingproof_evaluator_scenario.compat.recorded import OBSERVATION_ENDS
from livingproof_evaluator_scenario.errors import EvaluationError
from livingproof_evaluator_scenario.result import write_run

THRESHOLDS = {"time_limit": 27.0, "lateral_limit": 0.49, "half_width": 0.75, "fall_height": 0.5}
WHEN = "2026-11-13T00:00:00Z"


def _observation(samples, **fields):
    observation = {
        "format": frozen_observation_format(),
        "end": "crossed_exit",
        "exit_time": samples[-1][0],
        "duration_s": samples[-1][0],
        "max_abs_lateral": {"value": 0.1, "time": 0.0},
        "min_base_height": {"value": 0.7, "time": 0.0},
        "wall_contacts": [],
        "trace": {"samples": samples},
    }
    observation.update(fields)
    return observation


def _walk(p0, p1):
    return _observation([[0.0, 0.0, 0.0, 0.7], [10.0, *p0, 0.7], [10.5, *p1, 0.7]])


def test_the_frozen_scenario_grades_exactly_its_four_checks():
    document = parameters_document()
    assert len(document["checks"]) == 4
    assert EVALUATORS == tuple(check["evaluator"] for check in document["checks"])
    # passes-through-places is implemented but the frozen scenario does not use it.
    assert document["places"]["through"] == []
    assert all(check["fail_when"] != "not-in-order" for check in document["checks"])
    got = assess(_walk((2.9, 0.0), (3.1, 0.0)), THRESHOLDS, "t", ("trial", 1))
    assert [item["evaluator"] for item in got] == list(EVALUATORS)


@pytest.mark.parametrize(
    "check",
    [
        {"evaluator": "x", "measure": "min-base-height", "fail_when": "less-than-or-equal"},
        {"evaluator": "x", "measure": "min-base-height"},
        {"evaluator": "x", "measure": "wall-contacts", "fail_when": "greater-than-limit"},
        {"evaluator": "x", "measure": "min-base-height", "fail_when": "less-than-limit"},
        {
            "evaluator": "x",
            "measure": "min-base-height",
            "fail_when": "less-than-limit",
            "limit": "no_such_limit",
        },
    ],
    ids=["unknown-fail-when", "no-fail-when", "wrong-measure", "no-limit", "unknown-limit"],
)
def test_a_malformed_check_is_an_error_not_skipped(check):
    document = copy.deepcopy(parameters_document())
    document["checks"].append(check)
    with pytest.raises(EvaluationError) as caught:
        assess(_walk((2.9, 0.0), (3.1, 0.0)), THRESHOLDS, "t", ("trial", 1), parameters=document)
    assert caught.value.status == "ERROR"


def test_missing_exit_segment_threshold_is_an_error():
    thresholds = {k: v for k, v in THRESHOLDS.items() if k != "half_width"}
    with pytest.raises(EvaluationError) as caught:
        assess(_walk((2.9, 0.0), (3.1, 0.0)), thresholds, "t", ("trial", 1))
    assert "half_width" in str(caught.value)


def test_the_frozen_route_is_the_straight_centreline():
    route, exit_place = straight_route(0.75)
    assert route == [[-3, 0, 0], [3, 0, 0]]
    assert exit_place == {"points": [[3, -0.75, 0], [3, 0.75, 0]], "reference": [3, 0, 0]}


# (p0, p1, sample-rule result). The first and last disagree with the meeting point.
COUNTER_EXAMPLES = [
    ((2.9, 0.7), (3.5, 0.95), False),
    ((2.8, 0.9), (3.2, 0.7), True),
    ((2.996, 0.7525), (3.006, 0.7495), True),
    ((2.996, 0.7475), (3.006, 0.7505), False),
]


@pytest.mark.parametrize("p0,p1,crosses", COUNTER_EXAMPLES)
def test_the_evaluator_uses_the_sample_rule_not_the_meeting_point(p0, p1, crosses):
    got = assess(_walk(p0, p1), THRESHOLDS, "t", ("trial", 1))[0]
    if crosses:
        assert got["status"] == PASS
        assert got["details"]["observed"] == 10.5
    else:
        assert got["status"] == "FAIL"
        assert got["details"]["failures"][0]["via"] == "exit-outside-segment"


def test_a_step_starting_on_the_exit_line_does_not_count():
    got = assess(_walk((3.0, 0.0), (3.2, 0.0)), THRESHOLDS, "t", ("trial", 1))[0]
    assert got["status"] != PASS


def test_the_older_observation_format_stays_readable():
    frozen = frozen_observation_format()
    (older,) = [fmt for fmt in OBSERVATION_ENDS if fmt != frozen]
    assert older.endswith("/1.0.0")
    observation = _walk((2.9, 0.0), (3.1, 0.0))
    observation["format"] = older
    got = assess(observation, THRESHOLDS, "t", 1)
    assert [item["status"] for item in got] == [PASS] * 4
    # The early-departure end exists only in the frozen format. An older record
    # that claims it cannot be graded.
    (departure,) = OBSERVATION_ENDS[frozen] - OBSERVATION_ENDS[older]
    observation.update(end=departure, exit_time=None)
    observation[departure] = {"time": 3.0, "via": "w"}
    assert assess(observation, THRESHOLDS, "t", 1)[0]["status"] == INSUFFICIENT


def test_an_unknown_evidence_format_writes_nothing(tmp_path):
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"format": "livingproof-evidence/9.9.9"}), encoding="utf-8")
    out = tmp_path / "out"
    with pytest.raises(EvaluationError):
        write_run(manifest, THRESHOLDS, out, started_at=WHEN, completed_at=WHEN)
    assert not out.exists()
