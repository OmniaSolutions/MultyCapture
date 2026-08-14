"""The version. This file holds nothing else.

Everything that needs the number reads it from here:

    Python          from ._version import VERSION      (re-exported as
                                                        multycapture.__version__)
    packaging       sh installer/version.sh            (sed, no import)
    pyproject       [tool.setuptools.dynamic]
    session.json    stamped as app_version on every recording

A file with one job can be parsed by one line of sed and cannot grow an import
that quietly breaks the match. That is the whole reason it is separate from
__init__.py — and it is a Python module rather than a plain VERSION.txt
because PyInstaller follows imports, not data files: a text file would have to
be listed in the spec, and would be missing from the frozen application the day
someone forgot.

To release: change the line below, then tag v<that number>. CI compares the two
and refuses to build a tag that disagrees.
"""

VERSION = "0.2.0"
