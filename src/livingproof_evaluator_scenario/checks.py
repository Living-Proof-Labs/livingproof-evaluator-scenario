# SPDX-License-Identifier: Apache-2.0
"""Scenario step checks.

Each check in the parameter file's ``checks`` array is one step. ``fail_when``
selects the rule and ``measure`` selects the observation. Limit numbers are the
ones the caller passes in; resolving a limit uses
``livingproof_scenario_parameters`` and never a formula copied here. Exit
crossing and distance to the route use that package's ``crosses_exit`` and
``distance_to_route`` on the route from the scenario's world. With no world,
the frozen straight route is used so an already-recorded trial grades as before.
"""

from __future__ import annotations

import math

from livingproof_scenario_parameters import (
    ScenarioParameterError,
    crosses_exit,
    distance_to_route,
    reference_errors,
    resolve,
)

from livingproof_evaluator_scenario.compat import (
    allowed_ends,
    departure_state,
    departure_text,
    frozen_observation_format,
    limits_alias,
    outside_segment_text,
    parameters_document,
    straight_route,
    unknown_observation,
)
from livingproof_evaluator_scenario.errors import EvaluationError

PASS, FAIL, INSUFFICIENT = "PASS", "FAIL", "INSUFFICIENT_EVIDENCE"
# Assessment version recorded on each check. This is not the package version.
VERSION = "1.0.0"
# The measure each fail_when rule reads. The schema pairs them this way.
_MEASURES = {
    "absent-or-greater-than-limit": "exit-crossing-time",
    "greater-than-limit": "max-distance-from-route",
    "not-empty": "wall-contacts",
    "less-than-limit": "min-base-height",
    "not-in-order": "passes-through-places",
}


def _default_parameters() -> dict:
    return parameters_document()


EVALUATORS = tuple(check["evaluator"] for check in _default_parameters()["checks"])


def assessment(evaluator, status, rationale, evidence_id, details=None, assessor="deterministic"):
    return {
        "id": f"{evidence_id}/{evaluator}",
        "evaluator": evaluator,
        "version": VERSION,
        "assessor": {"type": assessor, "id": evaluator, "version": VERSION},
        "status": status,
        "rationale": rationale,
        "mandatory": True,
        "evidence_ids": [evidence_id],
        "details": details or {},
    }


def _num(v):
    return type(v) in (int, float) and math.isfinite(v)


def _extreme(o, name):
    e = o.get(name)
    if not isinstance(e, dict) or not _num(e.get("value")) or not _num(e.get("time")):
        return None
    return e


def _length(v, limit):
    """Fewest decimals (at least 2) at which observed and limit no longer read as equal."""
    for d in range(2, 7):
        if f"{v:.{d}f}" != f"{limit:.{d}f}":
            return f"{v:.{d}f}", f"{limit:.{d}f}"
    return f"{v:.6g}", f"{limit:.6g}"


def failure(check, observed, limit, unit, t, seed, **extra):
    """Structured failed check, so a PR comment can group failures."""
    return {
        "check": check,
        "observed": observed,
        "limit": limit,
        "unit": unit,
        "t": None if t is None else round(t, 2),
        "seed": _seed_number(seed),
        **extra,
    }


def _seed(seed):
    """Parenthetical for a rationale. An int is a 1.0.0 seed; ``("trial", n)`` is a 2.0.0 index."""
    if isinstance(seed, tuple) and len(seed) == 2 and seed[0] == "trial":
        return f" (trial {seed[1]})"
    return f" (seed {seed})" if seed is not None else ""


def _seed_number(seed):
    """The integer stored in a structured failure's ``seed`` field (a seed, or a trial index)."""
    if isinstance(seed, tuple) and len(seed) == 2 and seed[0] == "trial":
        return seed[1]
    return seed


def _insufficient(name, what, eid, seed):
    return assessment(
        name, INSUFFICIENT, f"missing or malformed observation {what}{_seed(seed)}", eid
    )


def _trace(observation):
    trace = observation.get("trace") or {}
    if not isinstance(trace, dict):
        return []
    samples = trace.get("samples", [])
    return samples if isinstance(samples, list) else []


def _point(sample):
    z = sample[3] if len(sample) > 3 else 0.0
    return [sample[1], sample[2], z]


def trace_distance(route, point):
    """Floor-plane distance from ``point`` to ``route``, from the parameters package."""
    return distance_to_route(route, point)


def trace_crosses(p0, p1, route, exit_place):
    """Whether the step ``p0`` to ``p1`` crosses ``exit_place``, from the parameters package.

    The package stops being true once a step has crossed: callers keep the first true.
    """
    return crosses_exit(p0, p1, route, exit_place)


def first_crossing(samples, route, exit_place):
    """The first sample at which a step crosses the exit, or ``None``.

    ``p0`` is strictly before the exit line and ``p1`` is on or past it. Later
    samples are not considered.
    """
    previous = None
    for sample in samples:
        if previous is not None and trace_crosses(
            _point(previous), _point(sample), route, exit_place
        ):
            return sample
        previous = sample
    return None


def first_distance_excess(samples, route, limit):
    """Time of the first sample whose distance to ``route`` is strictly over ``limit``."""
    for sample in samples:
        if trace_distance(route, _point(sample)) > limit:
            return sample[0]
    return None


def _claim_step(samples, time):
    """The last sample at ``time`` and the sample immediately before it."""
    previous = None
    found_previous = None
    found = None
    for sample in samples:
        if isinstance(sample, list) and len(sample) > 2 and sample[0] == time and _num(sample[2]):
            found_previous = previous
            found = sample
        previous = sample
    return found_previous, found


def accepted_limits(parameters: dict, raw: dict) -> dict:
    """Limits this evaluator would grade with for ``raw`` inputs.

    The numbers are ``livingproof_scenario_parameters.resolve``. A reference
    problem or a bad input is that package's ``ERROR``, and this module has no
    copy of a limit formula.
    """
    problems = reference_errors(parameters)
    if problems:
        raise ScenarioParameterError("; ".join(problems))
    return resolve(parameters, raw)["limits"]


def limits_from_thresholds(parameters: dict, thresholds: dict) -> dict:
    """Parameter-file limits taken from the threshold object the verifier passes.

    ``exit_segment`` is still accepted under the verifier's ``half_width`` key.
    """
    if not isinstance(thresholds, dict):
        raise EvaluationError(
            "ERROR: thresholds must be a JSON object with one number per limit. "
            'Example: {"time_limit": 27.0, "lateral_limit": 0.49, "half_width": 0.75, '
            '"fall_height": 0.5}'
        )
    limits = {}
    missing = []
    for name in parameters["limits"]:
        alias = limits_alias(name)
        if name in thresholds and _num(thresholds[name]):
            limits[name] = thresholds[name]
        elif alias and alias in thresholds and _num(thresholds[alias]):
            limits[name] = thresholds[alias]
        else:
            missing.append(alias or name)
    if missing:
        raise EvaluationError(
            "ERROR: thresholds missing "
            + ", ".join(missing)
            + ". Pass the resolved limits; exit_segment may be passed as half_width. "
            'Example: {"time_limit": 27.0, "lateral_limit": 0.49, "half_width": 0.75, '
            '"fall_height": 0.5}'
        )
    return limits


def _route_from_world(world, parameters):
    if not isinstance(world, dict) or not isinstance(world.get("places"), list):
        raise EvaluationError(
            "ERROR: the world has no places, so the route and the exit cannot be read. "
            "Example: a world whose places include the route polyline and the exit segment "
            "named by the parameter file."
        )
    names = {}
    for place in world["places"]:
        if isinstance(place, dict) and isinstance(place.get("name"), str):
            names[place["name"]] = place
    named = parameters["places"]
    route_place = names.get(named["route"])
    exit_place = names.get(named["exit"])
    points = route_place.get("points") if isinstance(route_place, dict) else None
    exit_points = exit_place.get("points") if isinstance(exit_place, dict) else None
    if not isinstance(points, list) or len(points) < 2:
        raise EvaluationError(
            f"ERROR: world place {named['route']!r} is not a route polyline of at least 2 points. "
            "Example: a polyline place named by parameters.places.route."
        )
    if not isinstance(exit_points, list) or len(exit_points) != 2:
        raise EvaluationError(
            f"ERROR: world place {named['exit']!r} is not an exit segment of 2 points. "
            "Example: a segment place named by parameters.places.exit."
        )
    return points, {"points": exit_points, "reference": exit_place.get("reference")}


def _require_measure(check):
    expected = _MEASURES.get(check.get("fail_when"))
    if expected is None:
        raise EvaluationError(
            f"ERROR: unknown fail_when {check.get('fail_when')!r}. "
            f"Expected one of {', '.join(_MEASURES)}. "
            'Example: {"fail_when": "greater-than-limit", "measure": "max-distance-from-route"}.'
        )
    if check.get("measure") != expected:
        raise EvaluationError(
            f"ERROR: fail_when {check['fail_when']!r} reads measure {expected!r}, "
            f"got {check.get('measure')!r}."
        )


def _limit(check, limits):
    name = check.get("limit")
    if name not in limits:
        raise EvaluationError(
            f"ERROR: check {check.get('evaluator')!r} needs limit {name!r}, "
            "which is not in the resolved thresholds."
        )
    return limits[name]


def fail_absent_or_greater(
    check, observation, limits, eid, seed, route, exit_place, document, world, frozen_record
):
    """Fail when the exit crossing is absent or its time is strictly over the limit."""
    _require_measure(check)
    name = check["evaluator"]
    if "exit_time" not in observation or not (
        observation["exit_time"] is None or _num(observation["exit_time"])
    ):
        return _insufficient(name, "exit_time", eid, seed)
    end = observation.get("end")
    known = allowed_ends(observation.get("format"))
    if end not in (known or ()):
        return _insufficient(name, "end", eid, seed)
    time_limit = _limit(check, limits)
    half = limits["exit_segment"]
    t = observation["exit_time"]
    departure = departure_state(observation)
    if departure is not None:
        if t is not None or departure["malformed"]:
            return _insufficient(name, departure["what"], eid, seed)
        text = departure_text(departure["via"], departure["time"], _seed(seed))
        failed = failure(name, None, time_limit, "s", departure["time"], seed, via=departure["via"])
        return assessment(
            name,
            FAIL,
            text,
            eid,
            {
                "observed": None,
                "threshold": time_limit,
                "time": departure["time"],
                "failures": [failed],
            },
        )
    if (t is None) != (end != "crossed_exit"):
        return _insufficient(name, "exit_time", eid, seed)
    if t is not None:
        previous, sample = _claim_step(_trace(observation), t)
        if sample is None or previous is None:
            return _insufficient(name, "exit crossing point", eid, seed)
        crossed = trace_crosses(_point(previous), _point(sample), route, exit_place)
        if not crossed:
            observed = abs(sample[2])
            a, b = _length(observed, half)
            # The frozen sentence names |y|. It is only true on the straight route,
            # where a rejected step is past the line and outside the segment.
            if frozen_record and observed > half:
                text = outside_segment_text(a, b, _seed(seed))
            else:
                text = f"exit line crossed outside the segment at {t:.2f} s{_seed(seed)}"
            failed = failure(name, observed, half, "m", t, seed, via="exit-outside-segment")
            return assessment(
                name,
                FAIL,
                text,
                eid,
                {"observed": observed, "threshold": half, "time": t, "failures": [failed]},
            )
    if t is None:
        end_time = (
            observation.get("duration_s") if _num(observation.get("duration_s")) else time_limit
        )
        failed = failure(name, None, time_limit, "s", end_time, seed)
        text = f"exit not reached by {time_limit:.2f} s{_seed(seed)}"
        return assessment(
            name,
            FAIL,
            text,
            eid,
            {"observed": None, "threshold": time_limit, "failures": [failed]},
        )
    margin = round(time_limit - t, 4)
    if t > time_limit:
        failed = failure(name, t, time_limit, "s", t, seed)
        text = f"exit {t:.2f} s > {time_limit:.2f} s at {t:.2f} s{_seed(seed)}"
        return assessment(
            name,
            FAIL,
            text,
            eid,
            {
                "observed": t,
                "threshold": time_limit,
                "time": t,
                "margin": margin,
                "failures": [failed],
            },
        )
    text = f"exit at {t:.2f} s <= {time_limit:.2f} s ({margin:.2f} s spare){_seed(seed)}"
    return assessment(
        name,
        PASS,
        text,
        eid,
        {"observed": t, "threshold": time_limit, "time": t, "margin": margin},
    )


def fail_greater(
    check, observation, limits, eid, seed, route, exit_place, document, world, frozen_record
):
    """Fail when the greatest distance to the route is strictly over the limit."""
    _require_measure(check)
    name = check["evaluator"]
    extreme = _extreme(observation, "max_abs_lateral")
    if extreme is None:
        return _insufficient(name, "max_abs_lateral", eid, seed)
    value, limit = extreme["value"], _limit(check, limits)
    margin = round(limit - value, 6)
    a, b = _length(value, limit)
    if value > limit:
        # First time over the limit. On the straight route this is the same sample as |y|.
        t = first_distance_excess(_trace(observation), route, limit)
        if t is None:
            t = extreme["time"]
        failed = failure(name, value, limit, "m", t, seed)
        text = f"lateral {a} m > {b} m at {t:.2f} s{_seed(seed)}"
        return assessment(
            name,
            FAIL,
            text,
            eid,
            {
                "observed": value,
                "threshold": limit,
                "time": t,
                "peak_time": extreme["time"],
                "margin": margin,
                "failures": [failed],
            },
        )
    text = f"lateral {a} m <= {b} m, largest at {extreme['time']:.2f} s{_seed(seed)}"
    return assessment(
        name,
        PASS,
        text,
        eid,
        {
            "observed": value,
            "threshold": limit,
            "time": extreme["time"],
            "peak_time": extreme["time"],
            "margin": margin,
        },
    )


def fail_not_empty(
    check, observation, limits, eid, seed, route, exit_place, document, world, frozen_record
):
    """Fail when any wall contact is recorded."""
    _require_measure(check)
    name = check["evaluator"]
    contacts = observation.get("wall_contacts")
    ok_shape = isinstance(contacts, list) and all(
        isinstance(c, dict) and _num(c.get("start")) and _num(c.get("depth")) for c in contacts
    )
    if not ok_shape:
        return _insufficient(name, "wall_contacts", eid, seed)
    if contacts:
        fails = [
            failure(name, c["depth"], 0.0, "m", c["start"], seed, wall=c.get("wall"))
            for c in contacts
        ]
        first = contacts[0]
        a, _ = _length(first["depth"], 0.0)
        more = f"; {len(contacts)} contacts" if len(contacts) > 1 else ""
        text = f"wall contact depth {a} m at {first['start']:.2f} s{_seed(seed)}{more}"
        return assessment(
            name,
            FAIL,
            text,
            eid,
            {
                "observed": len(contacts),
                "threshold": 0,
                "time": first["start"],
                "margin": -max(c["depth"] for c in contacts),
                "failures": fails,
            },
        )
    samples = _trace(observation)
    if samples and len(samples[0]) > 4:
        closest = min(samples, key=lambda s: s[4])
        text = f"no wall contact; closest {closest[4]:.3f} m at {closest[0]:.2f} s{_seed(seed)}"
        details = {"observed": 0, "threshold": 0, "time": closest[0], "margin": closest[4]}
    else:
        text, details = f"no wall contact{_seed(seed)}", {"observed": 0, "threshold": 0}
    return assessment(name, PASS, text, eid, details)


def fail_less(
    check, observation, limits, eid, seed, route, exit_place, document, world, frozen_record
):
    """Fail when the lowest base height is strictly under the limit."""
    _require_measure(check)
    name = check["evaluator"]
    extreme = _extreme(observation, "min_base_height")
    if extreme is None:
        return _insufficient(name, "min_base_height", eid, seed)
    value, limit = extreme["value"], _limit(check, limits)
    a, b = _length(value, limit)
    details = {
        "observed": value,
        "threshold": limit,
        "time": extreme["time"],
        "margin": round(value - limit, 6),
    }
    if value < limit:
        details["failures"] = [failure(name, value, limit, "m", extreme["time"], seed)]
        return assessment(
            name,
            FAIL,
            f"base height {a} m < {b} m at {extreme['time']:.2f} s{_seed(seed)}",
            eid,
            details,
        )
    return assessment(
        name,
        PASS,
        f"base height {a} m >= {b} m, lowest at {extreme['time']:.2f} s{_seed(seed)}",
        eid,
        details,
    )


def _contains(place, sample):
    if place.get("type") != "region":
        raise EvaluationError(
            f"ERROR: place {place.get('name')!r} has type {place.get('type')!r}. "
            "passes-through-places reads a region, boundaries included. "
            'Example: {"name": "corner", "type": "region", "x": [-0.4, 0.4], "y": [-0.4, 0.4]}.'
        )
    x0, x1 = place["x"]
    y0, y1 = place["y"]
    x, y = sample[1], sample[2]
    return (min(x0, x1) <= x <= max(x0, x1)) and (min(y0, y1) <= y <= max(y0, y1))


def fail_not_in_order(
    check, observation, limits, eid, seed, route, exit_place, document, world, frozen_record
):
    """Fail when a through-place is missed or entered out of order before the exit."""
    _require_measure(check)
    name = check["evaluator"]
    ordered = list(document["places"]["through"])
    if not ordered:
        return assessment(
            name,
            PASS,
            f"no place to pass through{_seed(seed)}",
            eid,
            {"observed": [], "threshold": []},
        )
    if not isinstance(world, dict):
        raise EvaluationError(
            "ERROR: passes-through-places needs the scenario world, which names each region. "
            "Example: assess(..., world=world) with a region place for every name in "
            "parameters.places.through."
        )
    places = {}
    for place in world.get("places") or []:
        if isinstance(place, dict) and isinstance(place.get("name"), str):
            places[place["name"]] = place
    samples = _trace(observation)
    crossing = first_crossing(samples, route, exit_place)
    crossing_time = None if crossing is None else crossing[0]
    entered_at = []
    previous = None
    for place_name in ordered:
        place = places.get(place_name)
        if place is None:
            return _insufficient(name, f"place {place_name}", eid, seed)
        entered = next((sample[0] for sample in samples if _contains(place, sample)), None)
        late = entered is None or crossing_time is None or entered > crossing_time
        out_of_order = previous is not None and entered is not None and entered < previous
        if late or out_of_order:
            failed = failure(name, entered, crossing_time, "s", entered, seed, place=place_name)
            text = f"did not pass through {place_name} in order before the exit{_seed(seed)}"
            return assessment(
                name,
                FAIL,
                text,
                eid,
                {
                    "observed": entered_at,
                    "threshold": ordered,
                    "time": entered,
                    "failures": [failed],
                },
            )
        entered_at.append({"place": place_name, "time": entered})
        previous = entered
    text = f"passed through {', '.join(ordered)} before the exit{_seed(seed)}"
    return assessment(
        name, PASS, text, eid, {"observed": entered_at, "threshold": ordered, "time": crossing_time}
    )


_RULES = {
    "absent-or-greater-than-limit": fail_absent_or_greater,
    "greater-than-limit": fail_greater,
    "not-empty": fail_not_empty,
    "less-than-limit": fail_less,
    "not-in-order": fail_not_in_order,
}


def _apply(
    check, observation, limits, eid, seed, route, exit_place, document, world, frozen_record
):
    rule = _RULES.get(check.get("fail_when"))
    if rule is None:
        raise EvaluationError(
            f"ERROR: unknown fail_when {check.get('fail_when')!r}. "
            f"Expected one of {', '.join(_RULES)}."
        )
    return rule(
        check, observation, limits, eid, seed, route, exit_place, document, world, frozen_record
    )


def assess(observation, thresholds, trial_id, seed=None, *, world=None, parameters=None):
    """One assessment per check in the parameter file, in that file's order.

    ``thresholds`` are the limits the verifier already resolved. ``world`` supplies
    the route and the exit; omitted, the frozen straight route is used.
    """
    if not isinstance(observation, dict):
        example = frozen_observation_format()
        raise EvaluationError(
            "ERROR: observation must be a JSON object. "
            f'Example: {{"format": "{example}", "end": "crossed_exit"}}.'
        )
    fmt = observation.get("format")
    if isinstance(fmt, str):
        unknown = unknown_observation(fmt)
        if unknown is not None:
            raise unknown
    document = parameters if parameters is not None else _default_parameters()
    limits = limits_from_thresholds(document, thresholds)
    frozen_record = world is None
    if world is None:
        route, exit_place = straight_route(limits["exit_segment"])
    else:
        route, exit_place = _route_from_world(world, document)
    return [
        _apply(
            check,
            observation,
            limits,
            trial_id,
            seed,
            route,
            exit_place,
            document,
            world,
            frozen_record,
        )
        for check in document["checks"]
    ]


def _one(name):
    def run(observation, thresholds, trial_id, seed=None):
        for item in assess(observation, thresholds, trial_id, seed):
            if item["evaluator"] == name:
                return item
        raise EvaluationError(f"ERROR: parameter file has no check {name!r}.")

    return run


EVALUATE = {name: _one(name) for name in EVALUATORS}
