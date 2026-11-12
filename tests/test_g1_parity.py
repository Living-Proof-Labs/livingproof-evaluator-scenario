# SPDX-License-Identifier: Apache-2.0
"""The stored G1 run, Actions 43159586597, graded again from its observations.

Playground is 3 successes, 100%. Stock is 0 successes, 0%. Each check's
status, rationale and details match the assessments that run stored.
"""

import json
from pathlib import Path

from livingproof_evaluator_scenario.checks import EVALUATORS
from livingproof_evaluator_scenario.result import assess

FIXTURES = Path(__file__).parent / "fixtures" / "run-43159586597"
EXPECTED = json.loads((FIXTURES / "expected.json").read_text(encoding="utf-8"))
PHRASES = {"playground": "3 successes, 100%", "stock": "0 successes, 0%"}


def _phrase(passed, total):
    """The success line reporter v3.5.0 writes for these two counts."""
    face = f"{round(100 * passed / total)}%"
    word = "success" if passed == 1 else "successes"
    return f"{passed} {word}, {face}"


def test_run_phrases_are_the_stored_outcomes():
    assert EXPECTED["run_id"] == "43159586597"
    for name, phrase in PHRASES.items():
        recorded = EXPECTED["configurations"][name]
        assert recorded["phrase"] == phrase
        assert _phrase(recorded["passed"], recorded["trials_n"]) == phrase


def test_each_check_matches_the_stored_assessment():
    for name, recorded in EXPECTED["configurations"].items():
        passed = 0
        for trial in recorded["trials"]:
            observation = json.loads((FIXTURES / trial["observation"]).read_text(encoding="utf-8"))
            got = assess(
                observation,
                recorded["thresholds"],
                trial["id"],
                ("trial", trial["index"]),
            )
            assert [item["evaluator"] for item in got] == list(EVALUATORS)
            assert got == trial["assessments"]
            if trial["status"] == "PASS":
                passed += 1
                assert all(item["status"] == "PASS" for item in got)
            else:
                assert trial["status"] == "FAIL"
                assert any(item["status"] == "FAIL" for item in got)
        assert passed == recorded["passed"]
        assert recorded["grade"] == ("PASS" if passed == recorded["trials_n"] else "FAIL")
        assert _phrase(passed, recorded["trials_n"]) == PHRASES[name]
