"""Seeded typography, paper geometry, and layout shared by every interface."""

import json
import math
import random
import re
import secrets
import unicodedata
from dataclasses import asdict, dataclass, replace
from xml.etree import ElementTree as ET

from .fonts import Font, bundled_fonts, number
from .palettes import PALETTES, clipping_colors, luminance, normalize_colors
from .units import FACTORS, LengthValue, parse_length

SVG_NS = "http://www.w3.org/2000/svg"
ET.register_namespace("", SVG_NS)
PRESETS = ("newspaper", "magazine", "mixed")
MODES = ("mixed", "letters", "words")
BACKGROUNDS = ("paper", "white", "transparent")
MAX_TEXT = 10_000


@dataclass(frozen=True)
class RenderOptions:
    preset: str = "newspaper"
    mode: str = "mixed"
    width: LengthValue = 1000
    font_size: LengthValue = 48
    background: str = "paper"
    seed: int | None = None
    height: LengthValue | None = None
    palette: str = "auto"
    colors: tuple[str, ...] = ()

    def validate(self) -> None:
        for label, value, choices in (
            ("preset", self.preset, PRESETS),
            ("mode", self.mode, MODES),
            ("background", self.background, BACKGROUNDS),
            ("palette", self.palette, tuple(PALETTES)),
        ):
            if value not in choices:
                raise ValueError(f"{label} must be one of: {', '.join(choices)}.")
        for label, value, low, high in (
            ("width", self.width, 64, 16384),
            ("font_size", self.font_size, 4, 512),
            ("height", self.height, 64, 16384),
        ):
            if value is None and label == "height":
                continue
            pixels = parse_length(value, label).pixels
            if not low <= pixels <= high:
                raise ValueError(
                    f"{label} must be between {low} and {high} px, or equivalent physical units."
                )
        if self.seed is not None and (
            type(self.seed) is not int or not 0 <= self.seed <= 2**32 - 1
        ):
            raise ValueError("seed must be an integer between 0 and 4294967295.")
        if self.palette == "custom":
            normalize_colors(self.colors)
        elif self.colors:
            raise ValueError("Set palette to custom when supplying colors.")


@dataclass(frozen=True)
class RenderResult:
    svg: str
    seed: int
    width: int | float
    height: int | float


@dataclass
class Clipping:
    element: ET.Element
    width: float
    height: float
    angle: float

    @property
    def rotated_size(self) -> tuple[float, float]:
        angle = math.radians(self.angle)
        c, s = abs(math.cos(angle)), abs(math.sin(angle))
        return self.width * c + self.height * s, self.width * s + self.height * c


def element(tag: str, parent: ET.Element | None = None, **attributes: str) -> ET.Element:
    attrs = {key.replace("_", "-"): value for key, value in attributes.items()}
    node = ET.Element(f"{{{SVG_NS}}}{tag}", attrs)
    if parent is not None:
        parent.append(node)
    return node


def _normalize(text: str) -> str:
    if not isinstance(text, str):
        raise ValueError("Text must be a string.")
    if len(text) > MAX_TEXT:
        raise ValueError(f"Text must contain at most {MAX_TEXT:,} characters.")
    if not text.strip():
        raise ValueError("Enter some text to create a note.")
    text = unicodedata.normalize("NFC", text.replace("\r\n", "\n").replace("\r", "\n"))
    if any(unicodedata.category(c) in ("Cc", "Cs") and c not in "\n\t" for c in text):
        raise ValueError("Text contains unsupported control characters.")
    return "\n".join(" ".join(line.split()) for line in text.split("\n"))


def _fragments(word: str, mode: str, rng: random.Random) -> list[str]:
    if mode == "words":
        return [word]
    if mode == "letters":
        return list(word)
    choice = rng.random()
    if choice < 0.22:
        return [word]
    if choice < 0.65:
        return list(word)
    pieces, start = [], 0
    while start < len(word):
        end = start + rng.randint(2, 3)
        pieces.append(word[start:end])
        start = end
    return pieces


def _lettering(text: str, font: Font, size: float) -> tuple[ET.Element, float, float]:
    scale = size / font.units
    glyphs = []
    cursor = 0.0
    ink_bounds = []
    for char in text:
        glyph = font.glyph(char)
        glyphs.append((cursor, glyph))
        if glyph.bounds:
            x0, y0, x1, y1 = glyph.bounds
            ink_bounds.append((cursor + x0, y0, cursor + x1, y1))
        cursor += glyph.advance
    if not ink_bounds:
        raise ValueError(f"No visible lettering for {text!r}.")
    x0 = min(b[0] for b in ink_bounds)
    y0 = min(b[1] for b in ink_bounds)
    x1 = max(b[2] for b in ink_bounds)
    y1 = max(b[3] for b in ink_bounds)
    group = element("g", transform=f"scale({number(scale, 9)} {number(-scale, 9)})")
    for cursor, glyph in glyphs:
        if glyph.path:
            element(
                "path",
                group,
                d=glyph.path,
                transform=f"translate({number(cursor - x0)} {number(-y1)})",
            )
    return group, (x1 - x0) * scale, (y1 - y0) * scale


def _paper_points(width: float, height: float, rng: random.Random) -> str:
    roughness = min(2.2, height * 0.035)
    points = [(0.0, 0.0)]
    for step in range(1, 6):
        points.append((width * step / 6, rng.uniform(0, roughness)))
    points.append((width, 0.0))
    for step in range(1, 4):
        points.append((width - rng.uniform(0, roughness), height * step / 4))
    points.append((width, height))
    for step in range(5, 0, -1):
        points.append((width * step / 6, height - rng.uniform(0, roughness)))
    points.append((0.0, height))
    for step in range(3, 0, -1):
        points.append((rng.uniform(0, roughness), height * step / 4))
    return " ".join(f"{number(x)},{number(y)}" for x, y in points)


def _clipping(
    text: str,
    options: RenderOptions,
    rng: random.Random,
    index: int,
    color_rng: random.Random,
) -> Clipping:
    fonts = bundled_fonts()
    candidates = [font for font in fonts if font.supports(text)]
    # Fonts always cover the entire fragment, including its accented letters.
    weights = [4 if font.name.startswith("Old Standard") else 2 for font in candidates]
    if options.preset == "magazine":
        weights = [1 if font.name.startswith("Old Standard") else 4 for font in candidates]
    font = rng.choices(candidates, weights=weights, k=1)[0]
    size = options.font_size * rng.uniform(0.82, 1.22)
    letters, ink_width, ink_height = _lettering(text, font, size)
    px, py = size * rng.uniform(0.13, 0.23), size * rng.uniform(0.10, 0.19)
    width, height = ink_width + 2 * px, ink_height + 2 * py
    angle = rng.uniform(-8, 8)
    paper, ink = clipping_colors(options.preset, options.palette, options.colors, color_rng)
    group = element("g", data_fragment=text, data_font=font.name)
    points = _paper_points(width, height, rng)
    element(
        "polygon",
        group,
        points=points,
        fill="#221b13",
        opacity="0.16",
        transform="translate(1.5 2)",
    )
    element("polygon", group, points=points, fill=paper)
    clip_id = f"paper-{index}"
    defs = element("defs", group)
    clip = element("clipPath", defs, id=clip_id)
    element("polygon", clip, points=points)
    grain = element(
        "g",
        group,
        clip_path=f"url(#{clip_id})",
        fill="#000000" if luminance(paper) > 0.3 else "#ffffff",
        opacity="0.08",
    )
    for _ in range(min(100, max(5, int(width * height / 140)))):
        element(
            "ellipse",
            grain,
            cx=number(rng.uniform(0, width)),
            cy=number(rng.uniform(0, height)),
            rx=number(rng.uniform(0.15, 0.55)),
            ry=number(rng.uniform(0.12, 0.4)),
        )
    ink_group = element("g", group, fill=ink, transform=f"translate({number(px)} {number(py)})")
    ink_group.append(letters)
    return Clipping(group, width, height, angle)


def render_note(text: str, options: RenderOptions | None = None) -> RenderResult:
    """Render deterministically when a seed is supplied; never perform I/O."""
    options = options or RenderOptions()
    options.validate()
    text = _normalize(text)
    unsupported = sorted(
        {c for c in text if not c.isspace() and not any(f.supports(c) for f in bundled_fonts())}
    )
    if unsupported:
        chars = ", ".join(f"{c!r} (U+{ord(c):04X})" for c in unsupported[:12])
        raise ValueError(f"Bundled fonts do not support these characters: {chars}.")
    seed = options.seed if options.seed is not None else secrets.randbits(32)
    options = replace(options, seed=seed)
    rng = random.Random(seed)
    color_rng = random.Random(seed ^ 0xC0104)
    page_width = parse_length(options.width)
    page_height = parse_length(options.height) if options.height is not None else None
    font_length = parse_length(options.font_size)
    options = replace(
        options,
        width=page_width.pixels if page_width.unit == "px" else page_width.svg,
        height=(page_height.pixels if page_height.unit == "px" else page_height.svg)
        if page_height
        else None,
        font_size=font_length.pixels if font_length.unit == "px" else font_length.svg,
    )
    if options.palette == "custom":
        options = replace(options, colors=normalize_colors(options.colors))
    metadata = {"generator": "cutnote", "version": "0.1.0", "text": text, **asdict(options)}
    options = replace(options, width=page_width.pixels, font_size=font_length.pixels)
    root = element("svg", width=page_width.svg, role="img")
    element("title", root).text = "Cutout note"
    element("desc", root).text = text
    element("metadata", root).text = json.dumps(metadata, ensure_ascii=False, sort_keys=True)
    margin = min(max(20, options.font_size * 0.6), options.width * 0.18)
    available = options.width - margin * 2
    fragment_gap = options.font_size * 0.07 + 3
    word_gap = options.font_size * 0.35
    row_gap = options.font_size * 0.30
    min_row_height = options.font_size * 1.2
    paper_layer = element("g")
    x, y, row_height = margin, margin, 0.0
    count = 0

    def new_row() -> None:
        nonlocal x, y, row_height
        y += max(row_height, min_row_height) + row_gap
        x, row_height = margin, 0.0

    for line_index, line in enumerate(text.split("\n")):
        if line_index:
            new_row()
        for word in re.findall(r"\S+", line):
            clips = []
            for part in _fragments(word, options.mode, rng):
                # A word may combine characters covered by different fonts.
                parts = [part] if any(f.supports(part) for f in bundled_fonts()) else list(part)
                for supported_part in parts:
                    clips.append(_clipping(supported_part, options, rng, count, color_rng))
                    count += 1
            word_width = sum(c.rotated_size[0] + 3 for c in clips)
            word_width += fragment_gap * (len(clips) - 1)
            if x > margin and x + word_width > options.width - margin:
                new_row()
            for clipping in clips:
                bw, bh = clipping.rotated_size
                # Include the rotated shadow in each clipping's reserved box.
                bw, bh = bw + 3, bh + 3
                scale = min(1.0, available / bw)
                bw, bh = bw * scale, bh * scale
                if x > margin and x + bw > options.width - margin:
                    new_row()
                jitter = rng.uniform(0, options.font_size * 0.11)
                placement = element(
                    "g",
                    paper_layer,
                    transform=(
                        f"translate({number(x + bw / 2)} {number(y + jitter + bh / 2)}) "
                        f"scale({number(scale, 9)}) rotate({number(clipping.angle)}) "
                        f"translate({number(-clipping.width / 2)} {number(-clipping.height / 2)})"
                    ),
                )
                placement.append(clipping.element)
                row_height = max(row_height, bh + jitter)
                x += bw + fragment_gap
            x += word_gap - fragment_gap
    natural_height = math.ceil(y + max(row_height, min_row_height) + margin)
    height = page_height.pixels if page_height else natural_height
    if page_height:
        root.set("height", page_height.svg)
        if natural_height > height:
            fit = height / natural_height
            paper_layer.set(
                "transform",
                (f"translate({number(options.width * (1 - fit) / 2)}) scale({number(fit, 9)})"),
            )
    else:
        root.set(
            "height",
            number(height / FACTORS[page_width.unit], 6)
            + (page_width.unit if page_width.unit != "px" else ""),
        )
    root.set("viewBox", f"0 0 {number(options.width, 6)} {number(height, 6)}")
    if options.background != "transparent":
        element(
            "rect",
            root,
            width="100%",
            height="100%",
            fill="#eee8da" if options.background == "paper" else "#ffffff",
        )
    root.append(paper_layer)
    svg = '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode") + "\n"
    return RenderResult(svg, seed, options.width, height)
