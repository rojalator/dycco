#!/usr/bin/env python

"""**Dycco** is another Python port of [Docco][docco], the quick-and-dirty,
hundred-line-long, literate-programming-style documentation generator. This
particular version has been updated to work with Python 3 (as of 2022).

This version allows output to a markdown file or to an asciidoc3 file, as well
as adding a option to sanitize internal HTML (which is handy if your code
includes html fragments).

Dycco reads Python source files and produces annotated source documentation in
HTML format. Comments and docstrings are formatted with [Markdown][markdown] or
with [AsciiDoc3][asciidoc3]
and presented as annotations alongside the source code, which is
syntax-highlighted by [Pygments][pygments]. This page is the result of running
Dycco against its [own source file][dycco].

Dycco differs from Nick Fitzgerald's [Pycco][pycco] ([new version][newpycco]), the first Python port of
[Docco][docco], in that it only knows how to generate documenation on Python
source code and it uses that specialization to more accurately parse
documentation. It does so using a two-pass parsing stage, first walking the
*Abstract Syntax Tree* of the code to gather up docstrings, then examining the
code line-by-line to extract comments.

Dycco's HTML and CSS are taken straight from [Docco][docco], but, like
Pycco, Dycco uses [Mustache][mustache] templates rendered by
[Pystache][pystache]. The first version of Dycco's templates and CSS were
taken straight from [Pycco][pycco], then updated to match the latest changes
to [Docco][docco]'s.

[docco]: https://ashkenas.com/docco/
[markdown]: http://daringfireball.net/projects/markdown/
[pygments]: http://pygments.org/
[dycco]: https://github.com/mccutchen/dycco
[pycco]: https://github.com/pycco-docs/pycco
[mustache]: https://github.com/peterldowns/python-mustache
[pystache]: https://github.com/defunkt/pystache
[asciidoc3]: https://asciidoc3.org/
[newpycco]: https://github.com/rojalator/pycco
"""

import ast
import datetime
import os
import re
import shutil
import io
from collections import defaultdict
import html

import markdown
import pystache
from pygments import highlight
from pygments.lexers import get_lexer_by_name
from pygments.formatters import HtmlFormatter

# We have to muck about a bit because of asciidoc3's strange behaviour
# See: [AttributeError: module 'asciidoc3' has no attribute 'messages'](https://gitlab.com/asciidoc3/asciidoc3/-/issues/5)
# for the explanation

import importlib.util

ascii_location = None
ascii_module = importlib.util.find_spec('asciidoc3')
if ascii_module:
    # We found a version of asciidoc3, so record where it is for later use by `preprocess_docs()`
    ascii_location = ascii_module.submodule_search_locations[0] + '/asciidoc3.py'
    import asciidoc3.asciidoc3api as AsciiDoc3API


COMMENT_PATTERN = r'^\s*#'

DYCCO_ROOT = os.path.dirname(__file__)
DYCCO_RESOURCES = os.path.join(DYCCO_ROOT, 'resources')
DYCCO_TEMPLATE = os.path.join(DYCCO_RESOURCES, 'template.html')
DYCCO_CSS = os.path.join(DYCCO_RESOURCES, 'dycco.css')


### Documentation Generation

def document(input_paths, output_dir, use_ascii:bool = False, escape_html:bool = False,
             single_file:bool = False):
    """Generates documentation for the Python files at the given `input_paths`
    by parsing each file into pairs of documentation and source code and
    rendering those pairs into an HTML file.

    The `input_paths` param can be a `list` of paths or a single `str` path.

    Usually, markdown() is called, but if `use_ascii` is true, we'll use asciidoc3
    (`__main__.py` looks for the `-a / --asciidoc3` flag for this). By default, it's set
    to False to retain the old behaviour of just using markdown.

    If escape_html is True, we use Python's `html.escape()` to prevent any embedded
    html in the comments from disrupting the output. Again, it's False by default
    to maintain the old behaviour.

    `single_file` means that we just want to produce a file with either `.md` or
    `.adoc` extension, in single-column format, with code blocks demarcated using
    markdown or asciidoc3 indicators. This is handy if, for example, you haven't
    got the Python asciidoc3 but have got asciidoctor available: you can pass it
    the file for processing.
    """

    # If we get a single path, stick it in a list so we can still pretend
    # we're operating on multiple paths.
    if isinstance(input_paths, str):
        input_paths = [input_paths]

    # Make sure the directory exists
    if not os.path.exists(output_dir) or not os.path.isdir(output_dir):
        os.makedirs(output_dir)

    # Parse each input file into sections, render the sections as HTML into a
    # string, and create or overwrite the documentation at the appropriate
    # output path. We have a default extension of `html`...
    extension = 'html'
    if single_file:
        # ...but if we are wanting a single file, use Markdown's or
        # Asciidoc3's extensions
        extension = 'adoc' if use_ascii else 'md'
    for input_path in input_paths:
        filename = os.path.basename(input_path)
        output_path = make_output_path(filename, output_dir, extension)
        with open(input_path) as f_input:
            src = f_input.read()
            sections = parse(src)
            output_body = render(filename, sections, use_ascii, escape_html, single_file)
            with open(output_path, 'w') as f_output:
                f_output.write(output_body)

    # Copy the CSS file into the output directory
    shutil.copy(DYCCO_CSS, output_dir)


### Parsing the Source

def parse(src:str) -> defaultdict:
    """Parse the given source code in two passes. The first pass walks the
    *Abstract Syntax Tree* of the code, gathering up and noting the location
    of any docstrings. The second pass processes the code line by line,
    grouping the code into sections based on docstrings and comments.

    The data structure returned is a special `dict` whose keys are the line
    numbers where sections start, which map to `dict`s containing the docs and
    code associated with those sections. The docs and code are stored as
    lists, which will be joined in post processing by `render()`.

    It will look a little like this:


        { 1: {docs: [..., ...],
               code: [..., ...] },
          9: {docs: [..., ...],
               code: [..., ...] } }



    The docs for each section can come from docstrings (the first pass) or
    from comments (the second pass). The line numbers start at zero, for
    simplicity's sake.
    """

    # Create the basic `sections` datastructure we'll use to keep track of
    # code and documentation.
    sections = make_sections()

    # First, parse all of the docstrings and get a list (set) of lines we should
    # skip when parsing the rest of the code. Modifies `sections` in place.
    skip_lines = parse_docstrings(src, sections)

    # Second, parse the rest of the code, adding code and comments to the
    # appropriate sections. Modifies `sections` in place.
    parse_code(src, sections, skip_lines)

    return sections


#### First Pass

def parse_docstrings(src:str, sections:defaultdict) -> set:
    """Parse the given `src` to find any docstrings, add them to the
    appropriate place in `sections`, and return a `set` of line numbers where
    the docstrings are. **Note:** Modifies `sections` in place.
    """
    # Find any docstrings in the source code by walking its AST.
    visitor = DocStringVisitor()
    visitor.visit(ast.parse(src))

    # Add all of the docstrings we've found to the appropriate places in the
    # `sections` datastructure. The corresponding code will be added later.
    for target_line, doc in visitor.docstrings.items():
        sections[target_line]['docs'].append(doc)

    return visitor.docstring_lines


#### Second Pass

def parse_code(src:str, sections:defaultdict, skip_lines:set):
    """Parse the given `src` line by line to gather source code and comments
    into the appropriate places in `sections`. Any line numbers in
    `skip_lines` are skipped. **Note:** Modifies `sections` in place.
    """
    # Iterate through each line of source code to gather up comments and code
    # listings and add them to the sections structure.
    current_comment = None
    current_section = None
    for i, line in enumerate(src.splitlines()):
        # Skip any lines that were in docstrings
        if i in skip_lines or should_filter(line, i):
            continue

        # Are we looking at a comment? If so, and we do not have a current
        # comment block, we're starting a new section. If we do have a current
        # comment block, we just add this comment to it (e.g. multi-line
        # comments).
        if re.match(COMMENT_PATTERN, line):
            comment = re.sub(COMMENT_PATTERN, '', line)
            if current_comment is None:
                current_comment = comment
            else:
                current_comment += '\n' + comment

        # Otherwise, we're looking at a line of code and we need to add it to
        # the appropriate section, along with any preceding comments.
        else:
            # If we have a current comment, that means we're starting a new
            # section with this line of code.
            if current_comment:
                current_comment = current_comment.strip()
                docs = sections[i]['docs']
                # If we've already got docs for this section, that (hopefully)
                # means we're looking at a function/class def that has a
                # docstring, but that the current comments precede the def. In
                # this case, we prepend the comments, so they come before the
                # docstring.
                if docs:
                    docs.insert(0, current_comment)
                else:
                    docs.append(current_comment)
                # The next comment we encounter will start a new section, but
                # any lines of code that follow this one belong to this
                # section.
                current_comment = None
                current_section = i

            # We don't have a current section, so we should be at our first
            # bit of code (aside from any module-level docstrings), and should
            # start a new section. But we want to skip any empty leading blank
            # lines.
            elif current_section is None and line:
                current_section = i

            # If the current line is already in the `sections` datastructure,
            # it is (probably) associated with a docstring from the first
            # pass, and we should  it to that section instead of whatever
            # current section we have.
            if i in sections:
                current_section = i

            # Finally, append the current line of code to the current
            # section's code block. Skips any empty leading lines of code,
            # which will not have a current section.
            if current_section is not None:
                sections[current_section]['code'].append(line)

    #### Decorators
    # Now we need to jiggle any decorators about - they should not be at the end of
    # sections, but at the start of the *next* code section (however, sometimes they
    # get placed at the end).

    # Get ourselves an ordered list of the possible section numbers so that we can
    # easily find the 'next' greater section-number
    section_numbers = sorted(sections.keys())
    # We'll now have an ordered list of just the section *numbers* like `[3, 14, 17, 22, 85]`
    # We don't check the last one (`85` in this example) as we cannot bump content
    # *from* it only *into* it
    for this_section_number in section_numbers[:-1]:
        # Get what would be the next section number: find where *we* are and add one to it
        # so, if we were `14` in `[3, 14, 17, 22, 85]` we'd be at `1`, but want the position of
        # the next section which is at `2`
        next_index = section_numbers.index(this_section_number) + 1
        # And then we want the value that's there (`17` in this example)
        next_section_number = section_numbers[next_index]
        # We move back 'up' the code content, moving any trailing decorators to the next section.
        content = sections[this_section_number]['code']
        for line in reversed(content):
            # Bail out if there are none, or we've used them all up...
            if not line.strip().startswith('@'):
                break
            # ...Otherwise, remove the last entry from our section's code...
            s = sections[this_section_number]['code'].pop()
            # ...and add it to the **start** of the *next* section's code - doing it this
            # way also preserves the order of the decorators.
            sections[next_section_number]['code'].insert(0, s)

### Rendering

def render(title:str, sections:defaultdict, use_ascii:bool = False,
           escape_html:bool = False, single_file:bool = False) -> str:
    """Renders the given sections, which should be the result of calling
    `parse` on a source code file, into HTML.

    If `single_file` is True, we don't actually run things through Pygments,
    Markdown or Asciidoc3, but just output a single file with a suitable extension
    """
    # Transform the `sections` `dict` we were given into a format suitable for
    # our Mustache template. Along the way, preprocess each block of
    # documentation via Markdown or Asciidoc3 and code via Pygments.
    sections = [{
        'num': key,
        'docs_html': preprocess_docs(value['docs'], use_ascii, escape_html, single_file),
        'code_html': preprocess_code(value['code'], use_ascii, single_file)
    } for key, value in sorted(sections.items())]

    # We include a timestamp in the footer.
    date = datetime.datetime.utcnow().strftime('%d %b %Y')

    if single_file:
        # For a `single_file` we just weld all the gubbins together, the code
        # sections will have been marked as such via `preprocess_code()`
        out_lines = []
        for section in sections:
            out_lines.extend([section['docs_html'], '\n', section['code_html']])
        out_text = '\n'.join(out_lines)
        return out_text
    else:
        # ...otherwise, we carry on as before, rendering via pystache and the template
        context = {
            'title': title,
            'sections': sections,
            'date': date,
            }
        with open(DYCCO_TEMPLATE) as f:
            return pystache.render(f.read(), context)


### Preprocessors

def preprocess_docs(docs:list, use_ascii:bool, escape_html:bool, raw:bool = False) -> str:
    """Preprocess the given `docs`, which should be a `list` of strings, by
    joining them together and running them through Markdown or
    asciidoc3, unless `raw` is True, in which case we just return the text
    """
    assert isinstance(docs, list)
    # Join the documentation sections together.
    # Sometimes we have `None` in entries - filter them out
    # while we do so.
    collated_docs = '\n\n'.join(filter(None, docs))
    # Sanitize it if required
    sanitized_docs = html.escape(collated_docs) if escape_html else collated_docs
    if raw:
        # Don't do any actual processing, just return the strings.
        return sanitized_docs
    if use_ascii:
        #### Documentation - Asciidoc3
        # If we couldn't find asciidoc3, bail out with an error
        if ascii_location is None:
            raise ImportError('asciidoc3 was not found')

        # Asciidoc3 likes file-like entities, so give it them
        dummy_infile = io.StringIO(sanitized_docs)
        dummy_outfile = io.StringIO()
        # We have to force-feed asciidoc3 with its location (`ascii_location`)
        # or it will choke and claim things are missing - this is
        # especially true in virtual environments using `pip`.
        # See [issue 5](https://gitlab.com/asciidoc3/asciidoc3/-/issues/5).
        asciidoc = AsciiDoc3API.AsciiDoc3API(ascii_location)
        asciidoc.options('--no-header-footer')
        # Call asciidoc - the output will be in `dummy_outfile`...
        asciidoc.execute(dummy_infile, dummy_outfile, backend='html5')
        # ...so return its content
        return dummy_outfile.getvalue()
    else:
        #### Documentation - Markdown

        # Otherwise, just pass the joined-up (possibly sanitized)
        # document sections to markdown()
        return markdown.markdown(sanitized_docs)

#### Code - Pygments


def preprocess_code(code:list, use_ascii:bool = False, raw:bool = False, language_name:str = 'python') -> str:
    """Preprocess the given code, which should be a `list` of strings, by
    joining them together and running them through the Pygments syntax
    highlighter unless `raw` is True, when we just return the text

    Although we are strictly python, it's possible that this might get called by other
    routines as it's quite handy, so allow the language to be specified
    in `language_name`. Behaviour if `language_name` is blank is undefined (for asciidoc3).
    """
    assert isinstance(code, list)
    # Sometimes code is empty, so just return nothing
    if not code or not ''.join(code).strip():
        return ''
    if raw:
        # We don't highlight for `raw` output, we'll just mark the code with the
        # appropriate 'this is code' text for markdown or asciidoc3
        delimiter = '---------------------------------------------------------------------'
        if use_ascii:
            # ...either asciidoc3's markers...
            code_block = '\n[source,{2}]\n{0}\n{1}\n{0}\n'.format(delimiter, '\n'.join(code), language_name)
        else:
            # ...or Markdown's markers
            delimiter = "```"
            code_block = '{0}{2}\n{1}\n{0}\n'.format(delimiter, '\n'.join(code), language_name)
        return code_block
    else:
        # Do what we always used to - pass througn Pygments
        lexer = get_lexer_by_name("python")
        formatter = HtmlFormatter()
        result = highlight('\n'.join(code), lexer, formatter)
        return result


### Support Functions

def make_sections() -> defaultdict:
    """Creates the special `sections` datastructure used to hold parsed
    documentation and code.
    """
    # A callable for use as the default object in the `defaultdict` we use to
    # represent the sections.
    def section() -> dict:
        return {'docs': [], 'code': [],}
    return defaultdict(section)


def should_filter(line:str, num:int) -> bool:
    """Test the given line to see if it should be included. Excludes shebang
    lines, for now.
    """
    # Filter shebang comments.
    if num == 0 and line.startswith('#!'):
        return True
    # Filter encoding specification comments.
    if num < 2 and line.startswith('#') and re.search('coding[:=]', line):
        return True
    return False


def make_output_path(filename, output_dir, extension:str = 'html') -> str:
    """Creates an appropriate output path for the given source file and output
    directory. The output file name will be the name of the source file
    without its original extension but with `html`, `md` or `adoc` as
    a new one.
    """
    name, ext = os.path.splitext(filename)
    return os.path.join(output_dir, '%s.%s' % (name, extension))


#### AST Parsing

class DocStringVisitor(ast.NodeVisitor):
    """A `NodeVisitor` subclass that walks an Abstract Syntax Tree (AST) and gathers
    up and notes the positions of any docstrings it finds.
    """

    def __init__(self):
        # Docstrings will be tracked as a dict mapping 0-based target line
        # numbers to cleaned up docstrings.
        self.docstrings = {}

        # Track the line numbers where docstrings are found, so they can be
        # skipped when processing the source code line-by-line.
        self.docstring_lines = set()

        # Keep track of the current module, class, or function node we're
        # looking at, if any.
        self.current_node = None
        self.current_doc = None

    def _visit_docstring_node(self, node):
        """A method to be called when visiting any node that might have an
        associated docstring (ie, module, function and class nodes). This uses
        `ast.get_docstring` to grab and sanitize the docstring, and notes
        which node we're currently looking at.
        """
        self.current_node = node
        self.current_doc = ast.get_docstring(node) or ''
        # Mark the place of any function or class definitions without
        # docstrings, to ensure that a new section will be started for every
        # def when rendering.
        if isinstance(node, (ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef)) and not self.current_doc:
            self.docstrings[node.lineno - 1 - len(node.decorator_list)] = None
        super(DocStringVisitor, self).generic_visit(node)

    # Use the `_visit_docstring_node` method when visiting all of these nodes.
    visit_Module = _visit_docstring_node
    visit_FunctionDef = _visit_docstring_node
    visit_ClassDef = _visit_docstring_node
    visit_AsyncFunctionDef = _visit_docstring_node

    def visit_Expr(self, node):
        """We need to actually visit the nodes representing the docstrings to
        record their positions. Docstring nodes show up as `Expr` nodes whose
        values are `Str` nodes.

        `ast.Str` was removed in Python 3.8 (well, deprecated and marked for
        removal), so we need to play around a bit...

        The Python docs state:

        A constant value. The value attribute of the Constant literal contains the Python
        object it represents. The values represented can be simple types such as a number,
        string or None, but also immutable container types (tuples and frozensets) if all
        of their elements are constant.

        ...or in English, the `node.value` **type** will be `ast.Constant` *but* you can get its
        actual type via `node.value.value` for constant types (`ast.Call` types don't have a
         `value.value` member).
        """
        if isinstance(node.value, ast.Constant):
            if isinstance(node.value.value, str) and self.current_node and self.current_doc:
                # Figure out where the docstring *ends*, accounting for 0-based line numbers.
                # _Note that modules *have* got an end-line despite what the older code says._
                end_line = node.end_lineno - 1

                # We need to know how many lines are in the docstring to figure
                # out where it actually starts. We might have triple-strings of
                # various combinations:-
                #
                # >      """..."""
                #
                # or
                #
                # >      """...
                # >      """
                #
                #  or
                #
                # >      """
                # >      ..."""
                #
                #  or... well, you get the idea!

                # `splitlines()` will handily split on the `\n`, so we can deal with all the above
                # variants quite easily
                line_count = len(node.value.s.splitlines())
                if isinstance(self.current_node, ast.Module):
                    start_line = end_line - (line_count if line_count > 1 else 0)
                    target_line = start_line

                # The current node's `lineno` attribute will be where the
                # function/class definition starts, taking decorators into
                # account, so there may be a gap between the `target_line` and the
                # `start_line` if the defintion includes decorators or spans
                # multiple lines.
                else:
                    start_line = end_line - (line_count - 1)
                    target_line = self.current_node.lineno - 1

                # Mark the positions of this node and its documentation.
                assert target_line not in self.docstrings
                self.docstrings[target_line] = self.current_doc.strip()
                self.docstring_lines.update(range(start_line, end_line + 1))

            # Reset the accounting variables even if we didn't find a docstring,
            # so that we don't accidentally add "unattached" docstrings to
            # whatever class/def/module happened to come before them.
            if self.current_node:
                self.current_node = None
                self.current_doc = None

        super(DocStringVisitor, self).generic_visit(node)
