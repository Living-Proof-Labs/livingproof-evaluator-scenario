# SPDX-License-Identifier: Apache-2.0
"""Test-system errors. A robot grade is never ``ERROR``."""


class EvaluationError(Exception):
    """The evaluator cannot grade this input. ``status`` is ``ERROR``."""

    def __init__(self, message: str):
        text = message if str(message).startswith("ERROR") else f"ERROR: {message}"
        super().__init__(text)
        self.status = "ERROR"
