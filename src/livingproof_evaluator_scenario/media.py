# SPDX-License-Identifier: Apache-2.0
"""Grade a verification run's media: each trial's MCAP, read through its merged binding.

This is the pipeline entry for the runner. It takes the run's evidence ``manifest.json`` and the
``media`` artifact (``media.json`` 2.1.0, ``mcap/`` with the recordings and their bindings) and
writes one ``livingproof-evaluator-result/1.1.0`` document per trial, plus ``thresholds.json``.

Limits come from the run manifest alone: the inputs it records (world, robot and configuration
profile, ``plan.command_speed``) resolved through the scenario parameter file's formulas. A
limit the manifest cannot give is *missing*, and the steps that need it are ``NOT_EVALUATED``
(``missing_threshold``). Neither the parameter file's own values nor any verifier supplies it.

Each result names the evaluator: ``evaluator.id`` and ``evaluator.version``, and an input of role
``evaluator`` whose ``uri`` is the identity the caller states (a commit or an image digest) and
whose ``sha256`` is the digest of this package's own source, so the two can be checked together.

    python -m livingproof_evaluator_scenario.media manifest.json media out \\
        --world world.json --identity git+https://github.com/ORG/REPO@COMMIT
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

from livingproof_scenario_parameters.parameters import (
    _get_path,
    evaluate,
    resolve_input,
    round_half_even_binary,
)

from livingproof_evaluator_scenario import result, runner
from livingproof_evaluator_scenario.checks import limits_alias, parameters_document
from livingproof_evaluator_scenario.errors import EvaluationError

MEDIA_FORMAT = re.compile(r"livingproof-[a-z0-9-]+-media/[0-9]+\.[0-9]+\.[0-9]+")
EVALUATOR_ROLE = "evaluator"


def source_digest() -> str:
    """sha256 over this package's source files (path and bytes, sorted)."""
    root = Path(__file__).resolve().parent
    digest = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*") if p.suffix in (".py", ".json") and p.is_file()):
        digest.update(
            path.relative_to(root).as_posix().encode() + b"\0" + path.read_bytes() + b"\0"
        )
    return digest.hexdigest()


def thresholds_from_manifest(manifest: dict, parameters: dict | None = None) -> tuple[dict, dict]:
    """``(thresholds, missing)`` read from the run manifest only.

    ``thresholds`` is keyed as the evaluator reads it (``half_width`` for ``exit_segment``).
    ``missing`` maps each limit the manifest cannot give to why.
    """
    document = json.loads(json.dumps(parameters_document() if parameters is None else parameters))
    world = manifest.get("world") if isinstance(manifest.get("world"), dict) else {}
    robot = manifest.get("robot") if isinstance(manifest.get("robot"), dict) else {}
    configuration = manifest.get("configuration")
    configuration = configuration if isinstance(configuration, dict) else {}
    plan = manifest.get("plan") if isinstance(manifest.get("plan"), dict) else {}
    sources = {
        "world": {"dimensions": {"clear_width": world.get("clear_width")}},
        "robot-profile": robot.get("profile"),
        "configuration-profile": configuration.get("profile"),
    }
    speed = plan.get("command_speed")
    document["parameters"]["command_speed"] = {"value": speed, "unit": "m/s"}
    inputs, why = {}, {}
    for name, spec in document["inputs"].items():
        if spec.get("rule") == "route-length-from-start-to-exit":
            raw = world.get("route_length")
        else:
            raw = (
                _get_path(sources[spec["source"]], spec["path"])
                if sources[spec["source"]]
                else None
            )
        try:
            inputs[name] = resolve_input(name, spec, raw)
        except Exception as exc:  # the library's own message says what is missing
            why[name] = str(exc)
    limits, missing = {}, {}
    for name, limit in document["limits"].items():
        try:
            value = evaluate(limit["expression"], document, inputs)
            if limit.get("round"):
                value = round_half_even_binary(value, limit["round"]["decimals"])
            limits[name] = value
        except Exception as exc:
            missing[name] = why.get(_first_input(limit["expression"]), str(exc))
    thresholds = {(limits_alias(k) or k): v for k, v in limits.items()}
    return thresholds, missing


def _first_input(expression) -> str | None:
    if isinstance(expression, dict):
        if "input" in expression:
            return expression["input"]
        for value in expression.values():
            found = _first_input(value)
            if found:
                return found
    if isinstance(expression, list):
        for value in expression:
            found = _first_input(value)
            if found:
                return found
    return None


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _listed(media_dir: Path, entry, what: str, index) -> Path:
    if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
        raise EvaluationError(f"ERROR: media.json trial {index} lists no {what} file (no {what}).")
    path = (media_dir / entry["path"]).resolve()
    if media_dir.resolve() not in path.parents or not path.is_file():
        raise EvaluationError(
            f"ERROR: trial {index} {what} {entry['path']!r} is not under the media directory."
        )
    if _sha256(path) != entry.get("sha256"):
        raise EvaluationError(
            f"ERROR: trial {index} {what} sha256 is not the one media.json lists for {entry['path']}."
        )
    return path


def _thresholds_bytes(thresholds: dict, missing: dict) -> bytes:
    if not missing:
        return result.thresholds_bytes(thresholds)
    document = result.thresholds_document(
        {**thresholds, **{limits_alias(k) or k: 0 for k in missing}}
    )
    document["limits"] = {k: v for k, v in document["limits"].items() if k not in missing}
    document["missing"] = dict(sorted(missing.items()))
    return result.canonical_json(document)


def write_media_run(
    manifest_path,
    media_dir,
    out_dir,
    *,
    started_at: str,
    completed_at: str,
    world: dict,
    identity: str,
    parameters: dict | None = None,
) -> list[Path]:
    """One result file per trial, and ``thresholds.json``. Nothing is written if any trial fails."""
    if not isinstance(identity, str) or not identity.strip():
        raise EvaluationError("ERROR: an evaluator identity (commit or image digest) is required.")
    manifest_path, media_dir = Path(manifest_path), Path(media_dir)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    index = json.loads((media_dir / "media.json").read_text(encoding="utf-8"))
    fmt = index.get("format", "")
    trials = index.get("trials")
    if not (isinstance(fmt, str) and MEDIA_FORMAT.fullmatch(fmt)) or not isinstance(trials, list):
        raise EvaluationError(f"ERROR: media.json format {fmt!r} is not a media index.")
    thresholds, missing = thresholds_from_manifest(manifest, parameters)
    bound = _thresholds_bytes(thresholds, missing)
    threshold_ref = {
        "role": result.THRESHOLDS_ROLE,
        "uri": result.THRESHOLDS_FILENAME,
        "sha256": hashlib.sha256(bound).hexdigest(),
    }
    configuration = manifest["configuration"]["name"]
    manifest_ref = {"role": "manifest", "uri": manifest_path.name, "sha256": _sha256(manifest_path)}
    evaluator_ref = {"role": EVALUATOR_ROLE, "uri": identity.strip(), "sha256": source_digest()}
    documents = []
    for trial in sorted(trials, key=lambda item: item["index"]):
        number = trial["index"]
        if "binding" not in trial:
            raise EvaluationError(
                f"ERROR: media.json trial {number} has no binding file ({fmt}); "
                "the recording cannot be read without its binding."
            )
        mcap = _listed(media_dir, trial.get("mcap"), "mcap", number)
        binding = _listed(media_dir, trial.get("binding"), "binding", number)
        ident = result.trial_id(configuration, number)
        payload = runner.run_trial(
            mcap, binding, thresholds, world, parameters=parameters, missing=missing or None
        )
        steps = payload["steps"]
        documents.append(
            (
                f"{ident}.json",
                _document(
                    ident,
                    steps,
                    [
                        {
                            "role": "recording",
                            "uri": trial["mcap"]["path"],
                            "sha256": _sha256(mcap),
                        },
                        {
                            "role": "binding",
                            "uri": trial["binding"]["path"],
                            "sha256": _sha256(binding),
                        },
                        manifest_ref,
                        threshold_ref,
                        evaluator_ref,
                    ],
                    started_at,
                    completed_at,
                ),
            )
        )
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / result.THRESHOLDS_FILENAME).write_bytes(bound)
    written = []
    for name, document in documents:
        path = out_dir / name
        path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
        written.append(path)
    return written


def _document(
    ident: str, steps: list[dict], inputs: list[dict], started: str, completed: str
) -> dict:
    result._timestamp(started, "started_at")
    result._timestamp(completed, "completed_at")
    version = result.package_version()
    return {
        "format": "livingproof-evaluator-result/1.1.0",
        "evaluator": {
            "id": result.EVALUATOR_ID,
            "version": version,
            "kind": "scenario",
            "execution": "deterministic",
            "display_name": result.DISPLAY_NAME,
            "publisher": result.PUBLISHER,
            "icon": result.ICON,
        },
        "inputs": inputs,
        "timestamps": {"started_at": started, "completed_at": completed},
        "scenario": {"trial_id": ident, "steps": steps},
        "descriptor": {
            "title": result.DISPLAY_NAME,
            "short_title": result.SHORT_TITLE,
            "icon": result.ICON,
            "icon_accessible_name": result.DISPLAY_NAME,
            "purpose": result.PURPOSE,
            "version": version,
            "tier": result.TIER,
            "findings": [],
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("manifest", type=Path)
    parser.add_argument("media", type=Path, help="the media directory (media.json and mcap/)")
    parser.add_argument("out", type=Path)
    parser.add_argument("--world", type=Path, required=True)
    parser.add_argument("--identity", required=True, help="the evaluator's commit or image digest")
    parser.add_argument("--started-at", default=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"))
    args = parser.parse_args(argv)
    try:
        written = write_media_run(
            args.manifest,
            args.media,
            args.out,
            started_at=args.started_at,
            completed_at=args.started_at,
            world=json.loads(args.world.read_text(encoding="utf-8")),
            identity=args.identity,
        )
    except EvaluationError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    for path in written:
        print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
