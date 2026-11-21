# SPDX-License-Identifier: Apache-2.0
"""A real recording of a robot that stays up: the fall step PASSes from a real MCAP (issue 32).

The MCAP, binding and observation are what livingproof-sim-mujoco v3.8.1 wrote for the Unitree G1
``playground`` configuration walking the stock scenario world (see the fixture's PROVENANCE.json and
generate.py.txt). Nothing in them is hand-written. Earlier real-sim fixtures all fall or touch a
wall, so none showed PASS on the fall step.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

from mcap.reader import make_reader

from livingproof_evaluator_scenario import runner
from livingproof_evaluator_scenario.compat import parameters_document

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "tests" / "fixtures" / "sim-v3.8.1-g1-playground"
WORLD = json.loads((ROOT / "tests/fixtures/sim-1e020b2/world.json").read_text())
# The limits capability-verifier graded this robot's run against (livingproof-verification
# run 43402628666, tests/fixtures/lpv-run-43402628666/g1-playground-verification.json).
THRESHOLDS = {"time_limit": 27.0, "lateral_limit": 0.49, "half_width": 0.75, "fall_height": 0.5}
BY_RULE = {c["fail_when"]: c["evaluator"] for c in parameters_document()["checks"]}
FALL = BY_RULE["less-than-limit"]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _run(**limits):
    return runner.run_trial(
        FIX / "trial-01.mcap", FIX / "trial-01.binding.json", {**THRESHOLDS, **limits}, WORLD
    )


def _verdicts(payload):
    return {step["id"]: step["verdict"] for step in payload["steps"]}


def test_the_fixture_is_the_recording_the_sim_wrote():
    provenance = json.loads((FIX / "PROVENANCE.json").read_text())
    generator = provenance["generator"]
    assert generator["runner"]["tag"] == "v3.8.1" and generator["command"]
    for name, digest in provenance["sha256"].items():
        assert _sha(FIX / name) == digest, name
    # The map covers every fixture file except PROVENANCE.json, which cannot hold its own hash.
    files = {p.name for p in FIX.iterdir()} - {"PROVENANCE.json"}
    assert set(provenance["sha256"]) == files
    assert "PROVENANCE.json" in provenance["sha256_note"]
    assert provenance["world"]["sha256"] == _sha(ROOT / "tests/fixtures/sim-1e020b2/world.json")


def test_the_provenance_names_what_actually_ran_and_the_binding_agrees():
    """The robot ref is the commit that produced the recording, not the lock's nominal pin."""
    provenance = json.loads((FIX / "PROVENANCE.json").read_text())
    robot, runner_pin = provenance["generator"]["robot"], provenance["generator"]["runner"]
    assert (robot["ref"], robot["commit"][:7]) == ("main", "0612df1")
    assert (runner_pin["tag"], runner_pin["commit"][:7]) == ("v3.8.1", "2ed053f")
    binding = json.loads((FIX / "trial-01.binding.json").read_text())
    nominal = binding["observables"]["base_height"]["nominal"]["ref"]
    assert f"{robot['repository'].split('/')[-1]}@{robot['commit']}:" in nominal
    assert "43402628666" in provenance["limits_source"]


def test_the_locks_nominal_pin_is_labelled_as_not_having_produced_the_recording():
    provenance = json.loads((FIX / "PROVENANCE.json").read_text())
    nominal = provenance["generator"]["lock_nominal_pins"]
    assert nominal["robot_ref"] == "v2.3.12" and "did NOT produce" in nominal["note"]
    assert provenance["generator"]["robot"]["commit"] != nominal["robot_commit"]
    readme = " ".join((FIX / "README.md").read_text().split())
    assert "0612df1" in readme and "2ed053f" in readme and "43402628666" in readme
    for token in ("v2.3.12", "v3.6.2"):
        assert token in readme and token in (FIX / "generate.py.txt").read_text()
    assert "nominal pins only" in readme and "did not produce this recording" in readme
    assert provenance["generator"]["robot"]["commit"][:7] in readme
    for text in (readme, (FIX / "generate.py.txt").read_text()):
        assert "nominal" in text


def test_the_observation_hash_is_the_one_verification_graded():
    """The sim's observation for this trial is byte-identical to the stored lpv run's."""
    provenance = json.loads((FIX / "PROVENANCE.json").read_text())
    assert provenance["observation_sha256"] == _sha(FIX / "observation-trial-01.json")
    assert provenance["observation_sha256"].startswith("48b6078f")


def test_every_step_passes_including_the_fall_step_on_a_real_recording():
    payload = _run()
    assert set(_verdicts(payload).values()) == {"PASS"}
    assert FALL in _verdicts(payload)


def test_the_robot_really_stayed_up_and_never_touched_a_wall():
    observation = json.loads((FIX / "observation-trial-01.json").read_text())
    assert observation["end"] == "crossed_exit" and observation["wall_contacts"] == []
    assert observation["min_base_height"]["value"] >= THRESHOLDS["fall_height"]
    with (FIX / "trial-01.mcap").open("rb") as stream:
        heights = [
            json.loads(m.data)["pose"]["position"]["z"]
            for _, c, m in make_reader(stream).iter_messages()
            if c.topic == "/base_pose"
        ]
    assert len(heights) > 100 and min(heights) >= THRESHOLDS["fall_height"]


def test_only_the_fall_step_flips_when_its_limit_is_raised_above_the_real_height():
    """The PASS is real: the same recording FAILs the fall step against a taller limit."""
    verdicts = _verdicts(_run(fall_height=0.8))
    assert verdicts[FALL] == "FAIL"
    assert {v for k, v in verdicts.items() if k != FALL} == {"PASS"}


def test_the_limits_source_names_the_files_that_hold_the_limits():
    source = json.loads((FIX / "PROVENANCE.json").read_text())["limits_source"]
    assert source["run"] == 43402628666
    stored = ROOT / source["stored_file"]
    assert stored.name == "g1-playground-verification.json" and stored.is_file()
    assert json.loads(stored.read_text())["thresholds"] == THRESHOLDS
    # run-manifest.json is in the run's evidence artifact, not stored here; it is named, not read.
    assert source["artifact_file"].endswith("run-manifest.json")


def test_the_lock_that_drove_the_run_is_pinned_by_commit_and_sha256():
    lock = json.loads((FIX / "PROVENANCE.json").read_text())["generator"]["lock_nominal_pins"][
        "lock"
    ]
    assert lock["repository"] == "Living-Proof-Labs/livingproof-verification"
    assert re.fullmatch(r"[0-9a-f]{40}", lock["commit"])
    assert re.fullmatch(r"[0-9a-f]{64}", lock["sha256"])
    assert lock["path"].endswith("unitree-g1-playground-mujoco-hallway.lock.json")
    text = (FIX / "generate.py.txt").read_text()
    assert lock["commit"] in text and lock["sha256"] in text


def test_the_regeneration_notes_say_to_clone_without_dot_git():
    """The binding's nominal ref carries the remote URL, so a .git suffix changes its bytes."""
    text = " ".join((FIX / "generate.py.txt").read_text().split())
    assert "without .git" in text
    ref = json.loads((FIX / "trial-01.binding.json").read_text())["observables"]["base_height"][
        "nominal"
    ]["ref"]
    assert ".git@" not in ref and ref.startswith("https://github.com/")
