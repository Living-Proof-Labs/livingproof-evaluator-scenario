# SPDX-License-Identifier: Apache-2.0
"""Grade a run's media (MCAP + binding per trial) into result files (issue 1, pipeline job).

Limits come from the run manifest only. A limit the manifest cannot give leaves its step
NOT_EVALUATED, whatever the parameter file or a default would say. Each result names the
evaluator that produced it: id, version and where it came from.
"""

from __future__ import annotations

import copy
import hashlib
import json
import shutil
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from livingproof_evaluator_scenario import media, result
from livingproof_evaluator_scenario.compat import parameters_document
from livingproof_evaluator_scenario.errors import EvaluationError

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "tests" / "fixtures" / "sim-1e020b2"
MANIFEST = json.loads((ROOT / "tests" / "fixtures" / "run-manifest" / "manifest.json").read_text())
WORLD = json.loads((FIX / "world.json").read_text())
PARAMETERS = parameters_document()
BY_RULE = {c["fail_when"]: c["evaluator"] for c in PARAMETERS["checks"]}
EXIT, LATERAL = BY_RULE["absent-or-greater-than-limit"], BY_RULE["greater-than-limit"]
WALL, FALL = BY_RULE["not-empty"], BY_RULE["less-than-limit"]
IDENTITY = "git+https://github.com/Living-Proof-Labs/livingproof-evaluator-scenario@" + "ab" * 20
STARTED = "2026-11-20T10:00:00Z"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_run(tmp_path: Path, kind: str, manifest: dict | None = None) -> tuple[Path, Path]:
    """A run directory: manifest.json and media/ (media.json 2.1.0, mcap/ with the bindings)."""
    run = tmp_path / "run"
    (run / "media" / "mcap").mkdir(parents=True)
    trials = []
    for index, n in enumerate(("01", "02"), start=1):
        entry = {"index": index}
        for key, suffix in (("mcap", "mcap"), ("binding", "binding.json")):
            target = run / "media" / "mcap" / f"trial-{n}.{suffix}"
            shutil.copy(FIX / kind / f"trial-{n}.{suffix}", target)
            entry[key] = {
                "path": f"mcap/trial-{n}.{suffix}",
                "bytes": target.stat().st_size,
                "sha256": sha(target),
            }
        trials.append(entry)
    (run / "media" / "media.json").write_text(
        json.dumps(
            {
                "format": "livingproof-" + "hall" + "way-media/2.1.0",
                "configuration": MANIFEST["configuration"]["name"],
                "run_id": MANIFEST["run_id"],
                "trials": trials,
            }
        )
    )
    path = run / "manifest.json"
    path.write_text(json.dumps(MANIFEST if manifest is None else manifest))
    return path, run / "media"


def grade(tmp_path, kind="contact", manifest=None, identity=IDENTITY):
    manifest_path, media_dir = make_run(tmp_path, kind, manifest)
    out = tmp_path / "out"
    written = media.write_media_run(
        manifest_path,
        media_dir,
        out,
        started_at=STARTED,
        completed_at=STARTED,
        world=WORLD,
        identity=identity,
    )
    return out, [json.loads(p.read_text()) for p in written if p.name != "thresholds.json"]


def steps(document):
    return {s["id"]: s for s in document["scenario"]["steps"]}


def test_limits_are_resolved_from_the_manifest_alone() -> None:
    limits, missing = media.thresholds_from_manifest(MANIFEST)
    assert missing == {}
    assert limits == {
        "time_limit": 27.0,
        "lateral_limit": 0.4795,
        "half_width": 0.75,
        "fall_height": 0.44,
    }


def test_a_limit_the_manifest_cannot_give_is_missing_and_never_defaulted() -> None:
    no_speed = copy.deepcopy(MANIFEST)
    del no_speed["plan"]["command_speed"]  # the parameter file's own 0.5 must not stand in
    limits, missing = media.thresholds_from_manifest(no_speed)
    assert "time_limit" not in limits and "time_limit" in missing
    assert limits["fall_height"] == 0.44
    no_fall = copy.deepcopy(MANIFEST)
    del no_fall["configuration"]["profile"]["locomotion"]["fall_base_height"]
    limits, missing = media.thresholds_from_manifest(no_fall)
    assert "fall_height" not in limits and "fall_height" in missing
    assert limits["time_limit"] == 27.0


def test_the_module_has_no_verifier_to_fall_back_on() -> None:
    text = (ROOT / "src" / "livingproof_evaluator_scenario" / "media.py").read_text()
    assert "capability_verifier" not in text


def test_a_wall_contact_run_reports_the_contact_from_the_recording(tmp_path) -> None:
    out, documents = grade(tmp_path, "contact")
    assert [d["scenario"]["trial_id"] for d in documents] == [
        f"{MANIFEST['configuration']['name']}-seed-01",
        f"{MANIFEST['configuration']['name']}-seed-02",
    ]
    wall = steps(documents[0])[WALL]
    assert (
        wall["verdict"] == "FAIL" and "wall-left" in wall["summary"] and "0.13" in wall["summary"]
    )
    assert (out / "media" / "thresholds.json").is_file()
    cited = [i for i in documents[0]["inputs"] if i["role"] == "thresholds"]
    # Beside the observation-graded results' own thresholds.json, not over it.
    assert cited[0]["uri"] == "media/thresholds.json"
    assert cited[0]["sha256"] == sha(out / "media" / "thresholds.json")


def test_each_result_names_the_evaluator_that_produced_it(tmp_path) -> None:
    _, documents = grade(tmp_path, "contact")
    document = documents[0]
    assert document["evaluator"]["id"] == "livingproof-scenario"
    assert document["evaluator"]["version"] == result.package_version()
    ident = [i for i in document["inputs"] if i["role"] == "evaluator"]
    assert len(ident) == 1 and ident[0]["uri"] == IDENTITY
    assert ident[0]["sha256"] == media.source_digest()
    roles = {i["role"] for i in document["inputs"]}
    assert {"recording", "binding", "manifest", "thresholds", "evaluator"} <= roles


def test_an_identity_is_required(tmp_path) -> None:
    with pytest.raises(EvaluationError, match="identity"):
        grade(tmp_path, identity="")


def test_a_missing_limit_leaves_only_its_step_not_evaluated(tmp_path) -> None:
    broken = copy.deepcopy(MANIFEST)
    del broken["configuration"]["profile"]["locomotion"]["fall_base_height"]
    _, documents = grade(tmp_path, "clear", broken)
    by = steps(documents[0])
    assert by[FALL]["verdict"] == "NOT_EVALUATED" and by[FALL]["reason"] == "missing_threshold"
    assert "fall_height" in by[FALL]["summary"]
    assert by[WALL]["verdict"] == "PASS"
    assert by[EXIT]["verdict"] in ("PASS", "FAIL")


def test_an_unbound_observable_is_not_evaluated_in_the_report_document(tmp_path) -> None:
    manifest_path, media_dir = make_run(tmp_path, "contact")
    binding_path = media_dir / "mcap" / "trial-01.binding.json"
    binding = json.loads(binding_path.read_text())
    del binding["observables"]["body_contact"]
    binding["bound_observables"].remove("body_contact")
    binding["unbound"] = [{"id": "body_contact", "reason": "producer_missing"}]
    binding_path.write_text(json.dumps(binding))
    index = json.loads((media_dir / "media.json").read_text())
    index["trials"][0]["binding"]["sha256"] = sha(binding_path)
    (media_dir / "media.json").write_text(json.dumps(index))
    written = media.write_media_run(
        manifest_path,
        media_dir,
        tmp_path / "o",
        started_at=STARTED,
        completed_at=STARTED,
        world=WORLD,
        identity=IDENTITY,
    )
    first = json.loads(written[0].read_text())
    assert steps(first)[WALL]["verdict"] == "NOT_EVALUATED"
    assert steps(first)[WALL]["reason"] == "unbound_observable"


def test_a_recording_that_is_not_the_one_media_json_lists_is_refused(tmp_path) -> None:
    manifest_path, media_dir = make_run(tmp_path, "clear")
    (media_dir / "mcap" / "trial-01.mcap").write_bytes(b"not the recording")
    with pytest.raises(EvaluationError, match="sha256"):
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


def test_a_media_json_without_binding_files_grades_nothing(tmp_path) -> None:
    manifest_path, media_dir = make_run(tmp_path, "clear")
    index = json.loads((media_dir / "media.json").read_text())
    index["format"] = "livingproof-" + "hall" + "way-media/2.0.0"
    for trial in index["trials"]:
        del trial["binding"]
    (media_dir / "media.json").write_text(json.dumps(index))
    with pytest.raises(EvaluationError, match="binding"):
        media.write_media_run(
            manifest_path,
            media_dir,
            tmp_path / "o",
            started_at=STARTED,
            completed_at=STARTED,
            world=WORLD,
            identity=IDENTITY,
        )


def test_the_scenario_payload_matches_the_contract_with_the_new_reason(tmp_path) -> None:
    schema = json.loads((FIX / "schema" / "scenario-result.schema.json").read_text())
    reasons = schema["$defs"]["step"]["properties"]["reason"]["enum"]
    assert "missing_threshold" not in reasons  # the contract change is its own evaluator PR
    schema["$defs"]["step"]["properties"]["reason"]["enum"] = [*reasons, "missing_threshold"]
    validator = Draft202012Validator(schema)
    broken = copy.deepcopy(MANIFEST)
    del broken["configuration"]["profile"]["locomotion"]["fall_base_height"]
    _, documents = grade(tmp_path, "contact", broken)
    for document in documents:
        assert list(validator.iter_errors(document["scenario"])) == []


def test_the_command_line_writes_the_same_files(tmp_path, capsys) -> None:
    manifest_path, media_dir = make_run(tmp_path, "contact")
    world = tmp_path / "world.json"
    world.write_text(json.dumps(WORLD))
    code = media.main(
        [
            str(manifest_path),
            str(media_dir),
            str(tmp_path / "cli"),
            "--world",
            str(world),
            "--identity",
            IDENTITY,
            "--started-at",
            STARTED,
        ]
    )
    assert code == 0
    assert sorted(p.name for p in (tmp_path / "cli").glob("*.json")) == [
        "stock-seed-01.json",
        "stock-seed-02.json",
        "thresholds.json",
    ]
