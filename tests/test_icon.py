# SPDX-License-Identifier: Apache-2.0
"""The scenario evaluator's icon is the artwork file, and it stays inside the report's SVG subset.

The report (livingproof-capability-report) inlines an evaluator icon only when it passes the subset
in the evaluator contract (livingproof-evaluator, docs/evaluator-descriptor.md, "Icons"). This
repository does not import the report, so this test restates that subset.
"""

import re
from importlib import resources
from xml.etree import ElementTree

from livingproof_evaluator_scenario.result import ICON

SVG = "http://www.w3.org/2000/svg"
ALLOWED_ELEMENTS = {"path", "circle", "rect", "g"}
ALLOWED_PAINT = {"currentColor", "none", "transparent"}
ICON_LIMIT_BYTES = 8192


def _artwork() -> str:
    return (
        resources.files("livingproof_evaluator_scenario")
        .joinpath("scenario-evaluator-icon.svg")
        .read_text(encoding="utf-8")
    )


def _walk(element):
    yield element
    for child in element:
        yield from _walk(child)


def test_the_declared_icon_is_the_artwork_file():
    assert ICON == _artwork().strip()


def test_icon_is_inside_the_report_subset():
    assert len(ICON.encode("utf-8")) <= ICON_LIMIT_BYTES
    for forbidden in ("<?", "<!", "&", "url(", "http:", "https:", "data:", "javascript:"):
        assert forbidden not in ICON.replace(f'xmlns="{SVG}"', "")
    root = ElementTree.fromstring(ICON)
    assert root.tag == f"{{{SVG}}}svg"
    assert root.get("viewBox") == "0 0 24 24"
    for element in _walk(root):
        name = element.tag.split("}")[-1]
        if element is not root:
            assert name in ALLOWED_ELEMENTS, name
        assert not (element.text or "").strip()
        for attribute, value in element.attrib.items():
            assert not attribute.lower().startswith("on"), attribute
            assert attribute not in {"style", "href", "src", "srcset"}, attribute
            if attribute.lower() in {"fill", "stroke"}:
                assert value in ALLOWED_PAINT, (name, attribute, value)


def test_icon_paints_with_current_colour_only():
    """No hex colour, so the report's own colours apply on light and dark."""
    assert not re.search(r"#[0-9A-Fa-f]{3,8}\b", ICON)
    assert ICON.count("currentColor") >= 2


def test_icon_has_no_title_text_or_raster():
    for tag in ("<title", "<text", "<image", "<style", "<use", "<script"):
        assert tag not in ICON
