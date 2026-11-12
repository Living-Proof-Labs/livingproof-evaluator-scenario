# SPDX-License-Identifier: Apache-2.0
"""Walk-hallway step checks.

Moved unchanged from ``capability_verifier.hallway`` (``exit_reached``,
``lateral_limit``, ``wall_contact``, ``fall``, and the helpers they call).
The bodies are the behaviour the stored G1 run already graded. The Gherkin
vocabulary is a later slice.
"""

from __future__ import annotations

import math

PASS, FAIL, INSUFFICIENT = "PASS", "FAIL", "INSUFFICIENT_EVIDENCE"
# Assessment version recorded on each check. This is not the package version.
VERSION = "1.0.0"
EVALUATORS = (
    "hallway-exit-reached",
    "hallway-lateral-limit",
    "hallway-wall-contact",
    "hallway-fall",
)
OBSERVATION_FORMAT = "livingproof-hallway-observation/2.0.0"
# Trial ends each observation format may report. Anything else is malformed.
OBSERVATION_ENDS = {
    "livingproof-hallway-observation/1.0.0": {"crossed_exit", "time_limit", "non_finite_state"},
    OBSERVATION_FORMAT: {"crossed_exit", "time_limit", "non_finite_state", "left_hallway"},
}


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
    """Structured failed check, so a report can group failures."""
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


def _exit_y(o, t):
    """The base's y in the trace sample at time ``t`` (the exit crossing), or None."""
    samples = (o.get("trace") or {}).get("samples")
    if not isinstance(samples, list):
        return None
    at = [s for s in samples if isinstance(s, list) and len(s) > 2 and s[0] == t and _num(s[2])]
    return at[-1][2] if at else None


def exit_reached(o, th, eid, seed=None):
    """PASS only for a crossed_exit through the exit segment (|y| <= half-width) in time.
    A left_hallway end (through a wall, or the exit line outside the segment) is a FAIL;
    an exit whose crossing point cannot be read is INSUFFICIENT, never a PASS."""
    name = "hallway-exit-reached"
    if "exit_time" not in o or not (o["exit_time"] is None or _num(o["exit_time"])):
        return _insufficient(name, "exit_time", eid, seed)
    end = o.get("end")
    if end not in OBSERVATION_ENDS.get(o.get("format"), ()):
        return _insufficient(name, "end", eid, seed)
    t, limit, half = o["exit_time"], th["time_limit"], th["half_width"]
    if end == "left_hallway":
        left = o.get("left_hallway")
        if t is not None or not (isinstance(left, dict) and _num(left.get("time"))):
            return _insufficient(name, "left_hallway", eid, seed)
        via = left.get("via")
        if not (isinstance(via, str) and via.strip()):
            # Where it left is part of the evidence: without it the FAIL cannot be exported.
            return _insufficient(name, "left_hallway.via", eid, seed)
        f = failure(name, None, limit, "s", left["time"], seed, via=via)
        text = f"left the hallway via {via} at {left['time']:.2f} s{_seed(seed)}"
        return assessment(
            name,
            FAIL,
            text,
            eid,
            {"observed": None, "threshold": limit, "time": left["time"], "failures": [f]},
        )
    if (t is None) != (end != "crossed_exit"):
        return _insufficient(name, "exit_time", eid, seed)
    if t is not None:
        y = _exit_y(o, t)
        if y is None:
            return _insufficient(name, "exit crossing point", eid, seed)
        if abs(y) > half:
            a, b = _length(abs(y), half)
            f = failure(name, abs(y), half, "m", t, seed, via="exit-outside-segment")
            text = f"exit line crossed at |y| {a} m > {b} m, outside the exit{_seed(seed)}"
            details = {"observed": abs(y), "threshold": half, "time": t, "failures": [f]}
            return assessment(name, FAIL, text, eid, details)
    if t is None:
        end = o.get("duration_s") if _num(o.get("duration_s")) else limit
        f = failure(name, None, limit, "s", end, seed)
        text = f"exit not reached by {limit:.2f} s{_seed(seed)}"
        return assessment(
            name, FAIL, text, eid, {"observed": None, "threshold": limit, "failures": [f]}
        )
    margin = round(limit - t, 4)
    if t > limit:
        f = failure(name, t, limit, "s", t, seed)
        text = f"exit {t:.2f} s > {limit:.2f} s at {t:.2f} s{_seed(seed)}"
        return assessment(
            name,
            FAIL,
            text,
            eid,
            {"observed": t, "threshold": limit, "time": t, "margin": margin, "failures": [f]},
        )
    text = f"exit at {t:.2f} s <= {limit:.2f} s ({margin:.2f} s spare){_seed(seed)}"
    return assessment(
        name, PASS, text, eid, {"observed": t, "threshold": limit, "time": t, "margin": margin}
    )


def lateral_limit(o, th, eid, seed=None):
    name = "hallway-lateral-limit"
    e = _extreme(o, "max_abs_lateral")
    if e is None:
        return _insufficient(name, "max_abs_lateral", eid, seed)
    v, limit = e["value"], th["lateral_limit"]
    margin = round(limit - v, 6)
    a, b = _length(v, limit)
    if v > limit:
        # First time over the limit, from the trace when it is present.
        t = next(
            (s[0] for s in (o.get("trace") or {}).get("samples", []) if abs(s[2]) > limit),
            e["time"],
        )
        f = failure(name, v, limit, "m", t, seed)
        text = f"lateral {a} m > {b} m at {t:.2f} s{_seed(seed)}"
        return assessment(
            name,
            FAIL,
            text,
            eid,
            {
                "observed": v,
                "threshold": limit,
                "time": t,
                "peak_time": e["time"],
                "margin": margin,
                "failures": [f],
            },
        )
    text = f"lateral {a} m <= {b} m, largest at {e['time']:.2f} s{_seed(seed)}"
    return assessment(
        name,
        PASS,
        text,
        eid,
        {
            "observed": v,
            "threshold": limit,
            "time": e["time"],
            "peak_time": e["time"],
            "margin": margin,
        },
    )


def wall_contact(o, th, eid, seed=None):
    name = "hallway-wall-contact"
    contacts = o.get("wall_contacts")
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
    samples = (o.get("trace") or {}).get("samples") or []
    if samples and len(samples[0]) > 4:
        closest = min(samples, key=lambda s: s[4])
        text = f"no wall contact; closest {closest[4]:.3f} m at {closest[0]:.2f} s{_seed(seed)}"
        details = {"observed": 0, "threshold": 0, "time": closest[0], "margin": closest[4]}
    else:
        text, details = f"no wall contact{_seed(seed)}", {"observed": 0, "threshold": 0}
    return assessment(name, PASS, text, eid, details)


def fall(o, th, eid, seed=None):
    name = "hallway-fall"
    e = _extreme(o, "min_base_height")
    if e is None:
        return _insufficient(name, "min_base_height", eid, seed)
    v, limit = e["value"], th["fall_height"]
    a, b = _length(v, limit)
    details = {"observed": v, "threshold": limit, "time": e["time"], "margin": round(v - limit, 6)}
    if v < limit:
        details["failures"] = [failure(name, v, limit, "m", e["time"], seed)]
        return assessment(
            name, FAIL, f"base height {a} m < {b} m at {e['time']:.2f} s{_seed(seed)}", eid, details
        )
    return assessment(
        name,
        PASS,
        f"base height {a} m >= {b} m, lowest at {e['time']:.2f} s{_seed(seed)}",
        eid,
        details,
    )


EVALUATE = {
    "hallway-exit-reached": exit_reached,
    "hallway-lateral-limit": lateral_limit,
    "hallway-wall-contact": wall_contact,
    "hallway-fall": fall,
}
