"""One version, read two ways, agreeing.

The application stamps ``__version__`` into every session.json while the
packaging scripts were told a number on the command line, and nothing compared
the two: a .deb built as 0.1.10 contained an application reporting 0.1.2, and
every recording made with it is labelled with a version that never existed.

The scripts now read src/multycapture/_version.py, but they read it with sed
rather than by importing it — they run where MultyCapture is not installed. So
the thing worth testing is that the text match and the Python value still
describe the same number, and that a package built from this tree would carry
it.
"""

from __future__ import annotations

import ast
import re
import subprocess
import sys
from pathlib import Path

import pytest

import multycapture

ROOT = Path(__file__).resolve().parent.parent
VERSION_SH = ROOT / "installer" / "version.sh"


def test_the_version_looks_like_a_version():
    assert re.fullmatch(r"\d+\.\d+\.\d+", multycapture.__version__)


@pytest.mark.skipif(sys.platform == "win32", reason="no POSIX shell")
def test_the_packaging_scripts_read_the_same_number():
    """installer/version.sh is what the .deb and the .iss are told."""
    printed = subprocess.run(
        ["sh", str(VERSION_SH)], capture_output=True, text=True, check=True,
    ).stdout.strip()
    assert printed == multycapture.__version__


def test_the_version_file_holds_exactly_one_assignment_and_no_code():
    """The sed match depends on _version.py staying plain.

    A computed version would still work in Python and silently stop matching,
    which is the failure this whole arrangement exists to prevent. Holding the
    string in its own file makes that unlikely; asserting it makes it loud.
    """
    source = (ROOT / "src" / "multycapture" / "_version.py").read_text(encoding="utf-8")

    assignments = re.findall(r'^VERSION = "([^"]*)"$', source, re.MULTILINE)
    assert assignments == [multycapture.__version__]

    # Parsed rather than filtered by line: a docstring is prose at column 0 and
    # is indistinguishable from a statement without reading the syntax.
    body = ast.parse(source).body
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
        body = body[1:]                                     # the docstring

    assert len(body) == 1, (
        "_version.py grew something besides the version; installer/version.sh "
        "reads it with sed and cannot follow logic"
    )
    (statement,) = body
    assert isinstance(statement, ast.Assign)
    assert isinstance(statement.value, ast.Constant), "the version must be a literal"
    assert statement.value.value == multycapture.__version__


def test_a_recording_stamps_the_real_version():
    """session.json's app_version defaults to the module's value."""
    import inspect

    from multycapture.capture.recorder import Recorder

    default = inspect.signature(Recorder.__init__).parameters["app_version"].default
    assert default == multycapture.__version__


@pytest.mark.skipif(sys.platform == "win32", reason="no POSIX shell")
def test_the_windows_installer_refuses_to_guess():
    """No literal fallback in the .iss.

    A default there is a number nobody chose, attached to an installer that
    claims to be a release.
    """
    iss = (ROOT / "installer" / "windows" / "multycapture.iss").read_text(encoding="utf-8")
    assert "#error" in iss
    assert not re.search(r'#define\s+MyAppVersion\s+"\d', iss)
