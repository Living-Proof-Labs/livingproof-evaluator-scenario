# SPDX-License-Identifier: Apache-2.0
"""Resolved limits match livingproof-scenario-parameters on every catalog case.

The case file is the byte copy of robot-capability-specs v2.2.0. See
tests/fixtures/robot-capability-specs-v2.2.0/PROVENANCE.json.
"""

import hashlib
import json
from pathlib import Path

import pytest
from livingproof_scenario_parameters import ScenarioParameterError, reference_errors, resolve

from livingproof_evaluator_scenario.checks import accepted_limits, limits_from_thresholds
from livingproof_evaluator_scenario.compat import parameters_document
from livingproof_evaluator_scenario.compat.recorded import PARAMETERS_COMMIT, PARAMETERS_SHA256

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "tests/fixtures/robot-capability-specs-v2.2.0"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _catalog():
    provenance = json.loads((CATALOG / "PROVENANCE.json").read_text(encoding="utf-8"))
    assert provenance["tag"] == "v2.2.0"
    assert provenance["commit"] == PARAMETERS_COMMIT
    loaded = {}
    for name, meta in provenance["files"].items():
        path = CATALOG / name
        assert _sha(path) == meta["sha256"], name
        loaded[name] = json.loads(path.read_text(encoding="utf-8"))
    vendored = ROOT / "src/livingproof_evaluator_scenario/compat/parameters.json"
    assert _sha(vendored) == provenance["files"]["parameters.json"]["sha256"]
    assert _sha(vendored) == PARAMETERS_SHA256
    assert parameters_document() == loaded["parameters.json"]
    return loaded


def test_every_parameter_case_matches_the_package_resolution():
    catalog = _catalog()
    document = catalog["parameters.json"]
    cases = catalog["parameter-cases.json"]["cases"]
    assert len(cases) == 20
    assert reference_errors(document) == []
    for case in cases:
        expect = case["expect"]
        if expect.get("error") == "ERROR":
            with pytest.raises(ScenarioParameterError) as ours:
                accepted_limits(document, case["inputs"])
            with pytest.raises(ScenarioParameterError) as package:
                resolve(document, case["inputs"])
            assert ours.value.status == package.value.status == "ERROR"
            continue
        package_limits = resolve(document, case["inputs"])["limits"]
        assert accepted_limits(document, case["inputs"]) == package_limits == expect["limits"]
        # The verifier still passes exit_segment as half_width. Those are the limits we accept.
        thresholds = {
            "time_limit": package_limits["time_limit"],
            "lateral_limit": package_limits["lateral_limit"],
            "half_width": package_limits["exit_segment"],
            "fall_height": package_limits["fall_height"],
        }
        assert limits_from_thresholds(document, thresholds) == package_limits
