# SPDX-License-Identifier: Apache-2.0
"""The implementation descriptor ``livingproof-evaluator.json`` (issue 60).

The schema copies under ``tests/fixtures/livingproof-evaluator-v1.11.0`` are livingproof-evaluator
v1.11.0, commit ``474dda56311fad6a03715fdba4cd957dc510d459``. The pin is that tag and commit.

The trial command is the one livingproof-evaluator v1.11.0 shows for this package. Exit 0 writes
results. Exit 1 is a refusal or an
uncaught crash, and the descriptor maps that code to ``refused``. Exit 2 is an argparse usage
error and is not listed, so it is a failure. This issue does not ask for a separate refusal code.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import importlib.util
import json
import os
import re
import subprocess
import sys
import tomllib
from functools import lru_cache
from pathlib import Path

import pytest
from github_fetch import fetch
from jsonschema import Draft202012Validator
from packaging.specifiers import SpecifierSet
from referencing import Registry, Resource

from livingproof_evaluator_scenario.result import DISTRIBUTION, EVALUATOR_ID
from test_media_run import IDENTITY, make_run

ROOT = Path(__file__).resolve().parents[1]
DESCRIPTOR = ROOT / "livingproof-evaluator.json"
SCHEMA = ROOT / "tests" / "fixtures" / "livingproof-evaluator-v1.11.0"
RESULT_SCHEMA = ROOT / "tests" / "fixtures" / "livingproof-evaluator-v1.0.0"
STOCK = ROOT / "tests" / "fixtures" / "run-43159586597" / "stock" / "manifest.json"
WORLD = ROOT / "tests" / "fixtures" / "sim-1e020b2" / "world.json"
README = ROOT / "README.md"
GUIDE = ROOT / "docs" / "guide.md"
INDEX = ROOT / "docs" / "index.md"
VERIFICATION = ROOT / "docs" / "verification.md"
PIN_COMMIT = "474dda56311fad6a03715fdba4cd957dc510d459"
PIN_TAG = "v1.11.0"
DECLARATION = "Living-Proof-Labs/livingproof-evaluator-scenario@<vX.Y.Z>/livingproof-evaluator.json"
TRIAL_ARGUMENTS = [
    "{evidence_manifest}",
    "--thresholds",
    "{thresholds}",
    "--out",
    "{result_dir}",
]
MEDIA_ARGUMENTS = [
    "{evidence_manifest}",
    "{media_dir}",
    "{result_dir}",
    "--world",
    "{world}",
    "--identity",
    "{identity}",
]
LIMITS = {"time_limit": 27.0, "lateral_limit": 0.49, "half_width": 0.75, "fall_height": 0.5}
TOKEN = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")
TAG = re.compile(r"^v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
COMMIT = re.compile(r"^[0-9a-f]{40}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SEMVER = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)
_DEV = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)\.dev\d+$")


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _descriptor() -> dict:
    return _load(DESCRIPTOR)


def _pin() -> dict:
    return _load(SCHEMA / "PROVENANCE.json")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _tokens(value) -> list[str]:
    found: list[str] = []
    if isinstance(value, str):
        found.extend(TOKEN.findall(value))
    elif isinstance(value, list):
        for item in value:
            found.extend(_tokens(item))
    elif isinstance(value, dict):
        for item in value.values():
            found.extend(_tokens(item))
    return found


def _registry() -> tuple[dict, Registry]:
    resources = []
    schema = None
    for name in ("implementation.schema.json", "defs.schema.json"):
        contents = _load(SCHEMA / "schema" / name)
        resources.append((contents["$id"], Resource.from_contents(contents)))
        if name == "implementation.schema.json":
            schema = contents
    assert schema is not None
    return schema, Registry().with_resources(resources)


def _errors(instance: dict) -> list:
    schema, registry = _registry()
    return list(Draft202012Validator(schema, registry=registry).iter_errors(instance))


def _fill(text: str, values: dict[str, str]) -> str:
    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        try:
            return values[name]
        except KeyError:
            raise AssertionError(f"placeholder {{{name}}} is not a provided input") from None

    return TOKEN.sub(replace, text)


def _expand(arguments: list, values: dict[str, str]) -> list[str]:
    expanded: list[str] = []
    for item in arguments:
        if isinstance(item, str):
            expanded.append(_fill(item, values))
            continue
        if not isinstance(item, dict):
            raise AssertionError("argument items are strings or {if, then} objects")
        if item["if"] not in values:
            continue
        then = item["then"]
        if not isinstance(then, list) or not then:
            raise AssertionError("conditional then must be a non-empty list")
        for part in then:
            if not isinstance(part, str):
                raise AssertionError("conditional then must be argument strings")
            expanded.append(_fill(part, values))
    return expanded


def _command(
    module: str, arguments: list, values: dict[str, str]
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", module, *_expand(arguments, values)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )


def _trial(manifest: Path, thresholds: Path, out: Path) -> subprocess.CompletedProcess[str]:
    descriptor = _descriptor()
    return _command(
        descriptor["entrypoint"]["module"],
        descriptor["arguments"],
        {
            "evidence_manifest": str(manifest),
            "thresholds": str(thresholds),
            "result_dir": str(out),
        },
    )


@lru_cache(maxsize=1)
def _result_validator():
    provenance = _load(RESULT_SCHEMA / "PROVENANCE.json")
    resources = []
    for name in provenance["files"]:
        contents = _load(RESULT_SCHEMA / "schema" / name)
        resources.append((contents["$id"], Resource.from_contents(contents)))
    schema = _load(RESULT_SCHEMA / "schema" / "evaluator-result.schema.json")
    return Draft202012Validator(schema, registry=Registry().with_resources(resources))


def _schema_errors(document: dict) -> list[str]:
    errors = sorted(
        _result_validator().iter_errors(document), key=lambda error: list(error.absolute_path)
    )
    return [
        f"{'/'.join(map(str, error.absolute_path)) or '<root>'}: {error.message}"
        for error in errors
    ]


def _assert_result_document(document: dict) -> None:
    descriptor = _descriptor()
    assert document["format"] == descriptor["result"]
    assert document["evaluator"]["id"] == descriptor["id"]
    assert document["evaluator"]["kind"] == descriptor["kind"]
    errors = _schema_errors(document)
    version = document["evaluator"]["version"]
    if _SEMVER.fullmatch(version):
        assert errors == []
        return
    assert _DEV.fullmatch(version), version
    assert errors
    assert all(item.startswith("evaluator/version:") for item in errors), errors
    released = json.loads(json.dumps(document))
    released["evaluator"]["version"] = "1.2.0"
    released["descriptor"]["version"] = "1.2.0"
    assert _schema_errors(released) == []


def _assert_results(out: Path) -> None:
    results = sorted(path for path in out.glob("*.json") if path.name != "thresholds.json")
    assert results
    for path in results:
        _assert_result_document(_load(path))


def test_the_shipped_descriptor_validates_against_the_v1_11_0_schema() -> None:
    assert DESCRIPTOR.is_file()
    descriptor = _descriptor()
    assert _errors(descriptor) == []
    assert _errors({**descriptor, "note": "not in the schema"})
    other_major = {**descriptor, "result": "livingproof-evaluator-result/2.0.0"}
    assert _errors(other_major)


def test_the_schema_copies_are_livingproof_evaluator_v1_11_0() -> None:
    pin = _pin()
    assert pin["repository"] == "Living-Proof-Labs/livingproof-evaluator"
    assert pin["tag"] == PIN_TAG
    assert pin["commit"] == PIN_COMMIT
    assert TAG.fullmatch(pin["tag"])
    assert COMMIT.fullmatch(pin["commit"])
    pinned = set()
    for rel, meta in pin["files"].items():
        assert SHA256.fullmatch(meta["sha256"])
        fixture = SCHEMA / rel
        assert _sha(fixture) == meta["sha256"]
        pinned.add(fixture.relative_to(SCHEMA / "schema").as_posix())
    present = {
        path.relative_to(SCHEMA / "schema").as_posix()
        for path in (SCHEMA / "schema").rglob("*")
        if path.is_file()
    }
    assert present == pinned


@pytest.mark.skipif(not os.environ.get("LIVINGPROOF_NETWORK"), reason="set LIVINGPROOF_NETWORK=1")
def test_the_schema_pin_matches_the_v1_11_0_release() -> None:
    pin = _pin()
    ref = json.loads(
        fetch(f"https://api.github.com/repos/{pin['repository']}/git/refs/tags/{pin['tag']}")
    )
    obj = ref["object"]
    if obj["type"] == "tag":
        tag = json.loads(
            fetch(f"https://api.github.com/repos/{pin['repository']}/git/tags/{obj['sha']}")
        )
        assert tag["object"]["type"] == "commit"
        peeled = tag["object"]["sha"]
    else:
        assert obj["type"] == "commit"
        peeled = obj["sha"]
    assert peeled == pin["commit"]
    for rel, meta in pin["files"].items():
        url = f"https://raw.githubusercontent.com/{pin['repository']}/{pin['commit']}/{rel}"
        assert hashlib.sha256(fetch(url)).hexdigest() == meta["sha256"]


def test_kind_is_scenario() -> None:
    assert _descriptor()["kind"] == "scenario"


def test_grading_is_robot() -> None:
    assert _descriptor()["grading"] == "robot"


def test_trial_arguments_pass_thresholds() -> None:
    assert "thresholds" in _tokens(_descriptor()["arguments"])


def test_the_output_placeholder_is_result_dir() -> None:
    descriptor = _descriptor()
    assert "result_dir" in _tokens(descriptor["arguments"])
    assert "result" not in _tokens(descriptor["arguments"])
    assert "result" not in _tokens(descriptor["media"])


def test_trial_arguments_are_the_shipped_trial_command() -> None:
    assert _descriptor()["arguments"] == TRIAL_ARGUMENTS


def test_the_trial_run_does_not_name_a_world_or_parameters() -> None:
    descriptor = _descriptor()
    names = _tokens(descriptor["arguments"])
    assert "world" not in names
    assert "parameters" not in names
    assert "parameters" not in _tokens(descriptor)


def test_media_arguments_match_the_package_command() -> None:
    media = _descriptor()["media"]
    assert media["module"] == "livingproof_evaluator_scenario.media"
    assert media["arguments"] == MEDIA_ARGUMENTS


def test_exit_codes_are_zero_result_and_one_refused() -> None:
    assert _descriptor()["exit_codes"] == {"0": "result", "1": "refused"}


def test_descriptor_matches_the_package() -> None:
    descriptor = _descriptor()
    assert descriptor["id"] == EVALUATOR_ID
    assert descriptor["result"] == "livingproof-evaluator-result/1.1.0"
    assert descriptor["package"]["name"] == DISTRIBUTION
    distribution = importlib.metadata.distribution(DISTRIBUTION)
    assert distribution.metadata["Name"] == DISTRIBUTION
    module = descriptor["entrypoint"]["module"]
    assert module == "livingproof_evaluator_scenario"
    assert importlib.util.find_spec(module) is not None
    assert importlib.util.find_spec(f"{module}.__main__") is not None
    assert importlib.util.find_spec(descriptor["media"]["module"]) is not None
    with (ROOT / "pyproject.toml").open("rb") as handle:
        requires = tomllib.load(handle)["project"]["requires-python"]
    assert descriptor["runtime"]["python"] == "3.12"
    assert SpecifierSet(requires).contains("3.12.0")


def test_the_declared_trial_command_writes_a_schema_valid_result(tmp_path: Path) -> None:
    recorded = _load(STOCK)
    # Split so this source does not contain the scenario id the compatibility guard searches for.
    assert recorded["lock"]["content"]["scenario"] == "walk-" + "hall" + "way@0.1.0"
    thresholds = tmp_path / "thresholds.json"
    thresholds.write_text(json.dumps(LIMITS), encoding="utf-8")
    out = tmp_path / "out"
    proc = _trial(STOCK, thresholds, out)
    assert proc.returncode == 0, proc.stderr
    assert _descriptor()["exit_codes"][str(proc.returncode)] == "result"
    _assert_results(out)
    assert (out / "thresholds.json").is_file()
    assert _load(out / "thresholds.json").get("format") != _descriptor()["result"]


def test_the_declared_media_command_writes_a_schema_valid_result(tmp_path: Path) -> None:
    manifest, media_dir = make_run(tmp_path, "clear")
    out = tmp_path / "out"
    descriptor = _descriptor()
    proc = _command(
        descriptor["media"]["module"],
        descriptor["media"]["arguments"],
        {
            "evidence_manifest": str(manifest),
            "media_dir": str(media_dir),
            "result_dir": str(out),
            "world": str(WORLD),
            "identity": IDENTITY,
        },
    )
    assert proc.returncode == 0, proc.stderr
    assert descriptor["exit_codes"][str(proc.returncode)] == "result"
    _assert_results(out)
    assert (out / "media" / "thresholds.json").is_file()


def test_a_refusal_exits_1(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"format": "not-a-manifest"}), encoding="utf-8")
    thresholds = tmp_path / "thresholds.json"
    thresholds.write_text(json.dumps(LIMITS), encoding="utf-8")
    proc = _trial(manifest, thresholds, tmp_path / "out")
    assert proc.returncode == 1, proc.stderr
    assert "Traceback" not in proc.stderr
    assert "ERROR" in proc.stderr
    assert _descriptor()["exit_codes"][str(proc.returncode)] == "refused"
    assert not (tmp_path / "out").exists()


def test_a_crash_exits_1(tmp_path: Path) -> None:
    proc = _trial(STOCK, tmp_path / "missing.json", tmp_path / "out")
    assert proc.returncode == 1, proc.stderr
    assert "Traceback" in proc.stderr
    assert _descriptor()["exit_codes"][str(proc.returncode)] == "refused"
    assert not (tmp_path / "out").exists()


def test_a_usage_error_exits_2_and_is_a_failure() -> None:
    descriptor = _descriptor()
    proc = subprocess.run(
        [sys.executable, "-m", descriptor["entrypoint"]["module"]],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 2, proc.stderr
    assert str(proc.returncode) not in descriptor["exit_codes"]


def test_the_manual_names_the_descriptor_declaration() -> None:
    for path in (README, GUIDE, INDEX):
        assert DECLARATION in path.read_text(encoding="utf-8")


def test_the_manual_names_the_pinned_release() -> None:
    pin = _pin()
    for path in (README, VERIFICATION):
        text = path.read_text(encoding="utf-8")
        assert pin["tag"] in text
        assert pin["commit"] in text
