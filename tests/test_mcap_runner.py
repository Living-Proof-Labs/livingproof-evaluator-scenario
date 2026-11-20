# SPDX-License-Identifier: Apache-2.0
"""The runner reads a trial's MCAP through its merged observation binding (issue 1).

The MCAP files and bindings are real: livingproof-sim-mujoco 1e020b2 wrote them (see
tests/fixtures/sim-1e020b2/PROVENANCE.json). Each trial is also graded from the sim's own
observation by the existing checks, so the two paths must give the same verdicts.
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from mcap.writer import Writer
from referencing import Registry, Resource

from livingproof_evaluator_scenario import runner
from livingproof_evaluator_scenario.checks import assess
from livingproof_evaluator_scenario.errors import EvaluationError

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "tests" / "fixtures" / "sim-1e020b2"
WORLD = json.loads((FIX / "world.json").read_text())
THRESHOLDS = {"time_limit": 9.0, "lateral_limit": 0.6, "half_width": 0.75, "fall_height": 0.1}
STEPS = [
    "hallway-exit-reached",
    "hallway-lateral-limit",
    "hallway-wall-contact",
    "hallway-fall",
]
TRIALS = [(kind, n) for kind in ("clear", "contact") for n in ("01", "02")]


def load(path: Path):
    return json.loads(path.read_text())


def paths(kind, n):
    base = FIX / kind
    return base / f"trial-{n}.mcap", base / f"trial-{n}.binding.json"


def verdicts(payload):
    return {step["id"]: step["verdict"] for step in payload["steps"]}


def validator(name: str) -> Draft202012Validator:
    schemas = {p.name: load(p) for p in (FIX / "schema").glob("*.json")}
    registry = Registry().with_resources(
        (doc["$id"], Resource.from_contents(doc)) for doc in schemas.values()
    )
    registry = registry.with_resources(
        [(f"{n}", Resource.from_contents(doc)) for n, doc in schemas.items()]
    )
    return Draft202012Validator(schemas[name], registry=registry)


def run(kind, n, **kwargs):
    mcap, binding = paths(kind, n)
    return runner.run_trial(mcap, binding, kwargs.pop("thresholds", THRESHOLDS), WORLD, **kwargs)


def synthetic(tmp_path, *, topic="/base_pose", contacts=True, pose_path=("pose", "position")):
    """A small recording and a merged binding for it, written here so a test can vary them."""
    mcap = tmp_path / "t.mcap"
    with mcap.open("wb") as stream:
        writer = Writer(stream)
        writer.start()
        schema = writer.register_schema("s", "jsonschema", b"{}")
        pose = writer.register_channel(topic, "json", schema)
        if contacts:
            writer.register_channel("/wall_contacts", "json", schema)
        for i in range(0, 101):
            t = i / 50
            body = {"x": -0.5 + t, "y": 0.0, "z": 0.7}
            message = {}
            node = message
            for key in pose_path[:-1]:
                node = node.setdefault(key, {})
            node[pose_path[-1]] = body
            ns = int(t * 1e9)
            writer.add_message(pose, ns, json.dumps(message).encode(), ns)
        writer.finish()
    base = "." + ".".join(pose_path)
    binding = {
        "format": "livingproof-observation-binding/1.0.0",
        "kind": "merged",
        "trial_id": "synthetic",
        "robot": {"id": "toy", "configuration": "stock"},
        "producer": {"id": "livingproof-sim-mujoco"},
        "recording": {"uri": "t.mcap", "sha256": hashlib.sha256(mcap.read_bytes()).hexdigest()},
        "observables": {
            "base": {
                "topic": topic,
                "encoding": "json",
                "schema": "s",
                "fields": {"x": base[1:] + ".x", "y": base[1:] + ".y"},
                "frame": "world",
                "body": "pelvis",
            },
            "base_height": {
                "topic": topic,
                "encoding": "json",
                "schema": "s",
                "fields": {"z": base[1:] + ".z"},
                "frame": "world",
                "nominal": {"value": 0.78, "unit": "meters", "source": "measured"},
            },
        },
        "bound_observables": ["base", "base_height"],
        "unbound": [{"id": "body_contact", "reason": "producer-does-not-carry"}],
    }
    if contacts:
        binding["observables"]["body_contact"] = {
            "topic": "/wall_contacts",
            "encoding": "json",
            "schema": "s",
            "fields": {"wall": "wall", "start": "start", "end": "end", "depth": "depth"},
            "frame": "world",
        }
        binding["bound_observables"].append("body_contact")
        binding["unbound"] = []
    return mcap, binding


def test_the_fixtures_are_the_ones_the_sim_wrote():
    provenance = load(FIX / "PROVENANCE.json")
    assert "1e020b2" in provenance["generator"]
    for name, digest in provenance["sha256"].items():
        assert hashlib.sha256((FIX / name).read_bytes()).hexdigest() == digest, name
    for kind, n in TRIALS:
        mcap, binding = paths(kind, n)
        doc = load(binding)
        assert doc["recording"]["sha256"] == hashlib.sha256(mcap.read_bytes()).hexdigest()
        assert doc["bound_observables"] == ["base", "base_height", "body_contact"]
        assert doc["observables"]["body_contact"]["topic"] == "/wall_contacts"
        assert list(validator("binding.schema.json").iter_errors(doc)) == []


def test_a_channel_entry_without_its_required_topic_is_rejected():
    """The mutation the evaluator's own tests left alive (sim-mujoco#28 follow-up)."""
    _, binding = paths("contact", "01")
    for term in ("base", "base_height", "body_contact"):
        broken = load(binding)
        del broken["observables"][term]["topic"]
        assert list(validator("binding.schema.json").iter_errors(broken)), term
        with pytest.raises(runner.BindingError, match=f"{term}.*topic"):
            runner.read_binding(broken)


@pytest.mark.parametrize(("kind", "n"), TRIALS)
def test_every_verdict_matches_the_existing_checks_on_the_sims_own_observation(kind, n):
    payload = run(kind, n)
    observation = load(FIX / kind / f"observation-trial-{n}.json")
    graded = assess(observation, THRESHOLDS, "t", ("trial", int(n)), world=WORLD)
    expected = {item["evaluator"]: item["status"] for item in graded}
    assert verdicts(payload) == expected


@pytest.mark.parametrize(("kind", "n"), TRIALS)
def test_the_payload_is_the_contracts_scenario_result(kind, n):
    payload = run(kind, n)
    assert list(validator("scenario-result.schema.json").iter_errors(payload)) == []
    assert payload["trial_id"] == f"trial-{n}"
    assert [step["id"] for step in payload["steps"]] == STEPS


def test_a_clear_trial_passes_exit_lateral_and_wall_and_the_fall_rule_is_the_absolute_height():
    payload = run("clear", "01")
    assert verdicts(payload) == {
        "hallway-exit-reached": "PASS",
        "hallway-lateral-limit": "PASS",
        "hallway-wall-contact": "PASS",
        "hallway-fall": "FAIL",  # this toy robot falls through the floor
    }
    lowered = run("clear", "01", thresholds={**THRESHOLDS, "fall_height": -100.0})
    assert verdicts(lowered)["hallway-fall"] == "PASS"
    summary = {s["id"]: s["summary"] for s in payload["steps"]}
    assert "fall height" not in summary["hallway-wall-contact"]
    assert "m < 0.10 m" in summary["hallway-fall"]  # the absolute fall_height, not a nominal ratio


def test_a_contact_trial_fails_the_wall_step_with_the_events_depth():
    payload = run("contact", "01")
    got = {s["id"]: s for s in payload["steps"]}
    assert got["hallway-wall-contact"]["verdict"] == "FAIL"
    assert "wall-left" in got["hallway-wall-contact"]["summary"]
    assert "0.13" in got["hallway-wall-contact"]["summary"]
    assert got["hallway-exit-reached"]["verdict"] == "FAIL"
    assert got["hallway-lateral-limit"]["verdict"] == "FAIL"


def test_an_unbound_body_contact_is_not_evaluated_and_the_other_steps_still_run():
    _, binding = paths("clear", "01")
    broken = load(binding)
    del broken["observables"]["body_contact"]
    broken["bound_observables"].remove("body_contact")
    broken["unbound"] = [{"id": "body_contact", "reason": "producer-does-not-carry"}]
    payload = runner.run_trial(paths("clear", "01")[0], broken, THRESHOLDS, WORLD)
    got = {s["id"]: s for s in payload["steps"]}
    assert got["hallway-wall-contact"]["verdict"] == "NOT_EVALUATED"
    assert got["hallway-wall-contact"]["reason"] == "unbound_observable"
    assert "body_contact" in got["hallway-wall-contact"]["summary"]
    assert got["hallway-exit-reached"]["verdict"] == "PASS"
    assert list(validator("scenario-result.schema.json").iter_errors(payload)) == []


def test_an_unbound_base_leaves_exit_and_lateral_not_evaluated():
    _, binding = paths("clear", "01")
    broken = load(binding)
    del broken["observables"]["base"]
    broken["bound_observables"].remove("base")
    broken["unbound"] = [{"id": "base", "reason": "robot-entry-missing"}]
    payload = runner.run_trial(paths("clear", "01")[0], broken, THRESHOLDS, WORLD)
    got = verdicts(payload)
    assert got["hallway-exit-reached"] == got["hallway-lateral-limit"] == "NOT_EVALUATED"
    assert got["hallway-wall-contact"] == "PASS"
    reasons = {s.get("reason") for s in payload["steps"] if s["verdict"] == "NOT_EVALUATED"}
    assert reasons == {"unbound_observable"}


def test_an_unknown_step_is_not_evaluated_with_that_reason():
    payload = run("clear", "01", steps=["hallway-fall", "hallway-teleport"])
    assert [(s["id"], s["verdict"], s.get("reason")) for s in payload["steps"]] == [
        ("hallway-fall", "FAIL", None),
        ("hallway-teleport", "NOT_EVALUATED", "unknown_step"),
    ]


def test_a_recording_that_never_declares_the_contacts_channel_is_inconclusive_not_clear(tmp_path):
    mcap, binding = synthetic(tmp_path, contacts=False)
    binding["observables"]["body_contact"] = {
        "topic": "/wall_contacts",
        "encoding": "json",
        "schema": "s",
        "fields": {"wall": "wall", "start": "start", "end": "end", "depth": "depth"},
        "frame": "world",
    }
    binding["bound_observables"].append("body_contact")
    binding["unbound"] = []
    payload = runner.run_trial(mcap, binding, THRESHOLDS, WORLD)
    got = {s["id"]: s for s in payload["steps"]}
    assert got["hallway-wall-contact"]["verdict"] == "INCONCLUSIVE"
    assert "/wall_contacts" in got["hallway-wall-contact"]["summary"]


def test_the_topic_and_field_paths_come_from_the_binding_not_from_the_runner(tmp_path):
    mcap, binding = synthetic(tmp_path, topic="/custom/pose", pose_path=("where", "at"))
    payload = runner.run_trial(mcap, binding, THRESHOLDS, WORLD)
    got = verdicts(payload)
    assert got["hallway-exit-reached"] == "PASS" and got["hallway-fall"] == "PASS"
    assert got["hallway-wall-contact"] == "NOT_EVALUATED"
    wrong = copy.deepcopy(binding)
    wrong["observables"]["base"]["topic"] = "/base_pose"  # the runner does not guess a topic
    assert (
        verdicts(runner.run_trial(mcap, wrong, THRESHOLDS, WORLD))["hallway-exit-reached"]
        == "INCONCLUSIVE"
    )


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda b: b["recording"].update(sha256="0" * 64), "sha256"),
        (lambda b: b["observables"]["base"].update(encoding="protobuf"), "encoding"),
        (lambda b: b["observables"]["base"].update(frame="map"), "frame"),
        (lambda b: b["observables"]["base"]["fields"].pop("y"), "base.*y"),
        (lambda b: b.update(kind="producer"), "kind"),
        (lambda b: b["bound_observables"].pop(), "bound_observables"),
        (lambda b: b["observables"]["base"].update(topic=["/a", "/b"]), "topic"),
    ],
)
def test_a_binding_the_runner_cannot_trust_is_an_error_not_a_guess(tmp_path, mutate, message):
    mcap, binding = synthetic(tmp_path)
    mutate(binding)
    with pytest.raises(EvaluationError, match=message):
        runner.run_trial(mcap, binding, THRESHOLDS, WORLD)


def test_the_fall_rule_is_the_absolute_fall_height_everywhere():
    for path in (ROOT / "README.md", *sorted((ROOT / "docs").rglob("*.md"))):
        text = path.read_text()
        assert "P% of nominal" not in text and "60% of nominal" not in text, path
    readme = " ".join((ROOT / "README.md").read_text().split())
    assert "the base height stays above the fall height" in readme
    assert "fall_height" in readme and "MCAP" in readme
