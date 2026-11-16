# SPDX-License-Identifier: Apache-2.0
"""Observation formats this evaluator grades, and the fields that differ between them.

``livingproof-route-observation/0.1.0`` is livingproof-sim-mujoco v3.2.0's record of
an adapter-driven trial (``observations.observe_route``): the greatest distance from
the route is ``max_route_distance``, an early end is ``left_world`` (``via`` a wall or
``exit-outside-segment``), and ``places_entered`` lists the through-places. The trace
columns are the same as the frozen format's. Frozen formats keep their own readers
in :mod:`livingproof_evaluator_scenario.compat`, unchanged.
"""

from __future__ import annotations

import math

from livingproof_evaluator_scenario import compat
from livingproof_evaluator_scenario.compat.recorded import OBSERVATION_ENDS
from livingproof_evaluator_scenario.errors import EvaluationError

ROUTE_FORMAT = "livingproof-route-observation/0.1.0"
ROUTE_ENDS = {"crossed_exit", "time_limit", "non_finite_state", "left_world"}
_ROUTE_DEPARTURE = "left_world"


def is_route(observation: dict) -> bool:
    return observation.get("format") == ROUTE_FORMAT


def known_formats() -> list[str]:
    return sorted({*OBSERVATION_ENDS, ROUTE_FORMAT})


def allowed_ends(fmt) -> set[str] | None:
    """Ends a known observation format may report. ``None`` when ``fmt`` is not known."""
    if fmt == ROUTE_FORMAT:
        return ROUTE_ENDS
    return compat.allowed_ends(fmt)


def unknown_observation(fmt: str) -> EvaluationError | None:
    """``ERROR`` when ``fmt`` is not a format this evaluator reads. ``None`` when it is."""
    if allowed_ends(fmt) is not None:
        return None
    return EvaluationError(
        f"ERROR: unknown observation format {fmt!r}. "
        f"This evaluator reads {', '.join(known_formats())}. Any other format is rejected. "
        f'Example: {{"format": "{ROUTE_FORMAT}"}}.'
    )


def distance_field(observation: dict) -> str:
    """The observation field holding the greatest distance from the route."""
    return "max_route_distance" if is_route(observation) else "max_abs_lateral"


def _num(value) -> bool:
    return type(value) in (int, float) and math.isfinite(value)


def departure_state(observation: dict) -> dict | None:
    """The early-end record, or ``None`` when the trial did not leave the world that way."""
    if not is_route(observation):
        return compat.departure_state(observation)
    if observation.get("end") != _ROUTE_DEPARTURE:
        return None
    left = observation.get(_ROUTE_DEPARTURE)
    if not (isinstance(left, dict) and _num(left.get("time"))):
        return {"malformed": True, "what": _ROUTE_DEPARTURE, "time": None, "via": None}
    via = left.get("via")
    if not (isinstance(via, str) and via.strip()):
        what = f"{_ROUTE_DEPARTURE}.via"
        return {"malformed": True, "what": what, "time": left["time"], "via": None}
    return {"malformed": False, "what": _ROUTE_DEPARTURE, "time": left["time"], "via": via}


def departure_text(observation: dict, via: str, time: float, seed_text: str) -> str:
    if not is_route(observation):
        return compat.departure_text(via, time, seed_text)
    return f"left the world via {via} at {time:.2f} s{seed_text}"


def distance_text(observation: dict, observed: str, limit: str, over: bool, when: str) -> str:
    """``lateral …`` for frozen records (exact historical wording), ``route distance …`` else."""
    word = "route distance" if is_route(observation) else "lateral"
    if over:
        return f"{word} {observed} m > {limit} m at {when}"
    return f"{word} {observed} m <= {limit} m, largest at {when}"
