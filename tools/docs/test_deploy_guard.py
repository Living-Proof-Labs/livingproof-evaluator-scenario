# SPDX-License-Identifier: Apache-2.0
"""Exercise the real manual delivery guards without GitHub or Pages."""

import hashlib
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml

MAIN_SHA = "a" * 40
STALE_SHA = "b" * 40
VERSION = "1.5.12"
TAG = f"v{VERSION}"
REPO = "example/repo"
BASE_ENV = {
    "CANDIDATE": MAIN_SHA,
    "SOURCE_COMMIT": MAIN_SHA,
    "GITHUB_SHA": MAIN_SHA,
    "GITHUB_REPOSITORY": REPO,
    "VERSION": VERSION,
    "MANUAL_VERSION": VERSION,
    "RELEASE_TAG": TAG,
    "GITHUB_RUN_ID": "123",
    "GITHUB_RUN_ATTEMPT": "2",
}


def workflow(name):
    # BaseLoader retains GitHub's `on` key and the literal spelling of conditionals.
    return yaml.load(Path(f".github/workflows/{name}.yml").read_text(), Loader=yaml.BaseLoader)


def step(job, name):
    return next(item["run"] for item in job["steps"] if item.get("name") == name)


def run(script, cwd, **overrides):
    return subprocess.run(
        ["bash", "-e", "-c", script],
        cwd=cwd,
        env={**os.environ, **BASE_ENV, **overrides},
        capture_output=True,
        text=True,
    )


def mock_bin(directory, name, source):
    mock = directory / name
    mock.write_text("#!/bin/bash\nset -eu\n" + source)
    mock.chmod(0o755)


class DeliveryGuardsTest(unittest.TestCase):
    def setUp(self):
        self.orchestrator = workflow("verify")
        self.docs = workflow("docs")
        self.deploy = self.orchestrator["jobs"]["deploy"]

    def test_writes_are_separated_from_build_and_replay(self):
        jobs = self.orchestrator["jobs"]
        self.assertEqual(set(self.docs["on"]), {"workflow_call"})
        self.assertEqual(self.docs["permissions"], {"contents": "read"})
        self.assertEqual(jobs["version"]["permissions"], {"contents": "read"})
        self.assertEqual(jobs["manual"]["permissions"], {"contents": "read"})
        self.assertEqual(jobs["release"]["permissions"], {"contents": "write"})
        self.assertEqual(jobs["release"]["needs"], ["verify", "version", "manual"])
        self.assertIn("github.event_name == 'push'", jobs["release"]["if"])
        self.assertNotIn("workflow_dispatch", jobs["release"]["if"])
        for field in ("version", "commit", "run-id", "attempt", "digest", "id"):
            self.assertIn(f"needs.manual.outputs.artifact-{field}", jobs["release"]["if"])
        for field in ("version", "commit"):
            self.assertIn(
                f"needs.manual.outputs.artifact-{field}",
                jobs["release"]["with"][f"expected-{field}"],
            )
        self.assertIn("needs.release.outputs.published == 'true'", self.deploy["if"])
        self.assertIn("github.event_name == 'workflow_dispatch'", self.deploy["if"])
        self.assertIn("needs.release.result == 'skipped'", self.deploy["if"])
        self.assertEqual(
            self.deploy["permissions"],
            {"contents": "read", "pages": "write", "id-token": "write"},
        )
        self.assertEqual(self.deploy["concurrency"]["cancel-in-progress"], "false")
        self.assertTrue(self.deploy["steps"][-1]["uses"].startswith("actions/deploy-pages@"))

    def test_current_main_fails_closed(self):
        guard = step(self.deploy, "Require current main inside deployment lock")
        with tempfile.TemporaryDirectory() as work:
            mock_bin(
                Path(work),
                "gh",
                '[[ "$*" == "api repos/example/repo/git/ref/heads/main --jq .object.sha" ]] '
                '|| exit 99\nprintf "%s\\n" "$MOCK_SHA"\nexit "$MOCK_EXIT"\n',
            )
            for label, response, api_exit in (
                ("current", MAIN_SHA, 0),
                ("stale", STALE_SHA, 0),
                ("malformed", "bad", 0),
                ("empty", "", 0),
                ("API failure", MAIN_SHA, 1),
            ):
                with self.subTest(label=label):
                    result = run(
                        guard,
                        work,
                        PATH=work + ":" + os.environ["PATH"],
                        MOCK_SHA=response,
                        MOCK_EXIT=str(api_exit),
                    )
                    self.assertEqual(result.returncode == 0, label == "current", result.stderr)

    def test_published_tag_must_resolve_to_the_exact_candidate(self):
        check = step(
            self.deploy, "Independently require the published stable release at the exact commit"
        )
        stable = {"tag_name": TAG, "draft": False, "prerelease": False, "published_at": "now"}
        light = f"{MAIN_SHA}\trefs/tags/{TAG}"
        annotated = f"{STALE_SHA}\trefs/tags/{TAG}\n{light}^{{}}"
        with tempfile.TemporaryDirectory() as work:
            mock_bin(
                Path(work),
                "git",
                '[[ "$*" == *"https://github.com/example/repo.git refs/tags/"* ]] || exit 99\n'
                'printf "%s\\n" "$MOCK_REFS"\nexit "$MOCK_GIT_EXIT"\n',
            )
            mock_bin(
                Path(work),
                "gh",
                '[[ "$*" == "api repos/example/repo/releases/tags/$RELEASE_TAG" ]] || exit 99\n'
                'printf "%s\\n" "$MOCK_RELEASE"\n',
            )
            cases = (
                ("lightweight", {}, light, stable, "0", True),
                ("annotated", {}, annotated, stable, "0", True),
                ("wrong SHA", {}, light.replace(MAIN_SHA, STALE_SHA), stable, "0", False),
                ("draft", {}, light, {**stable, "draft": True}, "0", False),
                ("unpublished", {}, light, {**stable, "published_at": None}, "0", False),
                ("prerelease", {}, light, {**stable, "prerelease": True}, "0", False),
                ("wrong release", {}, light, {**stable, "tag_name": "v1.5.11"}, "0", False),
                ("no ref", {}, "", stable, "2", False),
                ("input mismatch", {"RELEASE_TAG": "v1.5.11"}, light, stable, "0", False),
                ("event SHA mismatch", {"GITHUB_SHA": STALE_SHA}, light, stable, "0", False),
            )
            for label, overrides, refs, release, git_exit, ok in cases:
                with self.subTest(label=label):
                    result = run(
                        check,
                        work,
                        PATH=work + ":" + os.environ["PATH"],
                        MOCK_REFS=refs,
                        MOCK_RELEASE=json.dumps(release),
                        MOCK_GIT_EXIT=git_exit,
                        **overrides,
                    )
                    self.assertEqual(result.returncode == 0, ok, result.stderr)

    def test_transported_bytes_are_rechecked_before_tar(self):
        build = self.docs["jobs"]["build"]
        seal = step(build, "Seal the verified manual bytes for this attempt")
        readback = step(self.deploy, "Verify transport and package only the sealed HTML")
        for change in (
            "none",
            "metadata",
            "byte",
            "extra",
            "symlink",
            "wrong digest",
            "old attempt",
        ):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as work:
                tmp = Path(work)
                html = tmp / "artifacts/manual/html"
                html.mkdir(parents=True)
                index = html / "index.html"
                index.write_text("<html></html>")
                identity = {
                    "version": VERSION,
                    "source_commit": MAIN_SHA,
                    "source_dirty": False,
                    "run_id": "123",
                    "run_attempt": "2",
                }
                if change == "metadata":
                    identity["source_commit"] = STALE_SHA
                (html / "build.json").write_text(json.dumps(identity))
                output = tmp / "output"
                result = run(seal, tmp, GITHUB_OUTPUT=str(output))
                if change == "metadata":
                    self.assertNotEqual(result.returncode, 0)
                    continue
                self.assertEqual(result.returncode, 0, result.stderr)
                manifest = (html.parent / "site.sha256").read_bytes()
                digest = hashlib.sha256(manifest).hexdigest()
                self.assertIn(f"digest={digest}", output.read_text())
                if change == "byte":
                    index.write_text("different")
                if change == "extra":
                    (html / "extra.html").write_text("unlisted")
                if change == "symlink":
                    (html / "linked").symlink_to(index)
                html.parent.rename(tmp / "verified-manual")
                result = run(
                    readback,
                    tmp,
                    RUNNER_TEMP=work,
                    DIGEST="0" * 64 if change == "wrong digest" else digest,
                    GITHUB_RUN_ATTEMPT="1" if change == "old attempt" else "2",
                )
                self.assertEqual(result.returncode == 0, change == "none", result.stderr)
                self.assertEqual((tmp / "artifact.tar").is_file(), change == "none")


if __name__ == "__main__":
    unittest.main()
