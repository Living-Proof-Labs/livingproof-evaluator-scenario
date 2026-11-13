# SPDX-License-Identifier: Apache-2.0
"""One test per fail_when rule, plus a second scenario on a bent route.

The route, the exit and the distances are the three-point case in
route-geometry-cases.json. The parameter file's checks are replaced in memory
so this scenario is not the frozen one.
"""

import json
from pathlib import Path

from livingproof_evaluator_scenario.checks import PASS, assess, trace_crosses
from livingproof_evaluator_scenario.compat import frozen_observation_format, straight_route

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "tests/fixtures/robot-capability-specs-v2.2.0"
THRESHOLDS = {"time_limit": 10.0, "lateral_limit": 0.5, "half_width": 0.75, "fall_height": 0.5}
CORNER = {"name": "corner", "type": "region", "x": [-0.4, 0.4], "y": [-0.4, 0.4]}
WEST = {"name": "west", "type": "region", "x": [-2.2, -1.8], "y": [-0.2, 0.2]}


def _case():
    cases = json.loads((CATALOG / "route-geometry-cases.json").read_text(encoding="utf-8"))["cases"]
    return next(case for case in cases if len(case["route"]) == 3)


def _parameters(checks, through):
    document = json.loads((CATALOG / "parameters.json").read_text(encoding="utf-8"))
    document["checks"] = checks
    document["places"]["route"] = "route-centreline"
    document["places"]["exit"] = "exit"
    document["places"]["through"] = through
    return document


def _world(case, places):
    return {
        "places": [
            {"name": "route-centreline", "type": "polyline", "points": case["route"]},
            {
                "name": "exit",
                "type": "segment",
                "points": case["exit"]["points"],
                "reference": case["exit"]["reference"],
            },
            *places,
        ]
    }


def _sample(time, point, z=0.8):
    return [time, point[0], point[1], z]


def _observation(samples, **fields):
    observation = {
        "format": frozen_observation_format(),
        "end": "crossed_exit",
        "exit_time": samples[-1][0],
        "duration_s": samples[-1][0],
        "max_abs_lateral": {"value": 0.0, "time": samples[0][0]},
        "min_base_height": {"value": 0.8, "time": samples[0][0]},
        "wall_contacts": [],
        "trace": {"samples": samples},
    }
    observation.update(fields)
    return observation


def _grade(checks, observation, world, through=()):
    got = assess(
        observation,
        THRESHOLDS,
        "bend-seed-01",
        ("trial", 1),
        world=world,
        parameters=_parameters(checks, list(through)),
    )
    assert len(got) == len(checks)
    return got[0] if len(got) == 1 else got


def _inside_crossing(case):
    return next(
        item
        for item in case["crossings"]
        if item["crosses"] and item["p0"] == [0, 2, 0] and item["p1"] == [0, 4, 0]
    )


def test_fail_when_absent_or_greater_than_limit():
    case = _case()
    check = {
        "evaluator": "exit-reached",
        "measure": "exit-crossing-time",
        "fail_when": "absent-or-greater-than-limit",
        "limit": "time_limit",
    }
    world = _world(case, [CORNER])
    crossing = _inside_crossing(case)
    reached = _grade(
        [check],
        _observation(
            [_sample(1.0, [0, 0]), _sample(2.0, crossing["p0"]), _sample(3.0, crossing["p1"])]
        ),
        world,
    )
    assert reached["status"] == PASS
    assert reached["details"]["observed"] == 3.0

    late = _grade(
        [check],
        _observation(
            [_sample(11.0, crossing["p0"]), _sample(12.0, crossing["p1"])],
            exit_time=12.0,
            duration_s=12.0,
        ),
        world,
    )
    assert late["status"] == "FAIL"
    assert late["details"]["observed"] == 12.0

    absent = _grade(
        [check],
        _observation(
            [_sample(1.0, [0, 1]), _sample(2.0, [0, 2])],
            end="time_limit",
            exit_time=None,
            duration_s=10.0,
        ),
        world,
    )
    assert absent["status"] == "FAIL"
    assert absent["details"]["observed"] is None

    outside = next(
        item for item in case["crossings"] if item["p0"] == [1, 2, 0] and item["p1"] == [1, 4, 0]
    )
    assert outside["crosses"] is False
    rejected = _grade(
        [check],
        _observation([_sample(1.0, outside["p0"]), _sample(2.0, outside["p1"])]),
        world,
    )
    assert rejected["status"] == "FAIL"
    assert rejected["details"]["failures"][0]["via"] == "exit-outside-segment"


def test_fail_when_greater_than_limit():
    case = _case()
    check = {
        "evaluator": "on-route",
        "measure": "max-distance-from-route",
        "fail_when": "greater-than-limit",
        "limit": "lateral_limit",
    }
    world = _world(case, [])
    far = next(
        item for item in case["distances"] if item["point"][0] == 1 and item["point"][1] == 0
    )
    assert far["distance"] > THRESHOLDS["lateral_limit"]
    # The far point has y = 0, so |y| is not over the limit. A later point on the
    # route has |y| over the limit and distance 0. The failure time has to be the far point.
    samples = [
        _sample(0.0, [-2, 0]),
        _sample(0.5, far["point"]),
        _sample(2.0, [0, 0.8]),
        _sample(3.0, [0, 4]),
    ]
    failed = _grade(
        [check],
        _observation(samples, max_abs_lateral={"value": far["distance"], "time": 0.5}),
        world,
    )
    assert failed["status"] == "FAIL"
    assert failed["details"]["observed"] == far["distance"]
    assert failed["details"]["time"] == 0.5

    passed = _grade(
        [check],
        _observation([_sample(0.0, [-2, 0]), _sample(1.0, [0, 2])]),
        world,
    )
    assert passed["status"] == PASS
    assert passed["details"]["observed"] == 0.0


def test_fail_when_not_empty():
    case = _case()
    check = {"evaluator": "walls", "measure": "wall-contacts", "fail_when": "not-empty"}
    world = _world(case, [])
    samples = [_sample(0.0, [-2, 0]), _sample(1.0, [0, 2])]
    empty = _grade([check], _observation(samples), world)
    assert empty["status"] == PASS
    assert empty["details"]["observed"] == 0
    contact = _grade(
        [check],
        _observation(samples, wall_contacts=[{"start": 1.25, "depth": 0.02, "wall": "wall-a"}]),
        world,
    )
    assert contact["status"] == "FAIL"
    assert contact["details"]["observed"] == 1
    assert contact["details"]["time"] == 1.25


def test_fail_when_less_than_limit():
    case = _case()
    check = {
        "evaluator": "upright",
        "measure": "min-base-height",
        "fail_when": "less-than-limit",
        "limit": "fall_height",
    }
    world = _world(case, [])
    samples = [_sample(0.0, [-2, 0])]
    upright = _grade([check], _observation(samples), world)
    assert upright["status"] == PASS
    assert upright["details"]["observed"] == 0.8
    fallen = _grade(
        [check],
        _observation(samples, min_base_height={"value": 0.2, "time": 0.0}),
        world,
    )
    assert fallen["status"] == "FAIL"
    assert fallen["details"]["observed"] == 0.2


def test_fail_when_not_in_order():
    case = _case()
    check = {
        "evaluator": "through-place",
        "measure": "passes-through-places",
        "fail_when": "not-in-order",
    }
    crossing = _inside_crossing(case)
    world = _world(case, [WEST, CORNER])
    in_order = [
        _sample(0.5, [-2, 0]),
        _sample(1.5, [0, 0]),
        _sample(2.0, crossing["p0"]),
        _sample(3.0, crossing["p1"]),
    ]
    passed = _grade([check], _observation(in_order), world, through=["west", "corner"])
    assert passed["status"] == PASS
    assert [item["place"] for item in passed["details"]["observed"]] == ["west", "corner"]

    missed = [
        _sample(0.0, [-2, 1]),
        _sample(2.0, crossing["p0"]),
        _sample(3.0, crossing["p1"]),
    ]
    never = _grade([check], _observation(missed), world, through=["corner"])
    assert never["status"] == "FAIL"
    assert never["details"]["failures"][0]["place"] == "corner"

    swapped = [
        _sample(0.5, [0, 0]),
        _sample(1.5, [-2, 0]),
        _sample(2.0, crossing["p0"]),
        _sample(3.0, crossing["p1"]),
    ]
    out_of_order = _grade([check], _observation(swapped), world, through=["west", "corner"])
    assert out_of_order["status"] == "FAIL"


def test_a_bent_route_is_graded_without_the_straight_exit():
    """The same five rules on the bent route. The straight exit would not count this crossing."""
    case = _case()
    crossing = _inside_crossing(case)
    route, exit_place = straight_route(0.75)
    assert trace_crosses(crossing["p0"], crossing["p1"], route, exit_place) is False
    checks = [
        {
            "evaluator": "exit-reached",
            "measure": "exit-crossing-time",
            "fail_when": "absent-or-greater-than-limit",
            "limit": "time_limit",
        },
        {
            "evaluator": "on-route",
            "measure": "max-distance-from-route",
            "fail_when": "greater-than-limit",
            "limit": "lateral_limit",
        },
        {"evaluator": "walls", "measure": "wall-contacts", "fail_when": "not-empty"},
        {
            "evaluator": "upright",
            "measure": "min-base-height",
            "fail_when": "less-than-limit",
            "limit": "fall_height",
        },
        {
            "evaluator": "through-place",
            "measure": "passes-through-places",
            "fail_when": "not-in-order",
        },
    ]
    samples = [
        _sample(0.0, [-2, 0]),
        _sample(1.0, [0, 0]),
        _sample(2.0, crossing["p0"]),
        _sample(3.0, crossing["p1"]),
    ]
    got = _grade(checks, _observation(samples), _world(case, [CORNER]), through=["corner"])
    assert [item["status"] for item in got] == [PASS] * 5
    assert got[0]["details"]["observed"] == 3.0
    assert got[-1]["details"]["observed"][0]["place"] == "corner"
