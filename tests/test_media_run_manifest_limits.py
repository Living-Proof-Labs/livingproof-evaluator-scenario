# SPDX-License-Identifier: Apache-2.0
"""Hand checks for the media run (Vera, verification of PR 31).

Passing tests: a verdict follows a limit changed in the manifest, a missing limit is never a
default or a PASS, the thresholds file records what was used, and the identity is the one the
caller stated plus the digest of the installed source.

media.json is checked against the manifest's plan.trials.count: a run that lists fewer or more
trials than planned, an index outside 1..count, one index twice, or none, is refused with an
EvaluationError and nothing is written.
"""

from __future__ import annotations

import copy
import json

import pytest

from livingproof_evaluator_scenario import media
from livingproof_evaluator_scenario.errors import EvaluationError
from test_media_run import (
    EXIT,
    FALL,
    IDENTITY,
    LATERAL,
    MANIFEST,
    PLANNED_THREE,
    STARTED,
    WORLD,
    grade,
    make_run,
    steps,
)


def _verdicts(tmp_path, kind, manifest):
    _, documents = grade(tmp_path, kind, manifest)
    return {s["id"]: (s["verdict"], s.get("reason")) for s in documents[0]["scenario"]["steps"]}


def test_the_fall_verdict_follows_the_manifests_fall_base_height(tmp_path) -> None:
    low = copy.deepcopy(MANIFEST)
    low["configuration"]["profile"]["locomotion"]["fall_base_height"]["value"] = -100.0
    assert _verdicts(tmp_path / "a", "clear", MANIFEST)[FALL] == ("FAIL", None)
    assert _verdicts(tmp_path / "b", "clear", low)[FALL] == ("PASS", None)


def test_the_lateral_verdict_follows_the_manifests_clear_width(tmp_path) -> None:
    wide = copy.deepcopy(MANIFEST)
    wide["world"]["clear_width"] = 6.0
    assert _verdicts(tmp_path / "a", "contact", MANIFEST)[LATERAL] == ("FAIL", None)
    assert _verdicts(tmp_path / "b", "contact", wide)[LATERAL] == ("PASS", None)


@pytest.mark.parametrize(
    ("mutate", "step"),
    [
        (lambda m: m["plan"].pop("command_speed"), EXIT),
        (lambda m: m["world"].pop("clear_width"), LATERAL),
        (lambda m: m["robot"]["profile"]["dimensions"]["width"].update(value="wide"), LATERAL),
        (lambda m: m["configuration"]["profile"]["locomotion"].pop("fall_base_height"), FALL),
    ],
    ids=["no speed", "no clear width", "robot width not a number", "no fall base height"],
)
@pytest.mark.parametrize("kind", ["clear", "contact"])
def test_a_limit_the_manifest_lacks_is_never_a_default_or_a_pass(tmp_path, kind, mutate, step):
    manifest = copy.deepcopy(MANIFEST)
    mutate(manifest)
    got = _verdicts(tmp_path, kind, manifest)
    assert got[step] == ("NOT_EVALUATED", "missing_threshold")
    assert all(v[1] is None for k, v in got.items() if k not in (step, EXIT, LATERAL))
    _, documents = grade(tmp_path / "again", kind, manifest)
    assert "PASS" not in {steps(d)[step]["verdict"] for d in documents}


def test_the_thresholds_file_lists_what_was_missing_and_omits_it_from_the_limits(tmp_path) -> None:
    manifest = copy.deepcopy(MANIFEST)
    manifest["configuration"]["profile"]["locomotion"].pop("fall_base_height")
    out, _ = grade(tmp_path, "clear", manifest)
    document = json.loads((out / "media" / "thresholds.json").read_text())
    assert "fall_height" in document["missing"] and "fall_height" not in document["limits"]
    full, _ = grade(tmp_path / "full", "clear", MANIFEST)
    assert "missing" not in json.loads((full / "media" / "thresholds.json").read_text())


def test_the_evaluator_identity_is_the_stated_one_and_the_installed_source(tmp_path) -> None:
    _, documents = grade(tmp_path, "contact")
    for document in documents:
        assert document["evaluator"]["id"] == "livingproof-scenario"
        assert document["descriptor"]["version"] == document["evaluator"]["version"]
        (ref,) = [i for i in document["inputs"] if i["role"] == "evaluator"]
        assert ref == {"role": "evaluator", "uri": IDENTITY, "sha256": media.source_digest()}


def _write(tmp_path, index_edit, manifest=None):
    manifest_path, media_dir = make_run(tmp_path, "clear", manifest)
    index = json.loads((media_dir / "media.json").read_text())
    index_edit(index)
    (media_dir / "media.json").write_text(json.dumps(index))
    return media.write_media_run(
        manifest_path,
        media_dir,
        tmp_path / "out",
        started_at=STARTED,
        completed_at=STARTED,
        world=WORLD,
        identity=IDENTITY,
    )


def test_a_run_that_lists_fewer_trials_than_the_manifest_plans_is_refused(tmp_path) -> None:
    assert PLANNED_THREE["plan"]["trials"]["count"] == 3  # the fixture plans three trials
    with pytest.raises(EvaluationError, match="lists 2 trials but the manifest plans 3"):
        _write(tmp_path, lambda i: None, PLANNED_THREE)  # media.json lists two


def test_a_trial_index_listed_twice_is_refused(tmp_path) -> None:
    with pytest.raises(EvaluationError, match="trial 1 is listed twice"):
        _write(
            tmp_path,
            lambda i: i["trials"].append(copy.deepcopy(i["trials"][0])),
            _two_trial_manifest(),
        )


def test_a_media_json_with_no_trials_is_refused(tmp_path) -> None:
    with pytest.raises(EvaluationError, match="lists no trials"):
        _write(tmp_path, lambda i: i.update(trials=[]), _two_trial_manifest())


def test_a_binding_file_that_is_not_the_one_media_json_lists_is_refused(tmp_path) -> None:
    """Only the sha256 listed in media.json ties a binding to the run; the runner's own check
    covers the recording alone."""
    manifest_path, media_dir = make_run(tmp_path, "clear")
    path = media_dir / "mcap" / "trial-01.binding.json"
    binding = json.loads(path.read_text())
    binding["trial_id"] = "someone-elses-trial"  # still a valid binding for the same recording
    path.write_text(json.dumps(binding))
    with pytest.raises(EvaluationError, match="binding sha256"):
        media.write_media_run(
            manifest_path,
            media_dir,
            tmp_path / "o",
            started_at=STARTED,
            completed_at=STARTED,
            world=WORLD,
            identity=IDENTITY,
        )
    assert not (tmp_path / "o").exists()


def test_a_trial_index_outside_the_plan_is_refused(tmp_path) -> None:
    with pytest.raises(EvaluationError, match="trial 7"):
        _write(tmp_path, lambda i: i["trials"][1].update(index=7), _two_trial_manifest())
    assert not (tmp_path / "out").exists()


def test_a_refused_run_writes_nothing(tmp_path) -> None:
    with pytest.raises(EvaluationError):
        _write(
            tmp_path,
            lambda i: i["trials"].append(copy.deepcopy(i["trials"][0])),
            _two_trial_manifest(),
        )
    assert not (tmp_path / "out").exists()


def test_a_manifest_without_configuration_name_is_a_clear_error(tmp_path) -> None:
    manifest = copy.deepcopy(MANIFEST)
    del manifest["configuration"]["name"]
    with pytest.raises(EvaluationError, match="configuration.name"):
        _write(tmp_path, lambda i: None, manifest)


def test_a_manifest_without_a_trial_count_is_a_clear_error(tmp_path) -> None:
    manifest = copy.deepcopy(MANIFEST)
    del manifest["plan"]["trials"]["count"]
    with pytest.raises(EvaluationError, match="plan.trials.count"):
        _write(tmp_path, lambda i: None, manifest)


def _two_trial_manifest():
    return copy.deepcopy(MANIFEST)
