# SPDX-License-Identifier: Apache-2.0
"""Grade one trial from its MCAP recording, read through its merged observation binding.

The binding (livingproof-observation-binding/1.0.0, ``kind: merged``) says which channel and
fields carry each observable: ``base`` (x, y), ``base_height`` (z) and ``body_contact``
(``{wall, start, end, depth}``, one message per contact event). This module names no topic and
no field path of its own; it reads what the binding names. An observable the binding does not
bind makes the steps that need it ``NOT_EVALUATED`` (``unbound_observable``). A bound observable
whose channel the recording never declares, or whose messages are malformed, leaves its steps
``INCONCLUSIVE``: "no contacts" is a declared channel with no messages, not a missing channel.

The result is the contract's scenario payload (``trial_id`` and one verdict per step). Limits are
the ones the caller passes in, resolved with ``livingproof_scenario_parameters`` as in
:mod:`livingproof_evaluator_scenario.checks`, and the fall rule is the absolute ``fall_height``
(the profile's ``fall_base_height``); the nominal base height is reference data only.

    python -m livingproof_evaluator_scenario.runner trial-01.mcap trial-01.binding.json \\
        --thresholds thresholds.json --world world.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

from mcap.reader import make_reader

from livingproof_evaluator_scenario import checks
from livingproof_evaluator_scenario.errors import EvaluationError

FORMAT = "livingproof-observation-binding/1.0.0"
PASS, FAIL, INCONCLUSIVE, NOT_EVALUATED = "PASS", "FAIL", "INCONCLUSIVE", "NOT_EVALUATED"
# The observable vocabulary's terms and the value names a bound term must have (livingproof-evaluator
# v1.6.0, docs/observable-vocabulary.md).
FIELDS = {
    "base": ("x", "y"),
    "base_height": ("z",),
    "body_contact": ("wall", "start", "end", "depth"),
}
# The observable each parameter-file rule (``fail_when``) reads. The steps themselves, their ids
# and their order are the parameter file's ``checks``; this module names none of them.
RULE_OBSERVABLE = {
    "absent-or-greater-than-limit": "base",
    "greater-than-limit": "base",
    "not-empty": "body_contact",
    "less-than-limit": "base_height",
}


class BindingError(EvaluationError):
    """The binding is not one this runner can trust. Nothing is guessed in its place."""


def _text(value) -> bool:
    return isinstance(value, str) and bool(value.strip())


def read_binding(source) -> dict:
    """The merged binding as a dict, checked for what reading the recording relies on."""
    if isinstance(source, (str, Path)):
        try:
            binding = json.loads(Path(source).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise BindingError(f"ERROR: cannot read binding {source}: {exc}") from None
    else:
        binding = source
    if not isinstance(binding, dict):
        raise BindingError("ERROR: the binding must be a JSON object.")
    if binding.get("format") != FORMAT:
        raise BindingError(f"ERROR: binding format {binding.get('format')!r} is not {FORMAT}.")
    if binding.get("kind") != "merged":
        raise BindingError(
            f"ERROR: binding kind {binding.get('kind')!r} is not 'merged'. "
            "Read the per-trial merged binding, not a robot or producer binding."
        )
    observables = binding.get("observables")
    if not isinstance(observables, dict):
        raise BindingError("ERROR: binding observables must be an object.")
    if binding.get("bound_observables") != list(observables):
        raise BindingError(
            "ERROR: binding bound_observables must list exactly the observables, in order."
        )
    recording = binding.get("recording")
    if not isinstance(recording, dict) or not _text(recording.get("sha256")):
        raise BindingError("ERROR: binding recording has no sha256.")
    for name, entry in observables.items():
        if name not in FIELDS:
            raise BindingError(f"ERROR: observable {name!r} is not an observable vocabulary term.")
        if not isinstance(entry, dict):
            raise BindingError(f"ERROR: observable {name} entry must be an object.")
        if not _text(entry.get("topic")):
            raise BindingError(f"ERROR: observable {name} has no topic, so no channel carries it.")
        if entry.get("encoding") != "json":
            raise BindingError(
                f"ERROR: observable {name} encoding {entry.get('encoding')!r} is not supported; "
                "this runner reads json."
            )
        if entry.get("frame") != "world":
            raise BindingError(
                f"ERROR: observable {name} frame {entry.get('frame')!r} is not 'world'."
            )
        fields = entry.get("fields")
        if not isinstance(fields, dict):
            raise BindingError(f"ERROR: observable {name} has no fields.")
        for needed in FIELDS[name]:
            if not _text(fields.get(needed)):
                raise BindingError(f"ERROR: observable {name} is bound without its field {needed}.")
    unbound = binding.get("unbound")
    if not isinstance(unbound, list):
        raise BindingError("ERROR: binding unbound must be a list.")
    return binding


def _path(message: dict, dotted: str):
    node = message
    for key in dotted.split("."):
        if not isinstance(node, dict) or key not in node:
            return None
        node = node[key]
    return node


def _number(value) -> bool:
    return type(value) in (int, float) and math.isfinite(value)


class _Signal:
    """What one bound observable read from the recording: rows, or why there are none to use."""

    def __init__(self, topic: str):
        self.topic = topic
        self.rows: list[dict] = []
        self.problem: str | None = None


def read_signals(mcap_path, binding: dict) -> dict[str, _Signal]:
    """For each bound observable, its messages as rows of ``{t, <value name>: value}``."""
    signals = {name: _Signal(entry["topic"]) for name, entry in binding["observables"].items()}
    with Path(mcap_path).open("rb") as stream:
        reader = make_reader(stream)
        summary = reader.get_summary()
        declared = {c.topic: c for c in (summary.channels.values() if summary else [])}
        for name, signal in signals.items():
            channel = declared.get(signal.topic)
            if channel is None:
                signal.problem = f"the recording declares no {signal.topic} channel"
            elif channel.message_encoding != binding["observables"][name]["encoding"]:
                signal.problem = f"{signal.topic} is not encoded as the binding says"
        wanted = sorted({s.topic for s in signals.values() if s.problem is None})
        if wanted:
            for _schema, channel, message in reader.iter_messages(topics=wanted):
                try:
                    body = json.loads(message.data)
                except ValueError:
                    body = None
                for name, signal in signals.items():
                    if signal.topic != channel.topic or signal.problem is not None:
                        continue
                    fields = binding["observables"][name]["fields"]
                    row = {"t": message.log_time / 1e9}
                    for value_name in FIELDS[name]:
                        row[value_name] = _path(body, fields[value_name]) if body else None
                    numeric = [v for k, v in row.items() if k != "wall"]
                    if not all(_number(v) for v in numeric) or (
                        name == "body_contact" and not _text(row["wall"])
                    ):
                        signal.problem = f"a {signal.topic} message lacks its {name} fields"
                        signal.rows = []
                    else:
                        signal.rows.append(row)
    return signals


def _sha256(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _unusable(name: str, signal: _Signal | None, binding: dict):
    """The step result when the observable is unbound or its recording is unusable, else None."""
    if signal is None:
        reason = next((u.get("reason") for u in binding["unbound"] if u.get("id") == name), None)
        why = f" ({reason})" if reason else ""
        return (
            NOT_EVALUATED,
            f"observable {name} is unbound in the binding{why}",
            "unbound_observable",
        )
    if signal.problem is not None:
        return INCONCLUSIVE, f"{name}: {signal.problem}", None
    if name != "body_contact" and not signal.rows:
        return INCONCLUSIVE, f"{name}: no messages on {signal.topic}", None
    return None


def _samples(signal: _Signal) -> list[list[float]]:
    return [[row["t"], row["x"], row["y"]] for row in signal.rows]


def _exit(samples, limits, route, exit_place):
    crossing = checks.first_crossing(samples, route, exit_place)
    limit = limits["time_limit"]
    if crossing is None:
        return FAIL, f"the base did not cross the exit within {limit:.2f} s"
    if crossing[0] > limit:
        return FAIL, f"exit at {crossing[0]:.2f} s > {limit:.2f} s"
    return PASS, f"exit at {crossing[0]:.2f} s <= {limit:.2f} s ({limit - crossing[0]:.2f} s spare)"


def _lateral(samples, limits, route):
    limit = limits["lateral_limit"]
    distances = [(checks.trace_distance(route, [s[1], s[2], 0.0]), s[0]) for s in samples]
    over = next(((d, t) for d, t in distances if d > limit), None)
    if over is not None:
        return FAIL, f"lateral {over[0]:.2f} m > {limit:.2f} m at {over[1]:.2f} s"
    far, when = max(distances)
    return PASS, f"lateral {far:.2f} m <= {limit:.2f} m, largest at {when:.2f} s"


def _wall(signal: _Signal):
    if not signal.rows:
        return PASS, "no wall contact"
    first = signal.rows[0]
    more = f" (and {len(signal.rows) - 1} more)" if len(signal.rows) > 1 else ""
    return (
        FAIL,
        f"wall contact with {first['wall']} at {first['start']:.2f} s, "
        f"depth {first['depth']:.2f} m{more}",
    )


def _fall(signal: _Signal, limits):
    limit = limits["fall_height"]
    low = min(signal.rows, key=lambda row: row["z"])
    if low["z"] < limit:
        return FAIL, f"base height {low['z']:.2f} m < {limit:.2f} m at {low['t']:.2f} s"
    return PASS, f"base height {low['z']:.2f} m >= {limit:.2f} m, lowest at {low['t']:.2f} s"


def run_trial(mcap_path, binding, thresholds, world, *, steps=None, parameters=None) -> dict:
    """Verdicts for one trial: ``{"trial_id": ..., "steps": [{id, verdict, summary[, reason]}]}``.

    ``binding`` is a merged binding (dict or file). Its recording sha256 must be that of
    ``mcap_path``. ``thresholds`` and ``world`` are as for :func:`checks.assess`.
    """
    binding = read_binding(binding)
    actual = _sha256(mcap_path)
    if actual != binding["recording"]["sha256"]:
        raise BindingError(
            f"ERROR: recording sha256 {actual[:12]} is not the binding's "
            f"{binding['recording']['sha256'][:12]}; the binding is for a different recording."
        )
    document = parameters if parameters is not None else checks.parameters_document()
    limits = checks.limits_from_thresholds(document, thresholds)
    route, exit_place = checks._route_from_world(world, document)
    signals = read_signals(mcap_path, binding)
    rules = {check["evaluator"]: check["fail_when"] for check in document["checks"]}
    results = []
    for step in steps if steps is not None else list(rules):
        rule = rules.get(step)
        if rule not in RULE_OBSERVABLE:
            results.append(
                {
                    "id": step,
                    "verdict": NOT_EVALUATED,
                    "summary": f"step {step!r} is not one this evaluator knows",
                    "reason": "unknown_step",
                }
            )
            continue
        name = RULE_OBSERVABLE[rule]
        signal = signals.get(name)
        blocked = _unusable(name, signal, binding)
        if blocked is not None:
            verdict, summary, reason = blocked
        else:
            reason = None
            if rule == "absent-or-greater-than-limit":
                verdict, summary = _exit(_samples(signal), limits, route, exit_place)
            elif rule == "greater-than-limit":
                verdict, summary = _lateral(_samples(signal), limits, route)
            elif rule == "not-empty":
                verdict, summary = _wall(signal)
            else:
                verdict, summary = _fall(signal, limits)
        item = {"id": step, "verdict": verdict, "summary": summary}
        if reason:
            item["reason"] = reason
        results.append(item)
    return {"trial_id": binding["trial_id"], "steps": results}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("mcap", type=Path, help="the trial recording, e.g. trial-01.mcap")
    parser.add_argument("binding", type=Path, help="its merged binding, e.g. trial-01.binding.json")
    parser.add_argument(
        "--thresholds",
        type=Path,
        required=True,
        help='JSON of time_limit, lateral_limit, half_width, fall_height. Example: {"time_limit": 27.0, '
        '"lateral_limit": 0.49, "half_width": 0.75, "fall_height": 0.5}',
    )
    parser.add_argument("--world", type=Path, required=True, help="the world.json of the trial")
    args = parser.parse_args(argv)
    try:
        payload = run_trial(
            args.mcap,
            args.binding,
            json.loads(args.thresholds.read_text(encoding="utf-8")),
            json.loads(args.world.read_text(encoding="utf-8")),
        )
    except EvaluationError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
