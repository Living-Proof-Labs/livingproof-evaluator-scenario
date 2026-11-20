# SPDX-License-Identifier: Apache-2.0
"""The icon in a written result is the artwork file, byte for byte (Vera, verification of PR 28).

Gaps left by the first tests: a hash match between the file and the descriptor, the same string in
every written result and in both places, a clean file (no BOM, one line, one final newline), and
no fixed size, which the contract accepts but would fight the report's own sizing.
"""

from __future__ import annotations

import hashlib
import re
from importlib import resources
from xml.etree import ElementTree

from test_result import _one

from livingproof_evaluator_scenario.result import ICON


def _file_bytes() -> bytes:
    return (
        resources.files("livingproof_evaluator_scenario")
        .joinpath("scenario-evaluator-icon.svg")
        .read_bytes()
    )


def test_the_artwork_file_is_clean_utf8_on_one_line() -> None:
    raw = _file_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), "a byte order mark"
    text = raw.decode("utf-8")
    assert text.endswith("\n") and not text.endswith("\n\n")
    assert "\n" not in text[:-1] and "\r" not in text


def test_the_descriptor_and_envelope_icon_hash_equals_the_file() -> None:
    document, _ = _one()
    expected = hashlib.sha256(_file_bytes().strip()).hexdigest()
    for icon in (document["descriptor"]["icon"], document["evaluator"]["icon"]):
        assert hashlib.sha256(icon.encode("utf-8")).hexdigest() == expected


def test_the_icon_has_no_fixed_size_so_the_report_sizes_it() -> None:
    root = ElementTree.fromstring(ICON)
    assert "width" not in root.attrib and "height" not in root.attrib
    assert re.fullmatch(r"0 0 24 24", root.get("viewBox"))


def test_the_identity_around_the_icon_is_unchanged() -> None:
    document, _ = _one()
    evaluator, descriptor = document["evaluator"], document["descriptor"]
    assert {k: evaluator[k] for k in ("id", "kind", "execution", "display_name", "publisher")} == {
        "id": "livingproof-scenario",
        "kind": "scenario",
        "execution": "deterministic",
        "display_name": "Scenario",
        "publisher": "Living Proof Labs",
    }
    assert descriptor["icon_accessible_name"] == descriptor["title"] == "Scenario"
