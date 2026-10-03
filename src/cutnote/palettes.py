"""Text palettes and contrasting paper colors, independent of typography."""

import random
import re

PALETTES = {
    "auto": (),
    "newspaper": ("#22211e", "#34312a", "#161718", "#f8f3e6"),
    "magazine": ("#fff9e8", "#1e2426", "#182a25", "#322026", "#27221e"),
    "mixed": (
        "#22211e",
        "#34312a",
        "#161718",
        "#f8f3e6",
        "#fff9e8",
        "#1e2426",
        "#182a25",
        "#322026",
        "#27221e",
    ),
    "black-and-white": ("#000000", "#ffffff"),
    "primary": ("#ff0000", "#0000ff", "#ffcc00"),
    "rainbow": ("#ff0000", "#ff8000", "#ffdd00", "#00aa00", "#0066ff", "#8800ff"),
    "neon": ("#ff00ff", "#00ffff", "#bfff00", "#ffff00", "#ff3300"),
    "warm": ("#dd0000", "#ff5500", "#ffaa00", "#990000"),
    "cool": ("#0000ff", "#0088ff", "#00aa88", "#6600cc"),
    "grayscale": ("#000000", "#444444", "#888888", "#cccccc", "#ffffff"),
    "custom": (),
}


def normalize_colors(colors: list[str] | tuple[str, ...]) -> tuple[str, ...]:
    if not isinstance(colors, (list, tuple)) or not 1 <= len(colors) <= 16:
        raise ValueError("A custom palette needs between 1 and 16 hex colors.")
    result = []
    for color in colors:
        if not isinstance(color, str) or not re.fullmatch(
            r"#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3})?", color
        ):
            raise ValueError("Colors must use #RGB or #RRGGBB notation (e.g. #ff0000).")
        color = color.lower()
        if len(color) == 4:
            color = "#" + "".join(char * 2 for char in color[1:])
        result.append(color)
    return tuple(result)


def luminance(color: str) -> float:
    channels = [int(color[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    channels = [v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in channels]
    return sum(value * weight for value, weight in zip(channels, (0.2126, 0.7152, 0.0722)))


def contrast(first: str, second: str) -> float:
    low, high = sorted((luminance(first), luminance(second)))
    return (high + 0.05) / (low + 0.05)


def clipping_colors(
    preset: str,
    palette: str,
    custom_colors: tuple[str, ...],
    rng: random.Random,
) -> tuple[str, str]:
    neutral = ("#ffffff", "#f7f4e9", "#e8e4d8", "#000000")
    colorful = ("#ff0000", "#ffcc00", "#0044ff", "#00bb44", "#ff33bb", "#ffffff")
    if palette in ("auto", "newspaper", "magazine", "mixed"):
        style = preset if palette == "auto" else palette
        use_color = style == "magazine" or (style == "mixed" and rng.random() < 0.5)
        if use_color:
            return rng.choice(
                (
                    ("#c44032", "#fff9e8"),
                    ("#ecc443", "#1e2426"),
                    ("#253d62", "#fff9e8"),
                    ("#a8c5b9", "#182a25"),
                    ("#f0a3b1", "#322026"),
                    ("#f5e8cd", "#27221e"),
                )
            )
        paper = rng.choice(("#ece3ce", "#f8f3e6", "#d6cbb6", "#e2dac9", "#fffcf4"))
        ink = rng.choice(("#22211e", "#34312a", "#161718"))
        return ("#292823", "#f8f3e6") if rng.random() < 0.08 else (paper, ink)
    ink = rng.choice(custom_colors if palette == "custom" else PALETTES[palette])
    papers = neutral
    if preset == "magazine":
        papers = colorful + neutral
    elif preset == "mixed":
        papers = neutral + colorful
    candidates = [paper for paper in papers if contrast(ink, paper) >= 4.5]
    if not candidates:
        candidates = [max(("#000000", "#ffffff"), key=lambda paper: contrast(ink, paper))]
    return rng.choice(candidates), ink
