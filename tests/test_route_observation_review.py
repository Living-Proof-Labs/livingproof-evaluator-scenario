# SPDX-License-Identifier: Apache-2.0
"""Every robot's real route run grades PASS against its own resolved limits (Vera review of #18).

The fixtures in ``sim-v3.2.0-route`` are G1 stock and Go1 playground. These add the
other configurations the robot PRs drive (G1 playground, T1 stock and T1 playground),
recorded with livingproof-sim-mujoco v3.2.0 at the robot PR heads
(``tests/fixtures/sim-v3.2.0-route-review/PROVENANCE.json``). The limits are not typed
in: each run's own manifest supplies the robot width, class and fall height, and the
scenario parameter file resolves them, so T1's tighter route limit is its own.
"""

import json
from pathlib import Path

import pytest
from livingproof_scenario_parameters import resolve

from livingproof_evaluator_scenario.result import write_run

FIXTURES = Path(__file__).parent / "fixtures"
REVIEW = FIXTURES / "sim-v3.2.0-route-review"
WORLD = json.loads((FIXTURES / "sim-v3.2.0-route/world.json").read_text())
PARAMETERS = json.loads((FIXTURES / "sim-v3.2.0-route/parameters.json").read_text())
WHEN = "2026-11-16T12:00:00Z"
RUNS = sorted(p.name for p in REVIEW.iterdir() if (p / "manifest.json").is_file())


def _limits(manifest: dict) -> dict:
    inputs = {
        "route_length": manifest["world"]["route_length"],
        "clear_width": manifest["world"]["clear_width"],
        "robot_width": manifest["robot"]["profile"]["dimensions"]["width"],
        "robot_class": manifest["robot"]["profile"]["class"],
        "fall_base_height": manifest["configuration"]["profile"]["locomotion"]["fall_base_height"],
    }
    resolved = resolve(PARAMETERS, inputs)
    assert resolved["preconditions"] == {"fits_width": True}
    return resolved["limits"]


def test_the_review_set_is_the_three_configurations_not_in_the_pr_fixtures():
    assert RUNS == ["g1-playground", "t1-playground", "t1-stock"]


@pytest.mark.parametrize("run", RUNS)
def test_a_real_route_run_passes_every_check_at_its_own_limits(tmp_path, run):
    manifest_path = REVIEW / run / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    observation = json.loads((REVIEW / run / "trials/trial-01.json").read_text())
    assert observation["format"] == "livingproof-route-observation/0.1.0"
    assert observation["end"] == "crossed_exit"
    limits = _limits(manifest)
    (result,) = write_run(
        manifest_path,
        limits,
        tmp_path / "out",
        started_at=WHEN,
        completed_at=WHEN,
        world=WORLD,
        parameters=PARAMETERS,
    )
    steps = json.loads(result.read_text())["scenario"]["steps"]
    assert [step["id"] for step in steps] == [c["evaluator"] for c in PARAMETERS["checks"]]
    assert {step["id"]: step["verdict"] for step in steps} == {
        c["evaluator"]: "PASS" for c in PARAMETERS["checks"]
    }
    route = next(step for step in steps if step["id"] == "corner-route-limit")
    observed = observation["max_route_distance"]["value"]
    assert route["summary"].startswith(f"route distance {observed:.2f} m <= ")
    assert f"<= {limits['lateral_limit']:.2f} m" in route["summary"]


def test_t1_route_limit_is_its_own_and_a_limit_below_its_distance_fails(tmp_path):
    """T1 is the widest robot: its own limit is tighter than G1's, and 1 cm under its distance fails."""
    manifest_path = REVIEW / "t1-stock" / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    observation = json.loads((REVIEW / "t1-stock" / "trials/trial-01.json").read_text())
    limits = _limits(manifest)
    assert limits["lateral_limit"] < 0.49  # tighter than G1's: T1 is wider
    tight = {**limits, "lateral_limit": observation["max_route_distance"]["value"] - 0.01}
    (result,) = write_run(
        manifest_path,
        tight,
        tmp_path / "out",
        started_at=WHEN,
        completed_at=WHEN,
        world=WORLD,
        parameters=PARAMETERS,
    )
    steps = {s["id"]: s["verdict"] for s in json.loads(result.read_text())["scenario"]["steps"]}
    assert steps["corner-route-limit"] == "FAIL"
    assert [v for k, v in steps.items() if k != "corner-route-limit"] == ["PASS"] * 4
