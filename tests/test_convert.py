"""CNXML -> Markdown conversion tests (gaps the JS original left open)."""

from __future__ import annotations

from pathlib import Path

from openstax_md.convert import RenderOptions


def test_literal_dollar_is_escaped(module_markdown: str) -> None:
    """A raw '$' in prose or alt text must not open a math span."""
    assert "A unit costs \\$5 (about \\$10,000 for a pallet)." in module_markdown
    assert "groups of \\$10,000." in module_markdown
    assert module_markdown.replace("\\$", "").count("$") % 2 == 0


def test_bundle_dollar_balance(build_mini, tmp_path: Path) -> None:
    build_mini(tmp_path / "out")
    for path in (tmp_path / "out").rglob("*.md"):
        text = path.read_text(encoding="utf-8").replace("\\$", "")
        assert text.count("$") % 2 == 0, path


def test_front_matter_and_title(module_markdown: str) -> None:
    assert module_markdown.startswith("---\n")
    assert 'title: "Functions"' in module_markdown
    assert 'module_id: "m1"' in module_markdown
    assert 'book: "Demo Book"' in module_markdown
    assert 'license: "Creative Commons' in module_markdown
    assert "# Functions\n" in module_markdown


def test_math_is_latex_not_plain_text(module_markdown: str) -> None:
    assert "$f(x)$" in module_markdown
    assert "<m:" not in module_markdown
    assert "m:math" not in module_markdown


def test_inline_elements(module_markdown: str) -> None:
    assert "**function**" in module_markdown  # <term>
    assert "**inputs**" in module_markdown  # <emphasis effect="bold">
    assert "x<sup>2</sup>" in module_markdown
    assert "x<sub>n</sub>" in module_markdown
    assert "<br/>" in module_markdown  # <newline/>


def test_external_link(module_markdown: str) -> None:
    assert "[OpenStax](https://openstax.org)" in module_markdown


def test_section_headings(module_markdown: str) -> None:
    assert "\n## Graphs\n" in module_markdown


def test_inline_math_does_not_split_paragraph(module_markdown: str) -> None:
    assert "Inline math with $x$ mid-sentence stays one paragraph." in module_markdown


def test_lists(module_markdown: str) -> None:
    assert "a. first $1$" in module_markdown
    assert "b. second" in module_markdown
    assert "- bullet one" in module_markdown


def test_equations(module_markdown: str) -> None:
    assert "$$\ny=x^{2}\n$$" in module_markdown
    # a labelled equation keeps its number
    assert "z=1 \\tag{1.1}" in module_markdown


def test_table(module_markdown: str) -> None:
    assert "**Table 1.1 Values**" in module_markdown
    assert "| x | y |" in module_markdown
    assert "| --- | --- |" in module_markdown
    assert "| 1 | $2$ |" in module_markdown
    assert "| a \\| b | 4 |" in module_markdown  # pipes escaped
    assert "*Source: http://www.census.gov/data.*" in module_markdown  # caption kept


def test_learning_objectives_from_abstract(module_markdown: str) -> None:
    assert "**Learning Objectives**" in module_markdown
    assert "- **1.1.1** Recognize a function when you see one." in module_markdown
    assert "- **1.1.2** Evaluate functions." in module_markdown


def test_generated_numbering(module_markdown: str) -> None:
    """OpenStax ships empty <label/> elements; numbers are generated like theirs."""
    assert "*Figure 1.1 A caption.*" in module_markdown
    assert "**Table 1.1 Values**" in module_markdown
    assert "**Example 1.1: Evaluating Functions**" in module_markdown
    assert "**Checkpoint 1.1**" in module_markdown
    assert "\\tag{1.1}" in module_markdown


def test_figure_and_media(module_markdown: str) -> None:
    assert "![A picture of a graph.](" in module_markdown
    assert "pic.png)" in module_markdown
    assert "*Figure 1.1 A caption.*" in module_markdown


def test_example_solution_hint(module_markdown: str) -> None:
    assert "**Example 1.1: Evaluating Functions**" in module_markdown
    assert "**Solution**" in module_markdown
    assert "**Hint**" in module_markdown


def test_note_labels(module_markdown: str) -> None:
    assert "**Theorem 1**" in module_markdown  # explicit title wins
    assert "**Checkpoint 1.1**" in module_markdown  # numbered like the published page


def test_glossary(module_markdown: str) -> None:
    assert "## Glossary" in module_markdown
    assert "- **range** — the set of outputs" in module_markdown


def test_cross_references_resolved(module_markdown: str) -> None:
    # same-module reference -> anchor, labelled with the generated number
    assert "[Figure 1.1](#fig1)" in module_markdown
    # cross-module reference -> relative markdown link
    assert "[Section: Uses](../m2/index.md#sec2)" in module_markdown


def test_unknown_element_is_reported_and_kept(build_mini, tmp_path: Path) -> None:
    _, _, report = build_mini(tmp_path / "out")
    assert "unknown element text" in (tmp_path / "out" / "modules" / "m1" / "index.md").read_text()
    assert report.unhandled["mystery"] == 1


def test_dangling_reference_is_a_warning(build_mini, tmp_path: Path) -> None:
    _, _, report = build_mini(tmp_path / "out")
    assert any("nope" in warning for warning in report.warnings)


def test_anchors_only_for_referenced_ids(module_markdown: str) -> None:
    assert '<a id="fig1"></a>' in module_markdown
    assert '<a id="p2"></a>' not in module_markdown  # not referenced anywhere


def test_anchor_mode_always(build_mini, tmp_path: Path) -> None:
    build_mini(tmp_path / "out", options=RenderOptions(anchors="always"))
    text = (tmp_path / "out" / "modules" / "m1" / "index.md").read_text()
    assert '<a id="p2"></a>' in text


def test_media_copy_mode(mini_bundle: Path, build_mini, tmp_path: Path) -> None:
    out = tmp_path / "out"
    build_mini(out, options=RenderOptions(media="copy"))
    assert (out / "media" / "pic.png").is_file()
    text = (out / "modules" / "m1" / "index.md").read_text()
    assert "../../media/pic.png" in text


def test_media_original_mode(module_markdown: str, build_mini, tmp_path: Path) -> None:
    build_mini(tmp_path / "out2", options=RenderOptions(media="original"))
    text = (tmp_path / "out2" / "modules" / "m1" / "index.md").read_text()
    assert "(../../media/pic.png)" in text


def test_admonition_styles(build_mini, tmp_path: Path) -> None:
    build_mini(tmp_path / "bold", options=RenderOptions(admonitions="bold"))
    build_mini(tmp_path / "block", options=RenderOptions(admonitions="block"))
    build_mini(tmp_path / "heading", options=RenderOptions(admonitions="heading"))
    bold = (tmp_path / "bold" / "modules" / "m1" / "index.md").read_text()
    block = (tmp_path / "block" / "modules" / "m1" / "index.md").read_text()
    heading = (tmp_path / "heading" / "modules" / "m1" / "index.md").read_text()
    assert "**Solution**" in bold
    assert "> **Solution**" in block
    assert "#### Solution" in heading


def test_bracket_math_delimiters(build_mini, tmp_path: Path) -> None:
    build_mini(tmp_path / "out", options=RenderOptions(math="bracket"))
    text = (tmp_path / "out" / "modules" / "m1" / "index.md").read_text()
    assert "\\[y=x^{2}\\]" in text
    assert "\\(x\\)" in text


def test_math_none(build_mini, tmp_path: Path) -> None:
    build_mini(tmp_path / "out", options=RenderOptions(math="none"))
    text = (tmp_path / "out" / "modules" / "m1" / "index.md").read_text()
    assert "y=x^{2}" in text
    assert "$$" not in text


def test_no_front_matter(build_mini, tmp_path: Path) -> None:
    build_mini(tmp_path / "out", options=RenderOptions(front_matter=False))
    text = (tmp_path / "out" / "modules" / "m1" / "index.md").read_text()
    assert not text.startswith("---")


def test_collection_index_and_toc(build_mini, tmp_path: Path) -> None:
    build_mini(tmp_path / "out")
    index = (tmp_path / "out" / "collections" / "demo-book.md").read_text()
    assert "# Demo Book" in index
    assert "**Chapter 1**" in index  # subcollection becomes a TOC heading
    assert "- [Functions](../modules/m1/index.md)" in index
    assert "- [Uses of Functions](../modules/m2/index.md)" in index


def test_flat_layout(build_mini, tmp_path: Path) -> None:
    build_mini(tmp_path / "out", layout="flat")
    files = sorted(p.name for p in (tmp_path / "out" / "demo-book").glob("*.md"))
    assert files == ["01-functions.md", "02-uses-of-functions.md", "index.md"]
    index = (tmp_path / "out" / "demo-book" / "index.md").read_text()
    assert "- Functions" in index  # same-directory TOC entries carry no link
    assert "(01-functions.md)" not in index


def test_single_file_layout(build_mini, tmp_path: Path) -> None:
    build_mini(tmp_path / "out", layout="single")
    book = (tmp_path / "out" / "demo-book.md").read_text()
    assert book.count("---\n") == 2  # one front matter block
    assert "\n# Demo Book\n" in book
    assert "\n## Functions\n" in book  # module title demoted
    assert "\n### Graphs\n" in book  # section demoted too


def test_module_title_used_for_toc_and_paths(mini_bundle: Path) -> None:
    from openstax_md.book import Bundle

    bundle = Bundle.discover(mini_bundle)
    assert bundle.modules["m1"].title == "Functions"
    assert [e.module_id for e in bundle.collections[0].entries] == ["m1", "m2"]


def test_numbering_plan(mini_bundle: Path) -> None:
    from openstax_md.book import Bundle

    bundle = Bundle.discover(mini_bundle)
    numbering = bundle.numbering
    assert numbering.section_number("m1", "demo-book") == "1.1"
    assert numbering.section_number("m2", "demo-book") == "1.2"
    assert numbering.label("fig1", "demo-book", "m1") == "Figure 1.1"
    assert numbering.label("tbl1", "demo-book", "m1") == "Table 1.1"
    assert numbering.label("ex1", "demo-book", "m1") == "Example 1.1"
    assert numbering.label("note2", "demo-book", "m1") == "Checkpoint 1.1"
    assert numbering.label("eq2", "demo-book", "m1") == "(1.1)"
    assert numbering.label("eq1", "demo-book", "m1") == ""  # class="unnumbered"
    assert numbering.objective_labels("m1", "demo-book") == ["1.1.1", "1.1.2"]


def test_build_report_counts(build_mini, tmp_path: Path) -> None:
    _, _, report = build_mini(tmp_path / "out")
    assert report.modules == 2
    assert report.stats["equations"] == 2
    assert report.stats["links_resolved"] >= 3
    assert report.stats["media_linked"] >= 2
    assert report.missing_media == []


def test_convert_cnxml_and_mathml_helpers(mini_bundle: Path) -> None:
    from openstax_md import convert_cnxml, convert_mathml

    assert (
        convert_mathml("<m:math><m:msup><m:mi>x</m:mi><m:mn>2</m:mn></m:msup></m:math>")
        == "$x^{2}$"
    )
    assert (
        convert_mathml("<math><mfrac><mn>1</mn><mn>2</mn></mfrac></math>", display=True)
        == "$$\n\\frac{1}{2}\n$$"
    )

    sample_xml = (
        '<document xmlns="http://cnx.rice.edu/cnxml">'
        "<content><para>Direct string conversion.</para></content></document>"
    )
    md = convert_cnxml(sample_xml)
    assert "Direct string conversion." in md

    path = mini_bundle / "modules" / "m1" / "index.cnxml"
    md_file = convert_cnxml(path)
    assert "Functions" in md_file


def test_openstax_md_exports() -> None:
    import openstax_md

    assert openstax_md.__version__ == "0.2.0"
    assert openstax_md.convert_mathml("<m:math><mi>y</mi></m:math>") == "$y$"
    assert openstax_md.Bundle is not None
    assert openstax_md.Builder is not None
    assert openstax_md.convert_cnxml is not None
