"""A line that opens with an issue reference is a paragraph, not a heading.

Python-Markdown accepts "#304 fixed it" as an ATX heading; CommonMark requires a
space or tab after the # run. Both polarities, because only the pair shows the
rule: the headings test alone passed before the fix.
"""
import pytest

from macf.viz.markdown import _convert_md_to_html


@pytest.mark.parametrize("line", ["#304 introduced it, and #322 fixed it.", "#1 item", "#!/bin/bash"])
def test_a_hash_run_without_a_space_is_a_paragraph(line):
    html = _convert_md_to_html(line)
    assert html == f"<p>{line}</p>", html


def test_headings_with_a_space_still_render():
    html = _convert_md_to_html("# Title\n\ntext\n\n## Sub ##\n\npara\n### Third")
    assert '<h1 id="title">Title</h1>' in html
    assert '<h2 id="sub">Sub</h2>' in html
    assert '<h3 id="third">Third</h3>' in html
