# SPDX-License-Identifier: Apache-2.0
"""Frozen hallway evidence, the only scenario this reader names.

robot-capability-specs v2.2.0 (commit 23bec516bda29be7b26555286cbf2e8217ac5c81)
``specs/scenarios/walk-hallway/parameters.json`` is copied here byte for byte.
``hallway-open`` 0.1.0's passage centreline is the straight route below: from
``(-3, 0)`` to ``(3, 0)``, exit line at ``x = 3``. The segment's half-length
is the limit the verifier still passes as ``half_width`` (the parameter file's
``exit_segment``). No new writer emits these format names.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

from livingproof_evaluator_scenario.errors import EvaluationError

PARAMETERS_SHA256 = "9226aa6bc0e577863bdc210514e7e7c3a7edc32f49c4f7b46aa7249837f08b3d"
PARAMETERS_TAG = "v2.2.0"
PARAMETERS_COMMIT = "23bec516bda29be7b26555286cbf2e8217ac5c81"
EVIDENCE_FORMAT = "livingproof-hallway-evidence/2.0.0"
OBSERVATION_FORMAT = "livingproof-hallway-observation/2.0.0"
OBSERVATION_ENDS = {
    "livingproof-hallway-observation/1.0.0": {"crossed_exit", "time_limit", "non_finite_state"},
    OBSERVATION_FORMAT: {"crossed_exit", "time_limit", "non_finite_state", "left_hallway"},
}
# The verifier still passes the exit-segment limit under this key.
_LIMIT_ALIASES = {"exit_segment": "half_width"}
_DEPARTURE_END = "left_hallway"
_DEPARTURE_FIELD = "left_hallway"
_PATH = Path(__file__).with_name("parameters.json")
# hallway-open 0.1.0 passage centreline and the exit line at x = 3.
_EXIT_X = 3
_ROUTE = [[-3, 0, 0], [_EXIT_X, 0, 0]]


def parameters_document() -> dict:
    """The tagged parameter file. A sha256 mismatch is a test-system error."""
    raw = _PATH.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != PARAMETERS_SHA256:
        raise EvaluationError(
            f"ERROR: vendored parameter file sha256 {digest} != {PARAMETERS_SHA256} "
            f"({PARAMETERS_TAG} {PARAMETERS_COMMIT}). "
            "Restore compat/parameters.json from that tag. "
            "Example: the file next to this module is the byte copy of "
            "specs/scenarios/walk-hallway/parameters.json at that tag."
        )
    return json.loads(raw)


def frozen_observation_format() -> str:
    """The observation format already-recorded trials use."""
    return OBSERVATION_FORMAT


def allowed_ends(fmt) -> set[str] | None:
    """Ends a known observation format may report. ``None`` when ``fmt`` is not known."""
    if fmt not in OBSERVATION_ENDS:
        return None
    return OBSERVATION_ENDS[fmt]


def unknown_observation(fmt: str) -> EvaluationError | None:
    """``ERROR`` when ``fmt`` is not a format this evaluator reads. ``None`` when it is."""
    if fmt in OBSERVATION_ENDS:
        return None
    known = ", ".join(sorted(OBSERVATION_ENDS))
    return EvaluationError(
        f"ERROR: unknown observation format {fmt!r}. This evaluator reads {known}. "
        "A neutral observation format is not defined yet, so any other format is rejected. "
        f'Example: {{"format": "{OBSERVATION_FORMAT}"}}.'
    )


def require_evidence_format(fmt) -> None:
    """Raise ``ERROR`` unless ``fmt`` is the frozen evidence manifest format."""
    if fmt == EVIDENCE_FORMAT:
        return
    raise EvaluationError(
        f"ERROR: unknown evidence format {fmt!r}. This evaluator reads {EVIDENCE_FORMAT}. "
        "A neutral evidence format is not defined yet, so any other format is rejected. "
        f'Example: a manifest with "format": "{EVIDENCE_FORMAT}".'
    )


def evidence_manifest_help() -> str:
    """Argument help for the manifest path. Names the frozen format."""
    return f"{EVIDENCE_FORMAT} manifest"


def limits_alias(name: str) -> str | None:
    """Verifier threshold key for a parameter-file limit, when the key differs."""
    return _LIMIT_ALIASES.get(name)


def straight_route(half_width: float) -> tuple[list, dict]:
    """Frozen world's route and exit segment.

    One leg along ``y = 0``. The exit segment is perpendicular to that leg at
    ``x = 3``, and its half-length is ``half_width`` so the package's lateral
    test is the historical ``|y|`` test.
    """
    return list(_ROUTE), {
        "points": [[_EXIT_X, -half_width, 0], [_EXIT_X, half_width, 0]],
        "reference": [_EXIT_X, 0, 0],
    }


def _num(value) -> bool:
    return type(value) in (int, float) and math.isfinite(value)


def departure_state(observation: dict) -> dict | None:
    """The frozen early-end record, or ``None`` when the trial did not leave that way.

    ``malformed`` is true when the record cannot be graded. ``what`` is the
    observation field a missing-evidence sentence should name.
    """
    if observation.get("end") != _DEPARTURE_END:
        return None
    left = observation.get(_DEPARTURE_FIELD)
    if not (isinstance(left, dict) and _num(left.get("time"))):
        return {"malformed": True, "what": _DEPARTURE_FIELD, "time": None, "via": None}
    via = left.get("via")
    if not (isinstance(via, str) and via.strip()):
        return {
            "malformed": True,
            "what": f"{_DEPARTURE_FIELD}.via",
            "time": left["time"],
            "via": None,
        }
    return {"malformed": False, "what": _DEPARTURE_FIELD, "time": left["time"], "via": via}


def departure_text(via: str, time: float, seed_text: str) -> str:
    """Historical sentence for a frozen early end. The wording stays exact."""
    return f"left the hallway via {via} at {time:.2f} s{seed_text}"


def outside_segment_text(observed: str, limit_text: str, seed_text: str) -> str:
    """Historical sentence when the exit line is crossed outside the segment."""
    return f"exit line crossed at |y| {observed} m > {limit_text} m, outside the exit{seed_text}"
