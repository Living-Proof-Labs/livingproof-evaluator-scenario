# SPDX-License-Identifier: Apache-2.0
"""The fall-PASS fixture's recorded lock hash matches the real lock in livingproof-verification.

PROVENANCE.json names the lock that drove the run (repository, commit, path, sha256). This fetches
that file at that commit and checks its sha256, so the recorded hash cannot drift from the source.
The fetch is gated: set LIVINGPROOF_NETWORK=1 to run it (GITHUB_TOKEN is used when set, to avoid
the anonymous rate limit). The path is read from PROVENANCE.json and not written here, because
scenario names stay out of the tests (test_scenario_names).
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest
from github_fetch import fetch as _fetch

ROOT = Path(__file__).resolve().parents[1]
PROVENANCE = ROOT / "tests" / "fixtures" / "sim-v3.8.1-g1-playground" / "PROVENANCE.json"
COMMIT = "4e23501bb3c7539406ead420e76721d52a444caf"


def _lock() -> dict:
    return json.loads(PROVENANCE.read_text())["generator"]["lock_nominal_pins"]["lock"]


def test_the_recorded_lock_names_the_commit_and_a_sha256():
    lock = _lock()
    assert lock["repository"] == "Living-Proof-Labs/livingproof-verification"
    assert lock["commit"] == COMMIT
    assert len(lock["sha256"]) == 64 and lock["path"].endswith(".lock.json")


@pytest.mark.skipif(not os.environ.get("LIVINGPROOF_NETWORK"), reason="set LIVINGPROOF_NETWORK=1")
def test_the_recorded_lock_sha256_matches_the_lock_at_that_commit():
    lock = _lock()
    url = f"https://raw.githubusercontent.com/{lock['repository']}/{lock['commit']}/{lock['path']}"
    body = _fetch(url, os.environ.get("GITHUB_TOKEN"))
    actual = hashlib.sha256(body).hexdigest()
    assert actual == lock["sha256"], (
        f"sha256 of {url} (commit {lock['commit']}) is {actual}, "
        f"but PROVENANCE.json records {lock['sha256']}"
    )


def test_a_hash_mismatch_names_the_url_and_commit_and_is_not_retried(monkeypatch):
    """Vera, PR 47: the fetch is the only retried step; a wrong body fails on the first fetch and
    the message names the URL, the commit and both hashes. Calls the network test body directly
    (marks apply at collection only) with the fetch replaced, so it runs offline."""
    import sys

    module = sys.modules[__name__]
    calls = []

    def fake_fetch(url, token):
        calls.append(url)
        return b"not the lock"

    monkeypatch.setattr(module, "_fetch", fake_fetch)
    lock = _lock()
    with pytest.raises(AssertionError) as caught:
        test_the_recorded_lock_sha256_matches_the_lock_at_that_commit()
    message = str(caught.value)
    assert len(calls) == 1
    assert calls[0] in message and lock["commit"] in message
    assert lock["sha256"] in message and hashlib.sha256(b"not the lock").hexdigest() in message
