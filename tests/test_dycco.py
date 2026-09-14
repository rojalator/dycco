from pathlib import Path

from src.dycco import dycco

# We read files from this directory. New files can be added with an appropriate test
# or tests in this directory
SOURCE_FILE_DIR = 'input_files/'


def load_input(filename: str) -> str:
    path = Path(__file__).parent / SOURCE_FILE_DIR / filename
    return path.read_text()


def test_skip_shebang():
    # Results will be a dictionary of:--
    #
    #   starting line-number,
    #   docs (comment) lines [..]
    #   and the matching code lines [..]
    #
    src = load_input("skip_shebang.py")
    assert dict(dycco.parse(src)) == {1: {"docs": [], "code": ["print('Hello, World!')"]}}


def test_skip_coding():
    src = load_input("skip_coding.py")
    assert dict(dycco.parse(src)) == {1: {"docs": [], "code": ["print('Hello, World!')"]}}


def test_skip_emacs_coding():
    src = load_input("skip_emacs_coding.py")
    assert dict(dycco.parse(src)) == {1: {"docs": [], "code": ["print('Hello, World!')"]}}


def test_skip_shebang_and_coding():
    src = load_input("skip_shebang_and_coding.py")
    assert dict(dycco.parse(src)) == {2: {"docs": [], "code": ["print('Hello, World!')"]}}


def test_bad_shebang_and_coding():
    src = load_input("bad_shebang_and_coding.py")
    assert dict(dycco.parse(src)) == {
        3: {"docs": ["Shebang must come first\n!/usr/bin/env/python2.6\n -*- coding: utf8 -*-"],
            "code": ["print('Hello, World!')"]}
    }


def test_module_docstring():
    src = load_input("module_docstring.py")
    assert dict(dycco.parse(src)) == {0: {"docs": ["This is a module-level docstring."], "code": [], }}


def test_non_module_docstring():
    src = load_input("non_module_docstring.py")
    assert dict(dycco.parse(src)) == {
        0: {
            "docs": [],
            "code": [
                "import sys",
                "",
                '"""',
                "Is this is a module-level docstring?",
                "",
                "It has multiple lines.",
                '"""',
                "",
                "sys.exit(1)",
            ],
        }
    }


def test_torturetest():
    src = load_input("awkward_source.py")
    # Note that the spacing is important so that it matches the file input
    result = dycco.parse(src)
    assert result == {
        3: {'docs': [
            '## A Module-Level Docstring\n\nLorem ipsum dolor sit amet, consectetuer adipiscing elit. Aenean commodo\nligula eget dolor. Aenean massa. Cum sociis natoque penatibus et magnis dis\nparturient montes, nascetur ridiculus mus. Donec quam felis, ultricies nec,\npellentesque eu, pretium quis, sem. Nulla consequat massa quis enim. Donec\npede justo, fringilla vel, aliquet nec, vulputate eget, arcu. In enim justo,\nrhoncus ut, imperdiet a, venenatis vitae, justo. Nullam dictum felis eu pede\nmollis pretium. Integer tincidunt. Cras dapibus.\n\nVivamus elementum semper nisi. Aenean vulputate eleifend tellus. Aenean leo\nligula, porttitor eu, consequat vitae, eleifend ac, enim. Aliquam lorem ante,\ndapibus in, viverra quis, feugiat a, tellus. Phasellus viverra nulla ut metus\nvarius laoreet. Quisque rutrum. Aenean imperdiet. Etiam ultricies nisi vel\naugue. Curabitur ullamcorper ultricies nisi.'],
            'code': []},
        22: {'docs': ['Some imports'],
             'code': ['import sys, os, re',
                      'from functools import wraps',
                      'import itertools',
                      '',
                      '']},
        28: {'docs': [
            '## This is an important class',
            'Single-line docstring'],
            'code': ['class Foo(object):', '']},
        37: {'docs': ['### A singly-decorated method'],
             'code': []},
        38: {'docs': ['A multiline docstring with leading and trailing breaks.\n\nWhat do you think of that?'],
             'code': ['    @classmethod', '    def method1(cls):', '        pass', '']},
        73: {'docs': ['## Utility functions'],
             'code': ['']},
        74: {'docs': [None],
             'code': ['def bar(a, b, c):']},
        76: {'docs': ['Return the args we get, for some reason.'],
             'code': ['    return a, b, c', '']},
        46: {'docs': [None],
             'code': ['    @property',
                      '    @wraps(method1)',
                      '    @classmethod',
                      '    def method2(self):']},
        53: {'docs': ['Plus, a function-in-a-function with a docstring. WORLDS ARE\nCOLLIDING JERRY.'],
             'code': ['        def foo():',
                      '            return 42',
                      '',
                      '        return foo', '']},
        85: {'docs': ['A *decorated* long function definition With some very important\ndocumentation.'],
             'code': [
                 '@wraps(bar)',
                 'def decorated_function_definition(function, which, takes, many, args, whose,',
                 '                                  definition, wraps, across, multiple, lines):',
                 "    print('Hello!')"]},
        78: {'docs': ['A long function definition with some very important documentation.'],
             'code': ['def really_long_function_definition(function, which, takes, many, args, whose,',
                      '                                    definition, wraps, across, multiple,',
                      '                                    lines):',
                      '    return 2 ** 128',
                      '']},
        52: {'docs': ['A mutliply-decorated method, with no docstring. How will this look\n to your parents?'],
             'code': ['']},
        64: {'docs': ['A mutliply-decorated method, *with* a docstring. Better? I\ncertainly hope so.'],
             'code': ['    @property',
                      '    @wraps(method1)',
                      '    @classmethod',
                      '    def method2(self):']},
        69: {'docs': ['And also some explanatory comments.'], 'code': ['        return 99', '', '']},
        31: {'docs': ['A multiline docstring with no leading or trailing breaks, asdf asdf\nasdf asdf asfd asdf asd fasdf.'],
             'code': ['    def __init__(self):',
                      '        pass',
                      '']}}
