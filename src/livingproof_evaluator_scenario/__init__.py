# SPDX-License-Identifier: Apache-2.0
"""Deterministic scenario evaluator.

The hallway checks in :mod:`livingproof_evaluator_scenario.checks` are the
bodies moved from ``capability_verifier.hallway``. A later slice adds the
Gherkin vocabulary and the MCAP runner.
"""

from livingproof_evaluator_scenario.checks import EVALUATE, EVALUATORS
from livingproof_evaluator_scenario.result import package_version, trial_result

__all__ = ["EVALUATE", "EVALUATORS", "package_version", "trial_result"]
