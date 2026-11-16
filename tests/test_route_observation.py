# SPDX-License-Identifier: Apache-2.0
"""Grading livingproof-route-observation/0.1.0 (robot-capability-specs#40, step 11c).

livingproof-sim-mujoco v3.2.0 records an adapter-driven trial in the route format:
``max_route_distance`` instead of ``max_abs_lateral``, ``left_world`` instead of the
frozen departure field, and the places entered. The fixtures are real v3.2.0 runs
(``tests/fixtures/sim-v3.2.0-route/PROVENANCE.json``). A robot that does not declare
the scenario records no trial, so nothing is graded and nothing is an ERROR: the
UNSUPPORTED result passes through to the verifier.
"""

import copy
import json
from pathlib import Path

import pytest

from livingproof_evaluator_scenario.checks import FAIL, PASS, assess
from livingproof_evaluator_scenario.errors import EvaluationError
from livingproof_evaluator_scenario.result import write_run

FIXTURES = Path(__file__).parent / "fixtures/sim-v3.2.0-route"
WORLD = json.loads((FIXTURES / "world.json").read_text())
PARAMETERS = json.loads((FIXTURES / "parameters.json").read_text())
WHEN = "2026-11-16T12:00:00Z"
ROUTE_FORMAT = "livingproof-route-observation/0.1.0"
# Resolved walk-corner 0.1.0 limits: route length 5.5 m at 0.5 m/s gives 27 s; lateral is
# clear_width / 2 - robot width / 2 (G1 0.52 m, Go1 0.282 m); exit segment 0.75 m.
LIMITS = {
    "g1-stock": {
        "time_limit": 27.0,
        "lateral_limit": 0.49,
        "exit_segment": 0.75,
        "fall_height": 0.5,
    },
    "go1-playground": {
        "time_limit": 27.0,
        "lateral_limit": 0.609,
        "exit_segment": 0.75,
        "fall_height": 0.18,
    },
}
EVALUATORS = [check["evaluator"] for check in PARAMETERS["checks"]]


def _trial(run: str) -> dict:
    return json.loads((FIXTURES / run / "trials/trial-01.json").read_text())


def _grade(observation: dict, run: str = "g1-stock", **limits) -> dict:
    thresholds = {**LIMITS[run], **limits}
    items = assess(
        observation, thresholds, "trial-01", ("trial", 1), world=WORLD, parameters=PARAMETERS
    )
    return {item["evaluator"]: item for item in items}


@pytest.mark.parametrize("run", sorted(LIMITS))
def test_a_real_route_trial_passes_every_check(run):
    observation = _trial(run)
    assert observation["format"] == ROUTE_FORMAT
    graded = _grade(observation, run)
    assert list(graded) == EVALUATORS
    assert {name: item["status"] for name, item in graded.items()} == dict.fromkeys(
        EVALUATORS, PASS
    )


def test_route_distance_is_read_from_max_route_distance():
    observation = _trial("g1-stock")
    item = next(i for i in _grade(observation).values() if i["evaluator"] == "corner-route-limit")
    assert item["details"]["observed"] == observation["max_route_distance"]["value"]
    assert "route" in item["rationale"]


def test_route_distance_over_the_limit_fails():
    observation = _trial("g1-stock")
    item = _grade(observation, lateral_limit=0.1)["corner-route-limit"]
    assert item["status"] == FAIL
    assert item["details"]["failures"][0]["check"] == "corner-route-limit"


def test_leaving_the_world_fails_the_exit_check_with_the_wall():
    observation = copy.deepcopy(_trial("g1-stock"))
    observation["end"] = "left_world"
    observation["exit_time"] = None
    observation["left_world"] = {"time": 6.5, "via": "wall-outer-second", "x": 0.8, "y": 0.4}
    samples = observation["trace"]["samples"]
    observation["trace"]["samples"] = [s for s in samples if s[0] <= 6.5]
    item = _grade(observation)["corner-exit-reached"]
    assert item["status"] == FAIL
    assert item["rationale"] == "left the world via wall-outer-second at 6.50 s (trial 1)"


def test_a_malformed_left_world_record_is_insufficient_evidence():
    observation = copy.deepcopy(_trial("g1-stock"))
    observation["end"] = "left_world"
    observation["exit_time"] = None
    observation["left_world"] = None
    assert _grade(observation)["corner-exit-reached"]["status"] == "INSUFFICIENT_EVIDENCE"


def test_missing_the_through_place_fails_passes_through_places():
    observation = copy.deepcopy(_trial("g1-stock"))
    region = next(p for p in WORLD["places"] if p["name"] == "corner")
    observation["trace"]["samples"] = [
        s
        for s in observation["trace"]["samples"]
        if not (
            region["x"][0] <= s[1] <= region["x"][1] and region["y"][0] <= s[2] <= region["y"][1]
        )
    ]
    assert _grade(observation)["corner-turned"]["status"] == FAIL


def test_write_run_grades_a_route_run(tmp_path):
    written = write_run(
        FIXTURES / "g1-stock/manifest.json",
        LIMITS["g1-stock"],
        tmp_path / "out",
        started_at=WHEN,
        completed_at=WHEN,
        world=WORLD,
        parameters=PARAMETERS,
    )
    (result,) = written
    document = json.loads(result.read_text())
    assert [step["verdict"] for step in document["scenario"]["steps"]] == ["PASS"] * 5


def test_an_unsupported_run_writes_no_result_and_is_not_an_error(tmp_path):
    manifest = json.loads((FIXTURES / "unsupported/manifest.json").read_text())
    assert manifest["trials"]["results"] == []
    assert manifest["preconditions"] == [
        {
            "name": "scenario_supported",
            "met": False,
            "detail": "walk-corner is not named by the robot manifest scenarios",
        }
    ]
    written = write_run(
        FIXTURES / "unsupported/manifest.json",
        LIMITS["g1-stock"],
        tmp_path / "out",
        started_at=WHEN,
        completed_at=WHEN,
        world=WORLD,
        parameters=PARAMETERS,
    )
    assert written == []


def test_an_unknown_format_error_names_the_route_format_as_known():
    with pytest.raises(EvaluationError) as caught:
        _grade({"format": "livingproof-observation/9.9.9", "end": "time_limit", "exit_time": None})
    assert ROUTE_FORMAT in str(caught.value)
