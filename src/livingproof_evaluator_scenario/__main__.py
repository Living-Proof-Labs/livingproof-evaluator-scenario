# SPDX-License-Identifier: Apache-2.0
"""Write one result file per trial of a hallway evidence manifest.

The caller supplies the thresholds. This module does not grade the run and
does not edit a bundle.

    python -m livingproof_evaluator_scenario evidence/manifest.json \\
        --thresholds thresholds.json --out evaluator-results/livingproof-scenario
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from livingproof_evaluator_scenario.result import write_run


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("manifest", type=Path, help="livingproof-hallway-evidence/2.0.0 manifest")
    parser.add_argument(
        "--thresholds",
        type=Path,
        required=True,
        help="JSON object of time_limit, lateral_limit, half_width, and fall_height",
    )
    parser.add_argument(
        "--out", type=Path, required=True, help="Directory for one JSON file per trial"
    )
    parser.add_argument("--started-at", help="UTC timestamp, default the current minute")
    parser.add_argument("--completed-at", help="UTC timestamp, default the current minute")
    args = parser.parse_args(argv)
    started = args.started_at or _now()
    completed = args.completed_at or started
    thresholds = json.loads(args.thresholds.read_text(encoding="utf-8"))
    written = write_run(
        args.manifest, thresholds, args.out, started_at=started, completed_at=completed
    )
    for path in written:
        print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
