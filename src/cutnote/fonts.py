"""Read bundled fonts and cache vector glyph outlines, never system fonts."""

from dataclasses import dataclass
from functools import lru_cache
from importlib.resources import files
from io import BytesIO

from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.ttLib import TTFont


def number(value: float, precision: int = 3) -> str:
    return f"{value:.{precision}f}".rstrip("0").rstrip(".") or "0"


@dataclass(frozen=True)
class Glyph:
    path: str
    advance: float
    bounds: tuple[float, float, float, float] | None


class Font:
    def __init__(self, name: str, filename: str):
        self.name = name
        data = files("cutnote").joinpath("assets", "fonts", filename).read_bytes()
        self.font = TTFont(BytesIO(data), lazy=False)
        self.cmap = self.font.getBestCmap() or {}
        self.glyphs = self.font.getGlyphSet()
        self.units = self.font["head"].unitsPerEm

    def supports(self, text: str) -> bool:
        return all(ord(char) in self.cmap for char in text)

    @lru_cache(maxsize=2048)
    def glyph(self, char: str) -> Glyph:
        name = self.cmap[ord(char)]
        outline = SVGPathPen(self.glyphs, ntos=number)
        bounds = BoundsPen(self.glyphs)
        self.glyphs[name].draw(outline)
        self.glyphs[name].draw(bounds)
        return Glyph(outline.getCommands(), self.glyphs[name].width, bounds.bounds)


@lru_cache(maxsize=1)
def bundled_fonts() -> tuple[Font, ...]:
    return tuple(
        Font(name, filename)
        for name, filename in (
            ("Old Standard Regular", "OldStandard-Regular.ttf"),
            ("Old Standard Bold", "OldStandard-Bold.ttf"),
            ("Old Standard Italic", "OldStandard-Italic.ttf"),
            ("Anton", "Anton-Regular.ttf"),
            ("Bebas Neue", "BebasNeue-Regular.ttf"),
            ("Special Elite", "SpecialElite-Regular.ttf"),
        )
    )
