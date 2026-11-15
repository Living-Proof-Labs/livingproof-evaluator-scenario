# SPDX-License-Identifier: Apache-2.0
"""Review probes for threshold provenance beyond the PR's stability tests.

The head already checks that identical limits are byte-stable and that
different limits change the digest. These cover the written file against
the cited digest after the file is altered, a caller-supplied spoofed
thresholds entry, historical results without the new input, and the
collector's rule that only result documents are appended.
"""

from __future__ import annotations

import hashlib
import json
import re
from functools import lru_cache
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from livingproof_evaluator_scenario.result import (
    THRESHOLDS_FILENAME,
    THRESHOLDS_ROLE,
    trial_result,
    write_run,
)

FIXTURES = Path(__file__).parent / "fixtures" / "run-43159586597"
STORED = Path(__file__).parent / "fixtures" / "lpv-run-43402628666"
SCHEMA = Path(__file__).parent / "fixtures" / "livingproof-evaluator-v1.0.0"
MANIFEST = FIXTURES / "playground" / "manifest.json"
WHEN = "2026-11-12T05:11:41Z"
LIMITS = {"time_limit": 27.0, "lateral_limit": 0.49, "half_width": 0.75, "fall_height": 0.5}
OTHER = {**LIMITS, "time_limit": 99.0}
RESULT_FORMAT = re.compile(r"^livingproof-evaluator-result/1\.\d+\.\d+$")


def _write(out, thresholds=LIMITS):
    return write_run(MANIFEST, thresholds, out, started_at=WHEN, completed_at=WHEN)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _cited(document):
    found = [item for item in document["inputs"] if item["role"] == THRESHOLDS_ROLE]
    assert len(found) == 1
    return found[0]


def _file_errors(directory: Path) -> list[str]:
    """Compare each result's thresholds citation to thresholds.json in the same directory."""
    path = directory / THRESHOLDS_FILENAME
    errors = []
    for result in sorted(directory.glob("*-seed-*.json")):
        cited = _cited(json.loads(result.read_text(encoding="utf-8")))
        if not path.is_file():
            errors.append(
                f"thresholds.json missing: cited sha256 {cited['sha256']} but the file is missing"
            )
            continue
        actual = _sha(path)
        if actual != cited["sha256"]:
            errors.append(
                f"thresholds.json mismatch: cited sha256 {cited['sha256']} != file sha256 {actual}"
            )
    return errors


@lru_cache(maxsize=1)
def _validator():
    provenance = json.loads((SCHEMA / "PROVENANCE.json").read_text(encoding="utf-8"))
    resources = []
    for name in provenance["files"]:
        contents = json.loads((SCHEMA / "schema" / name).read_text(encoding="utf-8"))
        resources.append((contents["$id"], Resource.from_contents(contents)))
    schema = json.loads((SCHEMA / "schema" / "evaluator-result.schema.json").read_text())
    return Draft202012Validator(schema, registry=Registry().with_resources(resources))


def test_the_cited_digest_matches_the_written_file_and_fails_when_that_file_is_altered(
    tmp_path,
):
    written = _write(tmp_path / "ok")
    digest = _sha(tmp_path / "ok" / THRESHOLDS_FILENAME)
    for path in written:
        cited = _cited(json.loads(path.read_text(encoding="utf-8")))
        assert cited == {
            "role": THRESHOLDS_ROLE,
            "uri": THRESHOLDS_FILENAME,
            "sha256": digest,
        }
    assert _file_errors(tmp_path / "ok") == []

    modified = tmp_path / "modified"
    _write(modified)
    recorded = json.loads((modified / THRESHOLDS_FILENAME).read_text(encoding="utf-8"))
    recorded["limits"]["time_limit"] = 99.0
    (modified / THRESHOLDS_FILENAME).write_text(
        json.dumps(recorded, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    errors = _file_errors(modified)
    assert errors and "mismatch" in errors[0], errors

    pretty = tmp_path / "reformatted"
    _write(pretty)
    recorded = json.loads((pretty / THRESHOLDS_FILENAME).read_bytes())
    (pretty / THRESHOLDS_FILENAME).write_text(
        json.dumps(recorded, indent=2) + "\n", encoding="utf-8"
    )
    errors = _file_errors(pretty)
    assert errors and "mismatch" in errors[0], errors

    other = tmp_path / "other"
    _write(other, OTHER)
    swapped = tmp_path / "swapped"
    _write(swapped)
    (swapped / THRESHOLDS_FILENAME).write_bytes((other / THRESHOLDS_FILENAME).read_bytes())
    errors = _file_errors(swapped)
    assert errors and "mismatch" in errors[0], errors

    missing = tmp_path / "missing"
    _write(missing)
    (missing / THRESHOLDS_FILENAME).unlink()
    errors = _file_errors(missing)
    assert errors and "missing" in errors[0], errors


def test_a_caller_supplied_thresholds_input_is_replaced_with_the_canonical_digest(
    tmp_path,
):
    written = _write(tmp_path)
    digest = _sha(tmp_path / THRESHOLDS_FILENAME)
    observation = json.loads(
        (FIXTURES / "playground" / "trials" / "trial-01.json").read_text(encoding="utf-8")
    )
    document = trial_result(
        observation,
        LIMITS,
        "playground-seed-01",
        inputs=[
            {"role": "observation", "uri": "spoofed.json", "sha256": "ab" * 32},
            {"role": "thresholds", "uri": "evil.json", "sha256": "cd" * 32},
        ],
        started_at=WHEN,
        completed_at=WHEN,
    )
    cited = _cited(document)
    assert cited == {
        "role": THRESHOLDS_ROLE,
        "uri": THRESHOLDS_FILENAME,
        "sha256": digest,
    }
    assert cited["sha256"] != "cd" * 32
    assert [item["role"] for item in document["inputs"]] == [
        "observation",
        THRESHOLDS_ROLE,
    ]
    assert written


def test_stored_results_without_a_thresholds_input_still_match_the_contract_schema():
    stored = sorted(STORED.glob("*-result-01.json"))
    assert stored
    for path in stored:
        document = json.loads(path.read_text(encoding="utf-8"))
        assert document["format"] == "livingproof-evaluator-result/1.1.0"
        assert [item["role"] for item in document["inputs"]] == [
            "observation",
            "manifest",
        ]
        errors = sorted(
            _validator().iter_errors(document), key=lambda error: list(error.absolute_path)
        )
        assert [error.message for error in errors] == [], path.name


def test_a_collector_skips_thresholds_json_and_keeps_the_thresholds_reference(tmp_path):
    written = _write(tmp_path)
    collected = []
    skipped = []
    for path in sorted(tmp_path.rglob("*.json")):
        document = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(document, dict) and isinstance(document.get("format"), str):
            if RESULT_FORMAT.fullmatch(document["format"]):
                collected.append(document)
                continue
        skipped.append(path.name)
    assert skipped == [THRESHOLDS_FILENAME]
    assert [path.name for path in written] == [
        item["scenario"]["trial_id"] + ".json" for item in collected
    ]
    digest = _sha(tmp_path / THRESHOLDS_FILENAME)
    for document in collected:
        assert _cited(document)["sha256"] == digest
