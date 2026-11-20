# SPDX-License-Identifier: Apache-2.0
"""The media path on a corner scenario (issue 35, Vera's Lows 2 and 3 on lpv PR 184).

The recording is synthetic: a base track written here, graded with the walk-corner parameter file
and world. The step ``corner-turned`` (rule ``not-in-order``) is graded from the recording, and the
thresholds file cites the parameter file that selected the limits, not the frozen default's.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from mcap.writer import Writer

from livingproof_evaluator_scenario import media, result
from livingproof_evaluator_scenario.compat import parameters_document
from test_media_run import IDENTITY, MANIFEST, STARTED, sha

ROOT = Path(__file__).resolve().parents[1]
CORNER = ROOT / "tests" / "fixtures" / "sim-v3.2.0-route"
WORLD = json.loads((CORNER / "world.json").read_text())
PARAMETERS = json.loads((CORNER / "parameters.json").read_text())
TURNED = "corner-turned"
THROUGH = [(-2.5, 0.0), (0.0, 0.0), (0.0, 3.2)]
AROUND = [(-2.5, 0.0), (-2.5, 3.2), (0.0, 3.2)]


def _recording(directory: Path, points) -> tuple[Path, Path]:
    """A base track walking the points at 0.5 m/s, with an empty contacts channel."""
    mcap = directory / "trial-01.mcap"
    with mcap.open("wb") as stream:
        writer = Writer(stream)
        writer.start()
        schema = writer.register_schema("s", "jsonschema", b"{}")
        pose = writer.register_channel("/base_pose", "json", schema)
        writer.register_channel("/wall_contacts", "json", schema)
        t = 0.0
        for (x0, y0), (x1, y1) in zip(points, points[1:], strict=False):
            steps = max(1, round(max(abs(x1 - x0), abs(y1 - y0)) / 0.05))
            for i in range(steps):
                f = i / steps
                body = {"x": x0 + (x1 - x0) * f, "y": y0 + (y1 - y0) * f, "z": 0.8}
                ns = int(t * 1e9)
                writer.add_message(pose, ns, json.dumps({"p": body}).encode(), ns)
                t += 0.1
        writer.finish()
    observable = {"topic": "/base_pose", "encoding": "json", "schema": "s", "frame": "world"}
    binding = {
        "format": "livingproof-observation-binding/1.0.0",
        "kind": "merged",
        "trial_id": "synthetic",
        "robot": {"id": "toy", "configuration": "stock"},
        "producer": {"id": "livingproof-sim-mujoco"},
        "recording": {"uri": mcap.name, "sha256": hashlib.sha256(mcap.read_bytes()).hexdigest()},
        "observables": {
            "base": {**observable, "fields": {"x": "p.x", "y": "p.y"}, "body": "pelvis"},
            "base_height": {
                **observable,
                "fields": {"z": "p.z"},
                "nominal": {"value": 0.78, "unit": "meters", "source": "measured"},
            },
            "body_contact": {
                "topic": "/wall_contacts",
                "encoding": "json",
                "schema": "s",
                "fields": {"wall": "wall", "start": "start", "end": "end", "depth": "depth"},
                "frame": "world",
            },
        },
        "bound_observables": ["base", "base_height", "body_contact"],
        "unbound": [],
    }
    path = directory / "trial-01.binding.json"
    path.write_text(json.dumps(binding))
    return mcap, path


def _grade(tmp_path: Path, points, parameters=PARAMETERS, drop_speed=False):
    run = tmp_path / "run"
    (run / "media" / "mcap").mkdir(parents=True)
    mcap, binding = _recording(run / "media" / "mcap", points)
    entry = {"index": 1}
    for key, path in (("mcap", mcap), ("binding", binding)):
        entry[key] = {
            "path": f"mcap/{path.name}",
            "bytes": path.stat().st_size,
            "sha256": sha(path),
        }
    (run / "media" / "media.json").write_text(
        json.dumps(
            {
                "format": "livingproof-corner-media/2.1.0",
                "configuration": MANIFEST["configuration"]["name"],
                "run_id": MANIFEST["run_id"],
                "trials": [entry],
            }
        )
    )
    manifest = json.loads(json.dumps(MANIFEST))
    manifest["plan"]["trials"]["count"] = 1
    if drop_speed:
        del manifest["plan"]["command_speed"]
    (run / "manifest.json").write_text(json.dumps(manifest))
    written = media.write_media_run(
        run / "manifest.json",
        run / "media",
        tmp_path / "out",
        started_at=STARTED,
        completed_at=STARTED,
        world=WORLD,
        identity=IDENTITY,
        parameters=parameters,
    )
    documents = [json.loads(p.read_text()) for p in written]
    return tmp_path / "out", documents[0], {s["id"]: s for s in documents[0]["scenario"]["steps"]}


def test_corner_turned_passes_when_the_recording_goes_through_the_corner(tmp_path) -> None:
    _, _, steps = _grade(tmp_path, THROUGH)
    assert steps[TURNED]["verdict"] == "PASS", steps[TURNED]
    assert "corner" in steps[TURNED]["summary"]
    assert "reason" not in steps[TURNED]


def test_corner_turned_fails_when_the_recording_never_enters_the_corner(tmp_path) -> None:
    _, _, steps = _grade(tmp_path, AROUND)
    assert steps[TURNED]["verdict"] == "FAIL", steps[TURNED]
    assert "corner" in steps[TURNED]["summary"]


def test_corner_turned_is_not_evaluated_when_the_unbound_base_cannot_be_read(tmp_path) -> None:
    from livingproof_evaluator_scenario import runner

    mcap, binding = _recording(tmp_path, THROUGH)
    document = json.loads(binding.read_text())
    document["observables"].pop("base")
    document["bound_observables"].remove("base")
    document["unbound"] = [{"id": "base", "reason": "producer-does-not-carry"}]
    limits = {"time_limit": 27.0, "lateral_limit": 0.49, "half_width": 0.75, "fall_height": 0.5}
    payload = runner.run_trial(mcap, document, limits, WORLD, parameters=PARAMETERS)
    turned = next(s for s in payload["steps"] if s["id"] == TURNED)
    assert (turned["verdict"], turned["reason"]) == ("NOT_EVALUATED", "unbound_observable")


def test_thresholds_cite_the_parameter_file_that_selected_the_limits(tmp_path) -> None:
    out, document, _ = _grade(tmp_path, THROUGH)
    cited = json.loads((out / "media" / "thresholds.json").read_text())
    assert cited["parameters"] == result.parameters_source(PARAMETERS)
    assert "path" not in cited["parameters"]  # not the vendored default's repository, tag and path
    digest = next(i for i in document["inputs"] if i["role"] == "thresholds")["sha256"]
    assert digest == sha(out / "media" / "thresholds.json")


def test_thresholds_cite_the_parameter_file_when_a_limit_is_missing(tmp_path) -> None:
    out, _, _ = _grade(tmp_path, THROUGH, drop_speed=True)
    document = json.loads((out / "media" / "thresholds.json").read_text())
    assert "time_limit" in document["missing"]
    assert document["parameters"] == result.parameters_source(PARAMETERS)


def test_the_default_citation_is_unchanged_without_a_parameter_file() -> None:
    thresholds, _ = media.thresholds_from_manifest(MANIFEST)
    document = json.loads(result.thresholds_bytes(thresholds))
    assert document["parameters"] == result.parameters_source()
    assert document["parameters"]["path"] == result.PARAMETERS_PATH
    assert parameters_document()["scenario"]["id"] != PARAMETERS["scenario"]["id"]
