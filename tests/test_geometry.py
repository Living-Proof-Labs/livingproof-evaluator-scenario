# SPDX-License-Identifier: Apache-2.0
"""Route distance and exit crossing match every route-geometry case.

On the straight route, distance equals |y| and the first crossing is the
sample the stored observation already calls the exit.
"""

import json
from pathlib import Path

from livingproof_evaluator_scenario.checks import (
    first_crossing,
    first_distance_excess,
    trace_crosses,
    trace_distance,
)
from livingproof_evaluator_scenario.compat import straight_route

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "tests/fixtures/robot-capability-specs-v2.2.0"
G1 = ROOT / "tests/fixtures/run-43159586597"
REAL = ROOT / "tests/fixtures/lpv-run-43402628666"


def _cases():
    document = json.loads((CATALOG / "route-geometry-cases.json").read_text(encoding="utf-8"))
    return document["cases"]


def test_route_geometry_cases_have_zero_mismatches():
    distances = crossings = 0
    mismatches = []
    for case in _cases():
        for item in case["distances"]:
            distances += 1
            got = trace_distance(case["route"], item["point"])
            if got != item["distance"]:
                mismatches.append((case["name"], item["name"], got, item["distance"]))
        for item in case["crossings"]:
            crossings += 1
            got = trace_crosses(item["p0"], item["p1"], case["route"], case["exit"])
            if got is not item["crosses"]:
                mismatches.append((case["name"], item["name"], got, item["crosses"]))
    assert distances == 20 and crossings == 30
    assert mismatches == [], f"{len(mismatches)} mismatches"


def test_straight_route_is_the_two_point_geometry_case():
    route, exit_place = straight_route(0.75)
    matched = [case for case in _cases() if case["route"] == route and case["exit"] == exit_place]
    assert len(matched) == 1


def _observations():
    found = list(G1.rglob("trial-*.json"))
    found.extend(REAL.glob("*-trial-01.json"))
    assert len(found) >= 4
    return found


def test_straight_trace_fallback_matches_abs_y_with_zero_mismatches():
    """Distance and the first over-limit sample agree with |y| on every stored trace."""
    route, exit_place = straight_route(0.75)
    sample_mismatches = 0
    time_mismatches = 0
    crossing_mismatches = 0
    seen = 0
    for path in _observations():
        observation = json.loads(path.read_text(encoding="utf-8"))
        samples = observation["trace"]["samples"]
        seen += 1
        for sample in samples:
            if trace_distance(route, sample[1:4]) != abs(sample[2]):
                sample_mismatches += 1
        if "run-43159586597" in path.parts:
            expected = json.loads((G1 / "expected.json").read_text(encoding="utf-8"))
            limit = expected["configurations"][path.parent.parent.name]["thresholds"][
                "lateral_limit"
            ]
        else:
            verification = path.with_name(path.name.replace("-trial-01.json", "-verification.json"))
            limit = json.loads(verification.read_text(encoding="utf-8"))["thresholds"][
                "lateral_limit"
            ]
        by_distance = first_distance_excess(samples, route, limit)
        by_abs = next((sample[0] for sample in samples if abs(sample[2]) > limit), None)
        if by_distance != by_abs:
            time_mismatches += 1
        crossing = first_crossing(samples, route, exit_place)
        crossing_time = None if crossing is None else crossing[0]
        if crossing_time != observation.get("exit_time"):
            crossing_mismatches += 1
    assert seen >= 10
    assert sample_mismatches == 0
    assert time_mismatches == 0
    assert crossing_mismatches == 0
