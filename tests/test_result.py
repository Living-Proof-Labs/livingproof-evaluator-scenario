# SPDX-License-Identifier: Apache-2.0
"""The per-trial result document: descriptor, icon, and empty findings."""

import hashlib
import json
from pathlib import Path

from livingproof_evaluator_scenario.checks import INSUFFICIENT
from livingproof_evaluator_scenario.result import (
    DISPLAY_NAME,
    ICON,
    SHORT_TITLE,
    package_version,
    trial_result,
    write_run,
)

FIXTURES = Path(__file__).parent / "fixtures" / "run-43159586597"
EXPECTED = json.loads((FIXTURES / "expected.json").read_text(encoding="utf-8"))
WHEN = "2026-11-12T05:11:41Z"


def _one(name="playground"):
    recorded = EXPECTED["configurations"][name]
    trial = recorded["trials"][0]
    observation = json.loads((FIXTURES / trial["observation"]).read_text(encoding="utf-8"))
    digest = hashlib.sha256((FIXTURES / trial["observation"]).read_bytes()).hexdigest()
    document = trial_result(
        observation,
        recorded["thresholds"],
        trial["id"],
        seed=("trial", trial["index"]),
        inputs=[{"role": "observation", "uri": "trials/trial-01.json", "sha256": digest}],
        started_at=WHEN,
        completed_at=WHEN,
    )
    return document, trial


def test_descriptor_names_the_scenario_evaluator_and_inlines_the_icon():
    document, _trial = _one()
    assert document["format"] == "livingproof-evaluator-result/1.1.0"
    assert document["evaluator"]["id"] == "livingproof-scenario"
    assert document["evaluator"]["execution"] == "deterministic"
    assert document["evaluator"]["publisher"] == "Living Proof Labs"
    assert document["evaluator"]["display_name"] == DISPLAY_NAME
    assert document["evaluator"]["version"] == package_version()
    descriptor = document["descriptor"]
    assert descriptor["title"] == "Scenario evaluator"
    assert descriptor["title"] == document["evaluator"]["display_name"]
    assert descriptor["short_title"] == SHORT_TITLE == "Scenario eval"
    assert descriptor["version"] == document["evaluator"]["version"]
    assert descriptor["tier"] == "verdict"
    assert descriptor["findings"] == []
    assert "grade" not in descriptor
    assert descriptor["icon"] == document["evaluator"]["icon"] == ICON
    assert descriptor["icon_accessible_name"] == "Scenario evaluator"
    assert "<title" not in ICON
    assert "#0E8785" not in ICON
    assert "currentColor" in ICON
    assert 'd="M6.5 7L10.5 11L17.5 4"' in ICON


def test_versions_come_from_package_metadata_not_a_literal(monkeypatch):
    seen = []

    def fake(name):
        seen.append(name)
        return "9.9.9"

    monkeypatch.setattr("importlib.metadata.version", fake)
    document, _trial = _one()
    assert seen == ["livingproof-evaluator-scenario"]
    assert document["evaluator"]["version"] == "9.9.9"
    assert document["descriptor"]["version"] == "9.9.9"
    monkeypatch.undo()
    installed = package_version()
    assert installed != "9.9.9"
    assert installed != "0.0.0"


def test_playground_steps_pass_and_stock_steps_keep_the_failed_checks():
    playground, trial = _one("playground")
    assert trial["status"] == "PASS"
    assert [step["verdict"] for step in playground["scenario"]["steps"]] == ["PASS"] * 4
    assert playground["scenario"]["trial_id"] == "playground-seed-01"
    stock, failed = _one("stock")
    by_id = {step["id"]: step for step in stock["scenario"]["steps"]}
    stored = {item["evaluator"]: item for item in failed["assessments"]}
    assert by_id["hallway-exit-reached"]["verdict"] == "PASS"
    assert by_id["hallway-fall"]["verdict"] == "PASS"
    assert by_id["hallway-lateral-limit"]["verdict"] == "FAIL"
    assert by_id["hallway-wall-contact"]["verdict"] == "FAIL"
    for ident, step in by_id.items():
        assert step["summary"] == stored[ident]["rationale"]
    assert stock["descriptor"]["findings"] == []


def test_insufficient_evidence_is_inconclusive_on_the_contract_step():
    document = trial_result(
        {},
        {"time_limit": 27.0, "lateral_limit": 0.49, "half_width": 0.75, "fall_height": 0.5},
        "playground-seed-01",
        seed=("trial", 1),
        inputs=[{"role": "observation", "uri": "trials/trial-01.json", "sha256": "ab" * 32}],
        started_at=WHEN,
        completed_at=WHEN,
    )
    assert [step["verdict"] for step in document["scenario"]["steps"]] == ["INCONCLUSIVE"] * 4
    assert INSUFFICIENT == "INSUFFICIENT_EVIDENCE"


def test_write_run_stores_one_file_per_trial(tmp_path):
    recorded = EXPECTED["configurations"]["playground"]
    written = write_run(
        FIXTURES / "playground" / "manifest.json",
        recorded["thresholds"],
        tmp_path,
        started_at=WHEN,
        completed_at=WHEN,
    )
    assert [path.name for path in written] == [
        "playground-seed-01.json",
        "playground-seed-02.json",
        "playground-seed-03.json",
    ]
    for path, trial in zip(written, recorded["trials"], strict=True):
        document = json.loads(path.read_text(encoding="utf-8"))
        assert document["scenario"]["trial_id"] == trial["id"]
        assert document["evaluator"]["id"] == "livingproof-scenario"
        assert document["descriptor"]["findings"] == []
        assert "assessments" not in document
