"""SVG/CSS absolute lengths: physical units use 96 pixels per inch."""

import math
import re
from dataclasses import dataclass

from .fonts import number

FACTORS = {"px": 1.0, "mm": 96 / 25.4, "cm": 96 / 2.54, "in": 96.0, "pt": 96 / 72}
LengthValue = int | float | str


@dataclass(frozen=True)
class Length:
    value: float
    unit: str

    @property
    def pixels(self) -> int | float:
        pixels = self.value * FACTORS[self.unit]
        return int(pixels) if pixels.is_integer() else pixels

    @property
    def svg(self) -> str:
        return number(self.value, 6) + (self.unit if self.unit != "px" else "")


def parse_length(value: LengthValue, label: str = "Length") -> Length:
    if isinstance(value, str):
        match = re.fullmatch(r"\s*(\d+(?:\.\d*)?|\.\d+)\s*(px|mm|cm|in|pt)?\s*", value.lower())
        if not match:
            raise ValueError(f"{label} must be a number with px, mm, cm, in, or pt (e.g. 210mm).")
        amount, unit = float(match[1]), match[2] or "px"
    elif type(value) in (int, float):
        amount, unit = float(value), "px"
    else:
        raise ValueError(f"{label} must be a number or a length such as 210mm.")
    if not math.isfinite(amount) or amount <= 0:
        raise ValueError(f"{label} must be a finite, positive length.")
    return Length(amount, unit)
