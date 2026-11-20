# SPDX-License-Identifier: Apache-2.0
"""Refusals by type and bound (Vera, recheck of PR 31 at 7622fd4).

The first rows are the mutants the PR's tests let survive: a bool or a float or a string as a trial
index, index 0, a bool or non-positive or non-integer plan.trials.count, and a configuration.name
that is empty or not a string. Each must raise EvaluationError and leave a pre-existing output
directory byte-for-byte unchanged.
"""

from __future__ import annotations

import copy
import hashlib
import json

import pytest

from livingproof_evaluator_scenario import media
from livingproof_evaluator_scenario.errors import EvaluationError
from test_media_run import IDENTITY, MANIFEST, STARTED, WORLD, make_run


def _snapshot(root):
    return {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


def _refused(tmp_path, *, index=None, manifest=None):
    manifest_path, media_dir = make_run(tmp_path, "clear", copy.deepcopy(manifest or MANIFEST))
    document = json.loads((media_dir / "media.json").read_text())
    if index is not None:
        index(document)
        (media_dir / "media.json").write_text(json.dumps(document))
    out = tmp_path / "out"
    (out / "media").mkdir(parents=True)
    (out / "media" / "thresholds.json").write_text("OLD")
    (out / "stock-seed-01.json").write_text("OLD")
    before = _snapshot(out)
    with pytest.raises(EvaluationError) as raised:
        media.write_media_run(
            manifest_path,
            media_dir,
            out,
            started_at=STARTED,
            completed_at=STARTED,
            world=WORLD,
            identity=IDENTITY,
        )
    assert _snapshot(out) == before, "a refused run changed the output directory"
    return str(raised.value)


@pytest.mark.parametrize("bad", [0, -1], ids=repr)
def test_an_integer_index_outside_one_to_count_is_refused(tmp_path, bad) -> None:
    message = _refused(tmp_path, index=lambda d: d["trials"][0].update(index=bad))
    assert f"trial {bad} is outside the plan (1 to 2)" in message


@pytest.mark.parametrize("bad", [True, 1.0, "1", [1]], ids=repr)
def test_an_index_that_is_not_an_integer_is_refused_and_named(tmp_path, bad) -> None:
    message = _refused(tmp_path, index=lambda d: d["trials"][0].update(index=bad))
    assert f"index {bad!r} is not an integer" in message


def test_a_trial_with_no_index_says_so(tmp_path) -> None:
    message = _refused(tmp_path, index=lambda d: d["trials"][0].pop("index"))
    assert "entry 1 has no index" in message
    assert "None" not in message


def test_index_zero_with_a_full_length_list_is_refused(tmp_path) -> None:
    """[0, 2] has the planned length and no repeat; only the lower bound refuses it."""
    message = _refused(tmp_path, index=lambda d: d["trials"][0].update(index=0))
    assert "trial 0" in message


def test_a_trial_that_is_not_an_object_is_refused(tmp_path) -> None:
    _refused(tmp_path, index=lambda d: d["trials"].__setitem__(0, 1))


@pytest.mark.parametrize("bad", ["12", {"a": 1}, None, 2], ids=repr)
def test_trials_that_is_not_a_list_is_refused(tmp_path, bad) -> None:
    message = _refused(tmp_path, index=lambda d: d.update(trials=bad))
    assert f"trials must be a list, not {type(bad).__name__}" in message


@pytest.mark.parametrize("bad", [True, 0, -1, 2.0, "2"], ids=repr)
def test_a_plan_trials_count_that_is_not_a_positive_integer_is_refused(tmp_path, bad) -> None:
    manifest = copy.deepcopy(MANIFEST)
    manifest["plan"]["trials"]["count"] = bad
    assert "plan.trials.count" in _refused(tmp_path, manifest=manifest)


@pytest.mark.parametrize("bad", ["", "  ", 5, None, ["x"]], ids=repr)
def test_a_configuration_name_that_is_not_a_non_empty_string_is_refused(tmp_path, bad) -> None:
    manifest = copy.deepcopy(MANIFEST)
    manifest["configuration"]["name"] = bad
    assert "configuration.name" in _refused(tmp_path, manifest=manifest)


@pytest.mark.parametrize("bad", [True, "x"])
def test_a_manifest_whose_plan_or_configuration_is_not_an_object_is_refused(tmp_path, bad) -> None:
    for key, needle in (("plan", "plan.trials.count"), ("configuration", "configuration.name")):
        manifest = copy.deepcopy(MANIFEST)
        manifest[key] = bad
        assert needle in _refused(tmp_path / key, manifest=manifest)
