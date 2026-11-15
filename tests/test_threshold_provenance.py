# SPDX-License-Identifier: Apache-2.0
"""The limits a result graded are a stable, digest-bound input.

The same observation and manifest with different limits produce different
threshold digests. Identical limits produce byte-identical threshold files
and byte-identical result files. Written results are checked against the
livingproof-evaluator v1.0.0 result schema.
"""

import hashlib
import json
import re
from functools import lru_cache
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from livingproof_evaluator_scenario.__main__ import main
from livingproof_evaluator_scenario.compat.recorded import (
    PARAMETERS_COMMIT,
    PARAMETERS_PATH,
    PARAMETERS_REPOSITORY,
    PARAMETERS_SHA256,
    PARAMETERS_TAG,
    parameters_document,
)
from livingproof_evaluator_scenario.result import (
    THRESHOLDS_FILENAME,
    THRESHOLDS_ROLE,
    package_version,
    write_run,
)

FIXTURES = Path(__file__).parent / "fixtures" / "run-43159586597"
SCHEMA = Path(__file__).parent / "fixtures" / "livingproof-evaluator-v1.0.0"
WHEN = "2026-11-12T05:11:41Z"
MANIFEST = FIXTURES / "playground" / "manifest.json"
LIMITS = {"time_limit": 27.0, "lateral_limit": 0.49, "half_width": 0.75, "fall_height": 0.5}
_SEMVER = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)
_DEV = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)\.dev\d+$")


def _write(out, thresholds, parameters=None):
    return write_run(
        MANIFEST,
        thresholds,
        out,
        started_at=WHEN,
        completed_at=WHEN,
        parameters=parameters,
    )


def _thresholds(document):
    found = [item for item in document["inputs"] if item["role"] == THRESHOLDS_ROLE]
    assert len(found) == 1
    return found[0]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_limits() -> bytes:
    """The serializer's rules, written out so a change to them fails the test."""
    document = {
        "limits": {
            "exit_segment": 0.75,
            "fall_height": 0.5,
            "lateral_limit": 0.49,
            "time_limit": 27.0,
        },
        "parameters": {
            "commit": PARAMETERS_COMMIT,
            "path": PARAMETERS_PATH,
            "repository": PARAMETERS_REPOSITORY,
            "sha256": PARAMETERS_SHA256,
            "tag": PARAMETERS_TAG,
        },
    }
    text = json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return (text + "\n").encode("utf-8")


def test_schema_copies_match_the_v1_0_0_provenance():
    provenance = json.loads((SCHEMA / "PROVENANCE.json").read_text(encoding="utf-8"))
    assert provenance["repository"] == "Living-Proof-Labs/livingproof-evaluator"
    assert provenance["tag"] == "v1.0.0"
    assert provenance["commit"] == "9b865bc530a09d763e62cf602b35b5bb57232c0b"
    for name, meta in provenance["files"].items():
        assert _sha(SCHEMA / "schema" / name) == meta["sha256"], name


@lru_cache(maxsize=1)
def _validator():
    provenance = json.loads((SCHEMA / "PROVENANCE.json").read_text(encoding="utf-8"))
    resources = []
    for name in provenance["files"]:
        contents = json.loads((SCHEMA / "schema" / name).read_text(encoding="utf-8"))
        resources.append((contents["$id"], Resource.from_contents(contents)))
    schema = json.loads((SCHEMA / "schema" / "evaluator-result.schema.json").read_text())
    return Draft202012Validator(schema, registry=Registry().with_resources(resources))


def _schema_errors(document) -> list[str]:
    errors = sorted(_validator().iter_errors(document), key=lambda error: list(error.absolute_path))
    return [
        f"{'/'.join(map(str, error.absolute_path)) or '<root>'}: {error.message}"
        for error in errors
    ]


def test_identical_limits_have_byte_identical_provenance_and_different_limits_do_not(tmp_path):
    reordered = {
        "unused": 1,
        "fall_height": 0.5,
        "half_width": 0.75,
        "lateral_limit": 0.49,
        "time_limit": 27.0,
    }
    aliased = {
        "time_limit": 27.0,
        "lateral_limit": 0.49,
        "exit_segment": 0.75,
        "fall_height": 0.5,
    }
    changed = {**LIMITS, "time_limit": 99.0}
    first = _write(tmp_path / "first", LIMITS)
    second = _write(tmp_path / "second", reordered)
    third = _write(tmp_path / "third", aliased)
    other = _write(tmp_path / "other", changed)

    for path, again, aliased_path in zip(first, second, third, strict=True):
        assert path.read_bytes() == again.read_bytes() == aliased_path.read_bytes()
    for left, right in (
        (tmp_path / "first", tmp_path / "second"),
        (tmp_path / "first", tmp_path / "third"),
    ):
        assert (left / THRESHOLDS_FILENAME).read_bytes() == (
            right / THRESHOLDS_FILENAME
        ).read_bytes()

    expected = _canonical_limits()
    raw = (tmp_path / "first" / THRESHOLDS_FILENAME).read_bytes()
    assert raw == expected
    recorded = json.loads(raw)
    assert recorded["limits"] == {
        "exit_segment": 0.75,
        "fall_height": 0.5,
        "lateral_limit": 0.49,
        "time_limit": 27.0,
    }
    assert recorded["parameters"] == {
        "repository": PARAMETERS_REPOSITORY,
        "tag": PARAMETERS_TAG,
        "commit": PARAMETERS_COMMIT,
        "path": PARAMETERS_PATH,
        "sha256": PARAMETERS_SHA256,
    }

    digest = hashlib.sha256(expected).hexdigest()
    other_raw = (tmp_path / "other" / THRESHOLDS_FILENAME).read_bytes()
    assert other_raw != expected
    assert json.loads(other_raw)["limits"]["time_limit"] == 99.0
    for path, again in zip(first, other, strict=True):
        document = json.loads(path.read_text(encoding="utf-8"))
        different = json.loads(again.read_text(encoding="utf-8"))
        cited = _thresholds(document)
        assert set(cited) == {"role", "uri", "sha256"}
        assert cited == {"role": THRESHOLDS_ROLE, "uri": THRESHOLDS_FILENAME, "sha256": digest}
        assert cited["sha256"] == _sha(tmp_path / "first" / THRESHOLDS_FILENAME)
        assert _thresholds(different)["sha256"] != digest
        assert _thresholds(different)["sha256"] == _sha(tmp_path / "other" / THRESHOLDS_FILENAME)
        evidence = [item for item in document["inputs"] if item["role"] != THRESHOLDS_ROLE]
        assert evidence == [item for item in different["inputs"] if item["role"] != THRESHOLDS_ROLE]
        assert [item["role"] for item in document["inputs"]] == [
            "observation",
            "manifest",
            THRESHOLDS_ROLE,
        ]


def test_an_unknown_parameter_document_records_its_digest_without_a_tag(tmp_path):
    parameters = parameters_document()
    parameters["$comment"] = "not the vendored file"
    written = _write(tmp_path, LIMITS, parameters=parameters)
    recorded = json.loads((tmp_path / THRESHOLDS_FILENAME).read_text(encoding="utf-8"))
    assert set(recorded["parameters"]) == {"sha256"}
    assert recorded["parameters"]["sha256"] != PARAMETERS_SHA256
    assert "v2.2.0" not in (tmp_path / THRESHOLDS_FILENAME).read_text(encoding="utf-8")
    assert _thresholds(json.loads(written[0].read_text(encoding="utf-8")))["sha256"] == _sha(
        tmp_path / THRESHOLDS_FILENAME
    )


def test_the_command_writes_the_same_file_for_the_same_limits(tmp_path):
    pretty = tmp_path / "pretty.json"
    compact = tmp_path / "compact.json"
    pretty.write_text(json.dumps(LIMITS, indent=4) + "\n", encoding="utf-8")
    compact.write_text(
        json.dumps({"fall_height": 0.5, "time_limit": 27.0, **LIMITS}), encoding="utf-8"
    )
    out_pretty = tmp_path / "pretty-out"
    out_compact = tmp_path / "compact-out"
    args = ["--started-at", WHEN, "--completed-at", WHEN]
    assert main([str(MANIFEST), "--thresholds", str(pretty), "--out", str(out_pretty), *args]) == 0
    assert (
        main([str(MANIFEST), "--thresholds", str(compact), "--out", str(out_compact), *args]) == 0
    )
    assert (out_pretty / THRESHOLDS_FILENAME).read_bytes() == _canonical_limits()
    assert (out_pretty / THRESHOLDS_FILENAME).read_bytes() == (
        out_compact / THRESHOLDS_FILENAME
    ).read_bytes()
    assert (out_pretty / "playground-seed-01.json").read_bytes() == (
        out_compact / "playground-seed-01.json"
    ).read_bytes()


def test_written_results_match_the_evaluator_contract_schema(tmp_path, monkeypatch):
    written = _write(tmp_path / "dev", LIMITS)
    version = package_version()
    for path in written:
        document = json.loads(path.read_text(encoding="utf-8"))
        errors = _schema_errors(document)
        if _SEMVER.fullmatch(version):
            assert errors == []
        else:
            assert _DEV.fullmatch(version), version
            assert errors
            assert all(item.startswith("evaluator/version:") for item in errors), errors

    monkeypatch.setattr("livingproof_evaluator_scenario.result.package_version", lambda: "1.2.0")
    released = _write(tmp_path / "released", LIMITS)
    for path in released:
        document = json.loads(path.read_text(encoding="utf-8"))
        assert document["evaluator"]["version"] == "1.2.0"
        assert document["descriptor"]["version"] == "1.2.0"
        assert _schema_errors(document) == []
        assert _thresholds(document)["sha256"] == hashlib.sha256(_canonical_limits()).hexdigest()
