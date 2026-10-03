"""Typer entry points for file rendering and the local editor."""

import sys
from enum import StrEnum
from pathlib import Path
from typing import Annotated

import typer

from . import __version__
from .fonts import number
from .renderer import MAX_TEXT, RenderOptions, render_note

app = typer.Typer(
    name="cutnote", help="Create newspaper cutout notes as portable SVGs.", no_args_is_help=True
)


class Preset(StrEnum):
    newspaper = "newspaper"
    magazine = "magazine"
    mixed = "mixed"


class Mode(StrEnum):
    mixed = "mixed"
    letters = "letters"
    words = "words"


class Background(StrEnum):
    paper = "paper"
    white = "white"
    transparent = "transparent"


class Palette(StrEnum):
    auto = "auto"
    newspaper = "newspaper"
    magazine = "magazine"
    mixed = "mixed"
    black_and_white = "black-and-white"
    primary = "primary"
    rainbow = "rainbow"
    neon = "neon"
    warm = "warm"
    cool = "cool"
    grayscale = "grayscale"
    custom = "custom"


def _version(value: bool) -> None:
    if value:
        typer.echo(f"cutnote {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        bool, typer.Option("--version", callback=_version, is_eager=True, help="Show version.")
    ] = False,
) -> None:
    pass


@app.command()
def render(
    text: Annotated[
        str | None, typer.Argument(help="Quoted note text; omit for file or stdin.")
    ] = None,
    file: Annotated[Path | None, typer.Option("--file", help="Read a UTF-8 text file.")] = None,
    output: Annotated[
        str, typer.Option("--output", "-o", help="SVG path, or - for stdout.")
    ] = "note.svg",
    preset: Annotated[
        Preset, typer.Option(help="Clipping typography and paper style.")
    ] = Preset.newspaper,
    mode: Annotated[Mode, typer.Option(help="How to split text into clippings.")] = Mode.mixed,
    width: Annotated[str, typer.Option(help="Page width, e.g. 1000, 210mm, or 21cm.")] = "1000",
    font_size: Annotated[str, typer.Option(help="Letter size, e.g. 48, 10mm, or 1cm.")] = "48",
    height: Annotated[
        str | None, typer.Option(help="Fixed page height, e.g. 297mm; default auto.")
    ] = None,
    palette: Annotated[Palette, typer.Option(help="Text color palette.")] = Palette.auto,
    color: Annotated[
        list[str] | None,
        typer.Option("--color", help="Custom text hex color; repeat for more colors."),
    ] = None,
    background: Annotated[Background, typer.Option(help="Page background.")] = Background.paper,
    seed: Annotated[
        int | None, typer.Option(min=0, max=2**32 - 1, help="Repeatable random seed.")
    ] = None,
) -> None:
    """Render quoted text, a file, or piped stdin to an SVG."""
    try:
        piped = not sys.stdin.isatty()
        if text is not None and file is not None:
            raise ValueError("Use either quoted text or --file, not both.")
        # Read a bounded amount, also detecting an explicitly supplied second source.
        stdin_text = sys.stdin.read(MAX_TEXT + 1) if piped else ""
        if stdin_text and (text is not None or file is not None):
            raise ValueError("Use only one input source: quoted text, --file, or piped stdin.")
        if file is not None:
            with file.open(encoding="utf-8-sig") as handle:
                source = handle.read(MAX_TEXT + 1)
        elif text is not None:
            source = text
        elif stdin_text:
            source = stdin_text
        else:
            raise ValueError("Provide quoted text, --file, or piped stdin.")
        result = render_note(
            source,
            RenderOptions(
                preset=preset.value,
                mode=mode.value,
                width=width,
                font_size=font_size,
                background=background.value,
                seed=seed,
                height=None if height is None or height.lower() == "auto" else height,
                palette="custom" if color and palette == Palette.auto else palette.value,
                colors=tuple(color or ()),
            ),
        )
        if output == "-":
            typer.echo(result.svg.encode("utf-8"), nl=False)
        else:
            Path(output).write_text(result.svg, encoding="utf-8", newline="")
        typer.echo(
            f"Seed {result.seed} | {number(result.width)} x {number(result.height)} px | {output}",
            err=True,
        )
    except (ValueError, OSError, UnicodeError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(2) from exc


@app.command()
def gui(
    port: Annotated[
        int, typer.Option(min=0, max=65535, help="Local port; 0 chooses a free port.")
    ] = 0,
    no_browser: Annotated[
        bool, typer.Option(help="Print the URL without opening a browser.")
    ] = False,
) -> None:
    """Launch the offline browser editor. Stop with Ctrl+C."""
    from .server import serve_gui

    try:
        serve_gui(port=port, open_browser=not no_browser)
    except OSError as exc:
        typer.echo(f"Error: could not start the editor: {exc}", err=True)
        raise typer.Exit(2) from exc
