# SPDX-License-Identifier: Apache-2.0
"""Exercise the actual workflow shell guard with isolated GitHub API responses."""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml


class FreshnessGuardTest(unittest.TestCase):
    def test_workflow_guard(self):
        workflow = yaml.safe_load(Path(".github/workflows/docs.yml").read_text())
        steps = workflow["jobs"]["deploy"]["steps"]
        guard = steps[-2]
        self.assertEqual(guard["name"], "Reject stale main builds")
        self.assertTrue(steps[-1]["uses"].startswith("actions/deploy-pages@"))
        self.assertFalse(workflow["concurrency"]["cancel-in-progress"])
        for label, response, api_exit, expected in (
            ("current", "a" * 40, 0, 0),
            ("stale", "b" * 40, 0, 1),
            ("empty", "", 0, 1),
            ("api failure", "", 1, 1),
        ):
            with self.subTest(label=label), tempfile.TemporaryDirectory() as directory:
                gh = Path(directory) / "gh"
                gh.write_text(
                    "#!/bin/bash\n"
                    '[[ "$*" == "api repos/example/repo/git/ref/heads/main --jq .object.sha" ]] '
                    "|| exit 99\n"
                    'printf "%s\\n" "$MOCK_SHA"\nexit "$MOCK_EXIT"\n'
                )
                gh.chmod(0o755)
                result = subprocess.run(
                    ["bash", "-c", guard["run"]],
                    env={
                        **os.environ,
                        "PATH": directory + ":" + os.environ["PATH"],
                        "GITHUB_SHA": "a" * 40,
                        "GITHUB_REPOSITORY": "example/repo",
                        "MOCK_SHA": response,
                        "MOCK_EXIT": str(api_exit),
                    },
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(result.returncode, expected, result.stderr)


if __name__ == "__main__":
    unittest.main()
