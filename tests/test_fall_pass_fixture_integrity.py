# SPDX-License-Identifier: Apache-2.0
"""Integrity checks for the fall-PASS fixture that the provenance tests do not make (issue 32).

Each check ties a stored claim to the raw bytes: the observation's minimum base height to the
MCAP's own ``/base_pose`` samples, the binding's recording hash to the MCAP, and the fixture's
limits and observation to the stored verification run's files.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from mcap.reader import make_reader

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "tests" / "fixtures" / "sim-v3.8.1-g1-playground"
LPV = ROOT / "tests" / "fixtures" / "lpv-run-43402628666"


def _json(path: Path):
    return json.loads(path.read_text())


def _base_pose():
    with (FIX / "trial-01.mcap").open("rb") as stream:
        return [
            (m.log_time / 1e9, json.loads(m.data)["pose"]["position"]["z"])
            for _, c, m in make_reader(stream).iter_messages()
            if c.topic == "/base_pose"
        ]


def test_the_observations_minimum_height_is_the_minimum_in_the_raw_recording():
    samples = _base_pose()
    t0 = samples[0][0]
    lowest_time, lowest = min(((t - t0, z) for t, z in samples), key=lambda s: s[1])
    claimed = _json(FIX / "observation-trial-01.json")["min_base_height"]
    assert abs(claimed["value"] - lowest) < 5e-4, (claimed, lowest)
    assert abs(claimed["time"] - lowest_time) < 0.02, (claimed, lowest_time)
    assert round(lowest, 2) == 0.71


def test_the_binding_names_the_recording_by_its_sha256():
    recording = _json(FIX / "trial-01.binding.json")["recording"]
    path = FIX / recording["uri"]
    assert path.is_file()
    assert hashlib.sha256(path.read_bytes()).hexdigest() == recording["sha256"]


def test_the_fixture_observation_is_byte_identical_to_the_stored_verification_run():
    assert (FIX / "observation-trial-01.json").read_bytes() == (
        LPV / "g1-playground-trial-01.json"
    ).read_bytes()


def test_the_limits_in_the_fixture_tests_are_the_stored_verification_runs_thresholds():
    thresholds = _json(LPV / "g1-playground-verification.json")["thresholds"]
    assert thresholds == {
        "time_limit": 27.0,
        "lateral_limit": 0.49,
        "half_width": 0.75,
        "fall_height": 0.5,
    }
    source = _json(FIX / "PROVENANCE.json")["limits_source"]
    assert "43402628666" in source
    assert (LPV / "PROVENANCE.json").is_file()
