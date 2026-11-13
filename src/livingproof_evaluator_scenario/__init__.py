# SPDX-License-Identifier: Apache-2.0
"""Deterministic scenario evaluator.

Checks come from the scenario parameter file. A later slice adds the Gherkin
vocabulary and the MCAP runner. Already-recorded evidence stays readable
through :mod:`livingproof_evaluator_scenario.compat`.
"""

from livingproof_evaluator_scenario.checks import EVALUATE, EVALUATORS
from livingproof_evaluator_scenario.result import package_version, trial_result

__all__ = ["EVALUATE", "EVALUATORS", "package_version", "trial_result"]
