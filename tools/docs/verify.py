# SPDX-License-Identifier: Apache-2.0
"""Check generated HTML links, fragments and required shared branding offline."""

import json
import os
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit


class Page(HTMLParser):
    def __init__(self, path):
        super().__init__()
        self.ids = set()
        self.links = []
        self.text = []
        self.brand = False
        self.feed(path.read_text())

    def handle_starttag(self, tag, attributes):
        attrs = dict(attributes)
        if "id" in attrs:
            self.ids.add(attrs["id"])
        for key in ("href", "src"):
            if key in attrs:
                self.links.append(attrs[key])
        if tag == "link" and attrs.get("href", "").endswith("assets/brand.css"):
            self.brand = True
        assert attrs.get("data-md-color-primary") != "indigo", "Unexpected stock palette"

    def handle_data(self, data):
        self.text.append(data)


root = Path("artifacts/site").resolve()
pages = {p: Page(p) for p in root.rglob("*.html")}
assert root / "index.html" in pages, "Missing landing page"
for path, page in pages.items():
    assert page.brand, f"Missing shared brand: {path}"
    for link in page.links:
        url = urlsplit(link)
        if url.scheme or url.netloc or link.startswith("/"):
            continue
        target = (path.parent / unquote(url.path)).resolve() if url.path else path
        if target.is_dir():
            target /= "index.html"
        assert target.exists(), f"{path.name}: missing {link}"
        if url.fragment and target in pages:
            assert unquote(url.fragment) in pages[target].ids, f"{path.name}: missing {link}"
build = json.loads((root / "build.json").read_text())
expected = os.environ.get("MANUAL_VERSION", "development")
assert build["version"] == expected, "Manual metadata does not match the planned version"
version_page = pages[root / "version.html"]
assert f"Documentation version: {expected}" in " ".join(" ".join(version_page.text).split()), (
    "The planned documentation version is not visible in the rendered manual"
)
print(f"PASS: {len(pages)} HTML pages; local links/fragments and brand verified")
