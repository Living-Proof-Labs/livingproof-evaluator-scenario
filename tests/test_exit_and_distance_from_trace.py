# SPDX-License-Identifier: Apache-2.0
"""Acceptance for criterion 3: the evaluator applies the rule to the trace itself.

The exit is the first step the sample rule accepts, and the distance check
cannot pass while a trace sample is farther from the route than the limit.
Each case below is one where the stored fields and the trace disagree. The
evaluator may grade from the trace, or call the record inconsistent
(INSUFFICIENT_EVIDENCE); it may not grade from the stored field alone.
Every stored trial in tests/fixtures agrees with its trace, so these stay
byte-identical.
"""

from livingproof_evaluator_scenario.checks import INSUFFICIENT, PASS, assess
from livingproof_evaluator_scenario.compat import frozen_observation_format

THRESHOLDS = {"time_limit": 27.0, "lateral_limit": 0.49, "half_width": 0.75, "fall_height": 0.5}


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


def _exit(observation):
    return assess(observation, THRESHOLDS, "t", ("trial", 1))[0]


def _graded_at_first_crossing_or_inconsistent(got, first):
    assert got["status"] in (PASS, INSUFFICIENT), got["rationale"]
    if got["status"] == PASS:
        assert got["details"]["observed"] == first


def test_a_later_claimed_exit_does_not_hide_the_first_crossing():
    # Crosses inside the segment at 10.5 s, steps back, crosses again at 30 s.
    samples = [
        [0.0, 0.0, 0.0, 0.7],
        [10.0, 2.9, 0.0, 0.7],
        [10.5, 3.1, 0.0, 0.7],
        [20.0, 2.5, 0.0, 0.7],
        [30.0, 3.2, 0.0, 0.7],
    ]
    got = _exit(_observation(samples, exit_time=30.0, duration_s=30.0))
    _graded_at_first_crossing_or_inconsistent(got, 10.5)


def test_a_claimed_step_already_past_the_line_is_not_an_outside_segment_fail():
    samples = [
        [0.0, 0.0, 0.0, 0.7],
        [10.0, 2.9, 0.0, 0.7],
        [10.5, 3.1, 0.0, 0.7],
        [11.0, 3.4, 0.0, 0.7],
    ]
    got = _exit(_observation(samples, exit_time=11.0))
    _graded_at_first_crossing_or_inconsistent(got, 10.5)


def test_a_crossing_in_the_trace_is_not_exit_not_reached():
    samples = [
        [0.0, 0.0, 0.0, 0.7],
        [10.0, 2.9, 0.0, 0.7],
        [10.5, 3.1, 0.0, 0.7],
    ]
    got = _exit(_observation(samples, end="time_limit", exit_time=None, duration_s=27.0))
    _graded_at_first_crossing_or_inconsistent(got, 10.5)


def test_distance_cannot_pass_with_a_trace_sample_over_the_limit():
    # 0.9 m from the route at 5 s; the stored maximum says 0.1 m.
    samples = [
        [0.0, 0.0, 0.0, 0.7],
        [5.0, 0.0, 0.9, 0.7],
        [10.0, 2.9, 0.0, 0.7],
        [10.5, 3.1, 0.0, 0.7],
    ]
    observation = _observation(samples, max_abs_lateral={"value": 0.1, "time": 0.0})
    got = assess(observation, THRESHOLDS, "t", ("trial", 1))[1]
    assert got["status"] in ("FAIL", INSUFFICIENT), got["rationale"]
    if got["status"] == "FAIL":
        assert got["details"]["observed"] >= 0.9
        assert got["details"]["time"] == 5.0
