# SPDX-License-Identifier: Apache-2.0
"""Scenario names stay in the compatibility package.

This file is allowlisted because it has to name the strings it searches for.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN = ("walk-hallway", "hallway-open", "hallway")
ALLOW = (
    "src/livingproof_evaluator_scenario/compat/",
    "tests/test_scenario_names.py",
)


def test_scenario_names_stay_in_the_compatibility_module():
    bad = []
    for base in ("src", "tools", "tests"):
        for path in (ROOT / base).rglob("*.py"):
            relative = path.relative_to(ROOT).as_posix()
            if any(relative == item or relative.startswith(item) for item in ALLOW):
                continue
            text = path.read_text(encoding="utf-8")
            for name in FORBIDDEN:
                if name in text:
                    bad.append(f"{relative}: {name}")
    assert bad == []
