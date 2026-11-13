# SPDX-License-Identifier: Apache-2.0
"""Readers that keep already-recorded evidence usable.

Generic modules import this package. The frozen format names and the
scenario they belong to stay in :mod:`livingproof_evaluator_scenario.compat.recorded`.
"""

from livingproof_evaluator_scenario.compat.recorded import (
    allowed_ends,
    departure_state,
    departure_text,
    evidence_manifest_help,
    frozen_observation_format,
    limits_alias,
    outside_segment_text,
    parameters_document,
    require_evidence_format,
    straight_route,
    unknown_observation,
)

__all__ = [
    "allowed_ends",
    "departure_state",
    "departure_text",
    "evidence_manifest_help",
    "frozen_observation_format",
    "limits_alias",
    "outside_segment_text",
    "parameters_document",
    "require_evidence_format",
    "straight_route",
    "unknown_observation",
]
