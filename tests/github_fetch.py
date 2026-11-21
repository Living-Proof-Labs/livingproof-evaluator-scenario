# SPDX-License-Identifier: Apache-2.0
"""The one fetch the network-gated tests use (#48).

GITHUB_TOKEN (CI passes github.token) is sent to GitHub hosts only. The fetch is retried once, after
a short pause, on a transient network error or HTTP 403/429; anything else, and a second failure, is
raised. Only the fetch is retried: callers compare what came back, and a mismatch is never retried.
"""

from __future__ import annotations

import os
import time
import urllib.error
import urllib.parse
import urllib.request

GITHUB_HOSTS = {"raw.githubusercontent.com", "api.github.com"}
RETRY_STATUS = (403, 429)


def fetch(url: str, token: str | None = None, opener=urllib.request.urlopen, pause=time.sleep):
    """GET ``url`` and return the body bytes."""
    token = token or os.environ.get("GITHUB_TOKEN")
    headers = {}
    if token and urllib.parse.urlparse(url).hostname in GITHUB_HOSTS:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)
    for attempt in (1, 2):
        try:
            with opener(request, timeout=30) as response:
                return response.read()
        except urllib.error.HTTPError as error:
            if error.code not in RETRY_STATUS or attempt == 2:
                raise
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            if attempt == 2:
                raise
        pause(2)
    raise AssertionError("unreachable")
