import json
import re
from xml.etree import ElementTree as ET

import pytest
from typer.testing import CliRunner

from cutnote import RenderOptions, render_note
from cutnote.cli import app
from cutnote.palettes import PALETTES, contrast, normalize_colors
from cutnote.renderer import SVG_NS
from cutnote.units import parse_length

NS = {"s": SVG_NS}


@pytest.mark.parametrize(
    "value,expected",
    [
        (96, 96),
        (96.5, 96.5),
        ("96px", 96),
        ("25.4mm", 96),
        ("2.54cm", 96),
        ("1in", 96),
        ("72pt", 96),
        (" 21 CM ", 96 * 21 / 2.54),
    ],
)
def test_absolute_lengths(value, expected):
    assert parse_length(value).pixels == pytest.approx(expected)


@pytest.mark.parametrize(
    "value", [True, None, [], "100%", "auto", "nan", "-1mm", "0cm", float("inf")]
)
def test_invalid_lengths(value):
    with pytest.raises(ValueError):
        parse_length(value)


def test_metric_width_and_auto_height_are_real_svg_physical_dimensions():
    result = render_note(
        "Meet me at midnight.", RenderOptions(width="21cm", font_size="10mm", seed=42)
    )
    root = ET.fromstring(result.svg)
    assert root.attrib["width"] == "21cm"
    assert root.attrib["height"].endswith("cm")
    assert result.width == pytest.approx(210 * 96 / 25.4)
    assert parse_length(root.attrib["height"]).pixels == pytest.approx(result.height, abs=0.0001)
    assert list(map(float, root.attrib["viewBox"].split())) == pytest.approx(
        [0, 0, result.width, result.height]
    )


def test_a4_export_keeps_exact_size_and_fits_overflowing_content():
    result = render_note(
        "Read between the lines. " * 40,
        RenderOptions(width="210mm", height="297mm", font_size="15mm", seed=42),
    )
    root = ET.fromstring(result.svg)
    assert root.attrib["width"] == "210mm"
    assert root.attrib["height"] == "297mm"
    assert result.height == pytest.approx(297 * 96 / 25.4)
    layer = root.find("s:g", NS)
    fit = float(re.search(r"scale\(([^)]+)\)", layer.attrib["transform"])[1])
    assert 0 < fit < 1


def test_unitless_dimensions_stay_pixels_and_decimal_values_work():
    root = ET.fromstring(render_note("Hello", RenderOptions(width=500.5, seed=42)).svg)
    assert root.attrib["width"] == "500.5"


@pytest.mark.parametrize("palette", [p for p in PALETTES if p not in ("auto", "custom")])
def test_every_palette_renders_its_text_colors(palette):
    result = render_note(
        "Read between the lines and follow the clues.",
        RenderOptions(palette=palette, mode="letters", seed=42),
    )
    root = ET.fromstring(result.svg)
    for clipping in root.findall(".//s:g[@data-fragment]", NS):
        ink = clipping.find("s:g[@transform]", NS).attrib["fill"]
        assert ink in PALETTES[palette]
        if palette not in ("newspaper", "magazine", "mixed"):
            paper = clipping.findall("s:polygon", NS)[1].attrib["fill"]
            assert contrast(ink, paper) >= 4.5


def test_original_magazine_pairs_are_preserved():
    root = ET.fromstring(
        render_note(
            "Keep the old colors too.", RenderOptions(palette="magazine", mode="letters", seed=42)
        ).svg
    )
    pairs = {
        ("#c44032", "#fff9e8"),
        ("#ecc443", "#1e2426"),
        ("#253d62", "#fff9e8"),
        ("#a8c5b9", "#182a25"),
        ("#f0a3b1", "#322026"),
        ("#f5e8cd", "#27221e"),
    }
    for clipping in root.findall(".//s:g[@data-fragment]", NS):
        paper = clipping.findall("s:polygon", NS)[1].attrib["fill"]
        ink = clipping.find("s:g[@transform]", NS).attrib["fill"]
        assert (paper, ink) in pairs


def test_custom_colors_are_normalized_and_not_replaced():
    assert normalize_colors(["#F00", "#00Aaff"]) == ("#ff0000", "#00aaff")
    result = render_note(
        "A custom note", RenderOptions(palette="custom", colors=("#12aBcD",), seed=7)
    )
    root = ET.fromstring(result.svg)
    for clipping in root.findall(".//s:g[@data-fragment]", NS):
        assert clipping.find("s:g[@transform]", NS).attrib["fill"] == "#12abcd"
    assert json.loads(root.find("s:metadata", NS).text)["colors"] == ["#12abcd"]


def test_changing_palette_keeps_typography_and_positions():
    roots = [
        ET.fromstring(
            render_note("Keep the layout the same.", RenderOptions(palette=p, seed=42)).svg
        )
        for p in ("newspaper", "rainbow", "neon")
    ]

    def geometry(root):
        return [
            (
                node.tag,
                node.attrib.get("transform"),
                node.attrib.get("d"),
                node.attrib.get("data-fragment"),
                node.attrib.get("data-font"),
            )
            for node in root.iter()
            if node.tag != f"{{{SVG_NS}}}metadata"
        ]

    assert geometry(roots[0]) == geometry(roots[1]) == geometry(roots[2])


def test_cli_metric_page_and_custom_colors():
    result = CliRunner().invoke(
        app,
        [
            "render",
            "Colorful note.",
            "--width",
            "21cm",
            "--height",
            "29.7cm",
            "--font-size",
            "10mm",
            "--color",
            "#f00",
            "--color",
            "#00f",
            "--seed",
            "42",
            "-o",
            "-",
        ],
    )
    assert result.exit_code == 0, result.output
    root = ET.fromstring(result.stdout)
    assert root.attrib["width"] == "21cm"
    assert root.attrib["height"] == "29.7cm"
    assert json.loads(root.find("s:metadata", NS).text)["colors"] == ["#ff0000", "#0000ff"]


def test_cli_rejects_conflicting_palette_and_custom_colors():
    result = CliRunner().invoke(app, ["render", "Hello", "--palette", "rainbow", "--color", "#f00"])
    assert result.exit_code == 2
    assert "custom" in result.stderr
