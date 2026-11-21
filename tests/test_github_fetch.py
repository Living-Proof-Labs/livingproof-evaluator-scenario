# SPDX-License-Identifier: Apache-2.0
"""One shared fetch for the network-gated tests: token when available, one retry (#48).

The three LIVINGPROOF_NETWORK tests (guidelines interface, docs brand lock, fixture lock hash) fetch
through ``tests/github_fetch.py``. It sends GITHUB_TOKEN (CI passes github.token) to GitHub hosts
only, and retries once on a transient network error or HTTP 403/429. A hash mismatch is checked by
the caller after the fetch and is never retried.
"""

from __future__ import annotations

import io
import urllib.error
from pathlib import Path

import pytest
from github_fetch import fetch

TESTS = Path(__file__).parent
URL = "https://raw.githubusercontent.com/Living-Proof-Labs/x/main/y"


class _Reply:
    def __init__(self, body: bytes):
        self.body = body

    def __enter__(self):
        return io.BytesIO(self.body)

    def __exit__(self, *exc):
        return False


def _script(*steps):
    """An opener that plays ``steps`` in turn: an exception is raised, bytes are returned."""
    calls = []

    def opener(request, timeout):
        calls.append(request)
        step = steps[len(calls) - 1]
        if isinstance(step, BaseException):
            raise step
        return _Reply(step)

    return opener, calls


def _http(code):
    return urllib.error.HTTPError("https://example.invalid", code, "x", {}, None)


def _fetch(url, opener, token=None):
    return fetch(url, token, opener, lambda _: None)


@pytest.mark.parametrize(
    "first", [_http(403), _http(429), urllib.error.URLError("reset"), TimeoutError()]
)
def test_a_transient_failure_is_retried_once(first):
    opener, calls = _script(first, b"ok")
    assert _fetch(URL, opener) == b"ok"
    assert len(calls) == 2


def test_a_second_failure_is_raised_not_retried_again():
    opener, calls = _script(_http(429), _http(429), b"never")
    with pytest.raises(urllib.error.HTTPError):
        _fetch(URL, opener)
    assert len(calls) == 2


@pytest.mark.parametrize("code", [404, 500])
def test_other_http_errors_are_not_retried(code):
    opener, calls = _script(_http(code), b"never")
    with pytest.raises(urllib.error.HTTPError):
        _fetch(URL, opener)
    assert len(calls) == 1


def test_the_token_is_sent_to_github_when_given():
    opener, calls = _script(b"ok")
    _fetch(URL, opener, token="t0k")
    assert calls[0].get_header("Authorization") == "Bearer t0k"


def test_the_token_comes_from_github_token_when_none_is_passed(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "from-env")
    opener, calls = _script(b"ok")
    _fetch(URL, opener)
    assert calls[0].get_header("Authorization") == "Bearer from-env"


def test_no_token_means_no_authorization_header(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    opener, calls = _script(b"ok")
    _fetch(URL, opener)
    assert calls[0].get_header("Authorization") is None


def test_the_token_is_never_sent_to_another_host():
    opener, calls = _script(b"ok")
    _fetch("https://example.invalid/x", opener, token="t0k")
    assert calls[0].get_header("Authorization") is None


@pytest.mark.parametrize(
    "name",
    [
        "test_guidelines_pins.py",
        "test_docs_brand_lock.py",
        "test_fall_pass_fixture_lock_network.py",
    ],
)
def test_each_network_test_fetches_through_the_shared_helper(name):
    text = (TESTS / name).read_text()
    assert "from github_fetch import" in text
    assert "urlopen" not in text
