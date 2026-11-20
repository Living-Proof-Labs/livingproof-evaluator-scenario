# SPDX-License-Identifier: Apache-2.0
"""Parity of the media path and the trial path on corner-turned, and of the thresholds citation.

For one recording, ``runner.run_trial`` (the media path's grader) and ``checks.assess`` (the trial
path) must give the same corner-turned verdict: PASS, FAIL and INCONCLUSIVE. The citation digest
on the media path equals the trial path's for the same parameter document, taken from the real
``result.canonical_json``, not a copy of it.
"""

from __future__ import annotations

import copy
import hashlib
import json

import pytest

from livingproof_evaluator_scenario import checks, media, result, runner
from test_media_corner import (
    AROUND,
    PARAMETERS,
    THROUGH,
    TURNED,
    WORLD,
    _grade,
    _recording,
)
from test_media_run import MANIFEST

LIMITS = {"time_limit": 27.0, "lateral_limit": 0.49, "half_width": 0.75, "fall_height": 0.5}
LATE = [(-2.5, 0.0), (-2.5, 3.2), (0.0, 3.2), (0.0, 0.0)]
MID = {"name": "mid", "type": "region", "x": [-2.2, -1.5], "y": [-0.75, 0.75]}


def _variant(through):
    world = copy.deepcopy(WORLD)
    world["places"].append(MID)
    parameters = copy.deepcopy(PARAMETERS)
    parameters["places"]["through"] = through
    return world, parameters


def _both(tmp_path, points, world=WORLD, parameters=PARAMETERS):
    mcap, binding = _recording(tmp_path, points)
    media_step = next(
        s
        for s in runner.run_trial(mcap, binding, LIMITS, world, parameters=parameters)["steps"]
        if s["id"] == TURNED
    )
    signals = runner.read_signals(mcap, json.loads(binding.read_text()))
    observation = {"trace": {"samples": runner._samples(signals["base"])}}
    trial = next(
        i
        for i in checks.assess(observation, LIMITS, "t", world=world, parameters=parameters)
        if i["evaluator"] == TURNED
    )
    return media_step, trial


def _verdict(status):
    return {"PASS": "PASS", "FAIL": "FAIL"}.get(status, "INCONCLUSIVE")


@pytest.mark.parametrize(
    ("points", "through", "expected"),
    [
        (THROUGH, ["corner"], "PASS"),
        (AROUND, ["corner"], "FAIL"),
        (LATE, ["corner"], "FAIL"),
        (THROUGH, ["mid", "corner"], "PASS"),
        (THROUGH, ["corner", "mid"], "FAIL"),
        (THROUGH, ["corner", "nowhere"], "INCONCLUSIVE"),
    ],
)
def test_media_and_trial_paths_agree_on_corner_turned(tmp_path, points, through, expected) -> None:
    world, parameters = _variant(through)
    got, trial = _both(tmp_path, points, world, parameters)
    assert got["verdict"] == _verdict(trial["status"]) == expected, (got, trial["status"])
    assert "reason" not in got
    assert got["summary"] == trial["rationale"]


def test_citation_digest_is_the_trial_paths_for_the_same_parameter_document(tmp_path) -> None:
    out, document, _ = _grade(tmp_path, THROUGH)
    cited = next(i for i in document["inputs"] if i["role"] == "thresholds")["sha256"]
    thresholds, missing = media.thresholds_from_manifest(MANIFEST, PARAMETERS)
    assert not missing
    assert cited == result.thresholds_input(thresholds, PARAMETERS)["sha256"]
    parameters_digest = hashlib.sha256(result.canonical_json(PARAMETERS)).hexdigest()
    assert result.parameters_source(PARAMETERS) == {"sha256": parameters_digest}
    written = json.loads((out / "media" / "thresholds.json").read_text())
    assert written == result.thresholds_document(thresholds, PARAMETERS)
    assert (out / "media" / "thresholds.json").read_bytes() == result.thresholds_bytes(
        thresholds, PARAMETERS
    )
