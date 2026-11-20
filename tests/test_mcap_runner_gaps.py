# SPDX-License-Identifier: Apache-2.0
"""Hand-check gaps in the MCAP runner tests, found by mutating the runner (Vera, verification).

Each test pins a verdict that the first runner tests left unpinned: a channel declared with
another encoding, a malformed or non-finite message, a declared channel with no messages, and the
fall rule exactly at the limit. None of these may be a PASS that nobody earned.
"""

from __future__ import annotations

import hashlib
import json

import pytest
from mcap.writer import Writer

from livingproof_evaluator_scenario import runner
from test_mcap_runner import EXIT, FALL, LATERAL, THRESHOLDS, WORLD, synthetic, verdicts


def _record(tmp_path, binding, messages, *, encoding="json"):
    """Rewrite the synthetic recording with the given /base_pose payloads (None: no messages)."""
    mcap = tmp_path / "g.mcap"
    with mcap.open("wb") as stream:
        writer = Writer(stream)
        writer.start()
        schema = writer.register_schema("s", "jsonschema", b"{}")
        pose = writer.register_channel("/base_pose", encoding, schema)
        writer.register_channel("/wall_contacts", "json", schema)
        for i, body in enumerate(messages):
            ns = int(i / 50 * 1e9)
            raw = body if isinstance(body, bytes) else json.dumps({"pose": {"position": body}})
            writer.add_message(pose, ns, raw.encode() if isinstance(raw, str) else raw, ns)
        writer.finish()
    binding["recording"]["sha256"] = hashlib.sha256(mcap.read_bytes()).hexdigest()
    return mcap


def _ok(i):
    return {"x": -0.5 + 2 * i / 50, "y": 0.0, "z": 0.7}


def _binding(tmp_path):
    _, binding = synthetic(tmp_path)
    return binding


def test_a_channel_declared_with_another_encoding_is_inconclusive(tmp_path):
    binding = _binding(tmp_path)
    mcap = _record(tmp_path, binding, [_ok(i) for i in range(101)], encoding="protobuf")
    got = verdicts(runner.run_trial(mcap, binding, THRESHOLDS, WORLD))
    assert got[EXIT] == got[LATERAL] == got[FALL] == "INCONCLUSIVE"


@pytest.mark.parametrize(
    ("bad", "hit"),
    [
        ({"x": 0.0, "y": 0.0}, (FALL,)),  # z missing
        ({"x": 0.0, "y": 0.0, "z": "0.7"}, (FALL,)),  # text, not a number
        ({"x": 0.0, "y": 0.0, "z": True}, (FALL,)),  # a bool is not a number
        ({"x": float("nan"), "y": 0.0, "z": 0.7}, (EXIT, LATERAL)),  # json.dumps writes NaN
        ({"x": 0.0, "y": float("inf"), "z": 0.7}, (EXIT, LATERAL)),
        ({"x": 0.0, "z": 0.7}, (EXIT, LATERAL)),  # y missing
    ],
    ids=["z-missing", "z-text", "z-bool", "x-nan", "y-inf", "y-missing"],
)
def test_a_malformed_message_leaves_only_the_steps_that_read_it_inconclusive(tmp_path, bad, hit):
    binding = _binding(tmp_path)
    mcap = _record(tmp_path, binding, [_ok(i) for i in range(100)] + [bad])
    got = verdicts(runner.run_trial(mcap, binding, THRESHOLDS, WORLD))
    for step in (EXIT, LATERAL, FALL):
        assert (got[step] == "INCONCLUSIVE") == (step in hit), (step, got)


def test_a_message_that_is_not_json_leaves_the_steps_inconclusive(tmp_path):
    binding = _binding(tmp_path)
    mcap = _record(tmp_path, binding, [b"not json"])
    got = verdicts(runner.run_trial(mcap, binding, THRESHOLDS, WORLD))
    assert got[EXIT] == got[LATERAL] == got[FALL] == "INCONCLUSIVE"


def test_a_declared_pose_channel_with_no_messages_is_inconclusive_not_a_fail_or_a_pass(tmp_path):
    binding = _binding(tmp_path)
    mcap = _record(tmp_path, binding, [])
    got = verdicts(runner.run_trial(mcap, binding, THRESHOLDS, WORLD))
    assert got[EXIT] == got[LATERAL] == got[FALL] == "INCONCLUSIVE"


@pytest.mark.parametrize(
    ("z", "verdict"),
    [(0.1, "PASS"), (0.0999, "FAIL"), (0.1001, "PASS")],
    ids=["at", "below", "above"],
)
def test_the_fall_rule_is_strictly_below_the_absolute_fall_height(tmp_path, z, verdict):
    binding = _binding(tmp_path)
    messages = [{**_ok(i), "z": z} for i in range(101)]
    mcap = _record(tmp_path, binding, messages)
    thresholds = {**THRESHOLDS, "fall_height": 0.1}
    assert verdicts(runner.run_trial(mcap, binding, thresholds, WORLD))[FALL] == verdict
