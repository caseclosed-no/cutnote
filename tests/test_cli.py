from xml.etree import ElementTree as ET

import pytest
from typer.testing import CliRunner

from cutnote import RenderOptions, render_note
from cutnote.cli import app

runner = CliRunner()


@pytest.mark.parametrize(
    "args", [["--help"], ["render", "--help"], ["gui", "--help"], ["--version"]]
)
def test_help_and_version(args):
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    assert "cutnote" in result.output.lower()


def test_file_output_equals_shared_renderer(tmp_path):
    target = tmp_path / "note.svg"
    result = runner.invoke(
        app, ["render", "Meet me at midnight.", "--seed", "42", "-o", str(target)]
    )
    assert result.exit_code == 0, result.output
    assert target.read_bytes() == render_note(
        "Meet me at midnight.", RenderOptions(seed=42)
    ).svg.encode("utf-8")
    assert "Seed 42" in result.stderr


def test_utf8_file_with_bom(tmp_path):
    source = tmp_path / "message.txt"
    source.write_text("Hemmelig møte.\nZażółć gęślą jaźń.", encoding="utf-8-sig")
    result = runner.invoke(app, ["render", "--file", str(source), "--seed", "7", "-o", "-"])
    assert result.exit_code == 0, result.output
    ET.fromstring(result.stdout)
    assert "Seed 7" not in result.stdout


def test_stdin_and_stdout():
    result = runner.invoke(app, ["render", "-o", "-", "--seed", "1"], input="Read the clues.\n")
    assert result.exit_code == 0, result.output
    ET.fromstring(result.stdout)
    assert result.stdout == render_note("Read the clues.\n", RenderOptions(seed=1)).svg
    assert "Seed 1" in result.stderr


@pytest.mark.parametrize(
    "args,input_text",
    [
        (["render"], ""),
        (["render", "text", "--file", "unused.txt"], ""),
        (["render", "text"], "second source"),
        (["render", "--file", "unused.txt"], "second source"),
        (["render", "text", "--width", "0"], ""),
        (["render", "text", "--seed", "-1"], ""),
        (["render", "text", "--preset", "invalid"], ""),
        (["render", "--file", "does-not-exist.txt"], ""),
    ],
)
def test_input_and_option_errors(args, input_text):
    result = runner.invoke(app, args, input=input_text)
    assert result.exit_code == 2
    assert "error" in result.output.lower()


def test_unwritable_output_error(tmp_path):
    result = runner.invoke(app, ["render", "text", "-o", str(tmp_path)])
    assert result.exit_code == 2
    assert "Error:" in result.stderr
