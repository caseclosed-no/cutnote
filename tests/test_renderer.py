import hashlib
import json
import math
import re
from importlib.resources import files
from xml.etree import ElementTree as ET

import pytest

from cutnote import RenderOptions, render_note
from cutnote.fonts import bundled_fonts
from cutnote.renderer import BACKGROUNDS, MODES, PRESETS, SVG_NS

NS = {"s": SVG_NS}


def fragments(svg: str) -> list[str]:
    return [
        n.attrib["data-fragment"] for n in ET.fromstring(svg).iter() if "data-fragment" in n.attrib
    ]


def test_vendored_fonts_and_licenses_match_provenance():
    root = files("cutnote").joinpath("assets", "fonts")
    provenance = json.loads(root.joinpath("provenance.json").read_text(encoding="utf-8"))
    assert len(bundled_fonts()) == 6
    for name, entry in provenance["files"].items():
        assert hashlib.sha256(root.joinpath(name).read_bytes()).hexdigest() == entry["sha256"]
    assert len([name for name in provenance["files"] if name.endswith(".txt")]) == 4


def test_seed_reproduces_exact_output_and_can_replay_generated_seed():
    options = RenderOptions(seed=42)
    first = render_note("Meet me at midnight.", options)
    assert first == render_note("Meet me at midnight.", options)
    assert first.svg != render_note("Meet me at midnight.", RenderOptions(seed=43)).svg
    generated = render_note("Fresh cutouts")
    assert generated == render_note("Fresh cutouts", RenderOptions(seed=generated.seed))


@pytest.mark.parametrize("preset", PRESETS)
@pytest.mark.parametrize("mode", MODES)
def test_presets_and_modes_preserve_text_and_use_only_vectors(preset, mode):
    text = "Read between the lines!"
    result = render_note(text, RenderOptions(seed=42, preset=preset, mode=mode))
    root = ET.fromstring(result.svg)
    parts = fragments(result.svg)
    assert "".join(parts) == text.replace(" ", "")
    if mode == "words":
        assert parts == text.split()
    elif mode == "letters":
        assert all(len(part) == 1 for part in parts)
    assert root.find("s:desc", NS).text == text
    assert root.findall(".//s:path", NS)
    assert root.findall(".//s:polygon", NS)
    assert not root.findall(".//s:text", NS)
    assert not root.findall(".//s:image", NS)
    assert not root.findall(".//s:filter", NS)
    assert root.attrib["viewBox"] == f"0 0 {result.width} {result.height}"
    metadata = json.loads(root.find("s:metadata", NS).text)
    assert metadata["seed"] == result.seed


def test_mixed_mode_produces_varied_fragment_lengths():
    text = "Read between the lines and follow the clues to discover something unexpected."
    parts = fragments(render_note(text, RenderOptions(seed=42)).svg)
    assert any(len(part) > 1 for part in parts)
    assert any(len(part) == 1 for part in parts)


def test_accents_and_canonical_unicode_normalization():
    text = "Hemmelig møte. ÆØÅ æøå. Zażółć gęślą jaźń!"
    result = render_note(text, RenderOptions(seed=7))
    assert "".join(fragments(result.svg)) == text.replace(" ", "")
    assert render_note("café", RenderOptions(seed=7)) == render_note(
        "cafe\u0301", RenderOptions(seed=7)
    )


def test_whitespace_line_breaks_and_wrapping():
    options = RenderOptions(seed=42, mode="words", width=1000)
    normal = render_note("One two", options)
    assert normal == render_note("One \t  two", options)
    lines = render_note("One\ntwo", options)
    blank = render_note("One\n\ntwo", options)
    assert normal.height < lines.height < blank.height
    long_text = "Find the secret map and read between the lines. " * 3
    assert (
        render_note(long_text, RenderOptions(seed=42, width=320)).height
        > render_note(long_text, RenderOptions(seed=42, width=1000)).height
    )


@pytest.mark.parametrize("background", BACKGROUNDS)
def test_background(background):
    root = ET.fromstring(render_note("Paper", RenderOptions(background=background, seed=1)).svg)
    page = root.find("s:rect", NS)
    if background == "transparent":
        assert page is None
    else:
        assert page.attrib["fill"] == ("#ffffff" if background == "white" else "#eee8da")


def test_xml_markup_is_escaped_and_never_becomes_executable_elements():
    text = '<script>alert("hello")</script> & <image href="x"/>'
    root = ET.fromstring(render_note(text, RenderOptions(seed=2)).svg)
    assert root.find("s:desc", NS).text == text
    assert not root.findall(".//s:script", NS)
    assert not root.findall(".//s:image", NS)


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("seed", [0, 17, 42])
def test_all_rotated_paper_and_shadows_fit_canvas_including_oversized_words(mode, seed):
    result = render_note(
        "Supercalifragilisticexpialidocious\nÅgypj Meet me at midnight.",
        RenderOptions(seed=seed, width=320, font_size=144, mode=mode),
    )
    root = ET.fromstring(result.svg)
    placements = [
        node
        for node in root.findall(".//s:g", NS)
        if node.find("s:g[@data-fragment]", NS) is not None
    ]
    assert placements
    for placement in placements:
        cx, cy, scale, angle, tx, ty = map(
            float, re.findall(r"-?\d+(?:\.\d+)?", placement.attrib["transform"])
        )
        c, s = math.cos(math.radians(angle)), math.sin(math.radians(angle))
        for polygon in placement.findall("s:g/s:polygon", NS):
            shadow_x, shadow_y = (1.5, 2) if "transform" in polygon.attrib else (0, 0)
            for pair in polygon.attrib["points"].split():
                px, py = map(float, pair.split(","))
                x, y = px + shadow_x + tx, py + shadow_y + ty
                page_x, page_y = cx + scale * (x * c - y * s), cy + scale * (x * s + y * c)
                assert -0.25 <= page_x <= result.width + 0.25
                assert -0.25 <= page_y <= result.height + 0.25


@pytest.mark.parametrize("text", ["", " \t\n", "x" * 10001, "bad\x00text", "bad\ud800text"])
def test_invalid_text_is_rejected(text):
    with pytest.raises(ValueError):
        render_note(text)


def test_unsupported_character_error_is_actionable():
    with pytest.raises(ValueError, match="U\\+1F600"):
        render_note("Hello 😀")


def test_maximum_length_word_remains_visible_when_scaled_down():
    result = render_note(
        "W" * 10000, RenderOptions(seed=42, mode="words", width=320, font_size=144)
    )
    root = ET.fromstring(result.svg)
    placement = root.find("s:g/s:g", NS)
    scale = float(re.search(r"scale\(([^)]+)\)", placement.attrib["transform"]).group(1))
    assert scale > 0
    paper = placement.find("s:g/s:polygon", NS)
    paper_width = max(float(pair.split(",")[0]) for pair in paper.attrib["points"].split())
    assert 0 < paper_width * scale < result.width


@pytest.mark.parametrize(
    "kwargs",
    [
        {"width": 0},
        {"width": 50000},
        {"width": float("nan")},
        {"font_size": 0},
        {"font_size": True},
        {"seed": -1},
        {"seed": 2**32},
        {"seed": "42"},
        {"preset": "unknown"},
        {"mode": "unknown"},
        {"background": "unknown"},
        {"height": 0},
        {"height": "100%"},
        {"font_size": "large"},
        {"width": "-21cm"},
        {"palette": "unknown"},
        {"palette": "custom"},
        {"palette": "custom", "colors": ("red",)},
        {"palette": "custom", "colors": ("#abc",) * 17},
        {"colors": ("#ff0000",)},
    ],
)
def test_options_are_validated(kwargs):
    with pytest.raises(ValueError):
        render_note("Hello", RenderOptions(**kwargs))
