"""Unit tests for the MathML -> LaTeX converter."""

from __future__ import annotations

from lxml import etree

from cnxml2md.mathml import MathMLConverter

M = "http://www.w3.org/1998/Math/MathML"


def conv(xml: str, delimiters: str = "dollar") -> str:
    node = etree.fromstring(xml.replace("<math", f'<math xmlns="{M}"', 1))
    return MathMLConverter(delimiters).render(node)


def latex(xml: str) -> str:
    node = etree.fromstring(xml.replace("<math", f'<math xmlns="{M}"', 1))
    return MathMLConverter().to_latex(node)


def test_fraction_and_power() -> None:
    assert conv("<math><mfrac><mn>1</mn><mi>x</mi></mfrac></math>") == "$\\frac{1}{x}$"
    assert conv("<math><msup><mi>x</mi><mn>2</mn></msup></math>") == "$x^{2}$"
    assert conv("<math><msub><mi>x</mi><mn>1</mn></msub></math>") == "$x_{1}$"
    assert conv("<math><msubsup><mi>x</mi><mn>1</mn><mn>2</mn></msubsup></math>") == "$x_{1}^{2}$"


def test_roots() -> None:
    assert conv("<math><msqrt><mi>x</mi></msqrt></math>") == "$\\sqrt{x}$"
    assert conv("<math><mroot><mi>x</mi><mn>3</mn></mroot></math>") == "$\\sqrt[3]{x}$"


def test_limit_underscript() -> None:
    xml = (
        "<math><munder><mrow><mtext>lim</mtext></mrow>"
        "<mrow><mi>x</mi><mo>\u2192</mo><mn>1</mn></mrow></munder></math>"
    )
    assert conv(xml) == "$\\lim_{x\\to 1}$"


def test_big_operator_with_limits() -> None:
    xml = (
        "<math><munderover><mo>\u2211</mo><mrow><mi>i</mi><mo>=</mo><mn>1</mn></mrow>"
        "<mi>n</mi></munderover></math>"
    )
    assert conv(xml) == "$\\sum_{i=1}^{n}$"


def test_operator_spacing_does_not_glue_letters() -> None:
    """`\\circ` followed by `f` must not become the unknown command `\\circf`."""
    xml = "<math><mrow><mo>\u2218</mo><mi>f</mi></mrow></math>"
    assert conv(xml) == "$\\circ f$"

    xml = "<math><mrow><mi>x</mi><mo>\u2208</mo><mi>I</mi></mrow></math>"
    assert conv(xml) == "$x\\in I$"


def test_cases_table() -> None:
    xml = (
        "<math><mrow><mo>{</mo><mrow><mtable>"
        "<mtr><mtd><mrow><mtext>\u2212</mtext><mi>x</mi><mo>,</mo><mi>x</mi><mo>&lt;</mo><mn>0</mn></mrow></mtd></mtr>"
        "<mtr><mtd><mrow><mi>x</mi><mo>,</mo><mi>x</mi><mo>\u2265</mo><mn>0</mn></mrow></mtd></mtr>"
        "</mtable></mrow></mrow></math>"
    )
    out = conv(xml)
    assert "\\begin{cases}" in out
    assert "-x,x<0" in out
    assert "\\end{cases}" in out


def test_fenced_with_separators() -> None:
    xml = '<math><mfenced open="[" close="]" separators=";"><mn>1</mn><mn>2</mn></mfenced></math>'
    assert conv(xml) == "$\\left[ 1 ; 2 \\right]$"


def test_style_variants() -> None:
    xml = (
        '<math><mrow><mstyle mathvariant="bold"><mi>x</mi></mstyle>'
        '<mstyle mathvariant="bold"><mtext>\u2212</mtext></mstyle></mrow></math>'
    )
    assert conv(xml) == "$\\mathbf{x}-$"


def test_symbol_in_mtext_becomes_math() -> None:
    assert conv("<math><mtext>\u221e</mtext></math>") == "$\\infty$"
    assert conv("<math><mtext>has some property</mtext></math>") == "$\\text{has some property}$"


def test_accents_and_spaces() -> None:
    xml = '<math><mover accent="true"><mi>f</mi><mo>\u2032</mo></mover></math>'
    out = conv(xml)
    assert "f" in out
    assert conv('<math><mspace width="0.2em"/></math>') == "$\\,$"
    assert conv('<math><mspace width="2em"/></math>') == "$\\qquad$"


def test_display_and_delimiters() -> None:
    node = etree.fromstring(f'<math xmlns="{M}" display="block"><mi>x</mi></math>')
    assert MathMLConverter().render(node) == "$$\nx\n$$"
    assert MathMLConverter("bracket").render(node) == "\\[x\\]"
    assert MathMLConverter("none").render(node) == "x"


def test_unprefixed_mathml_namespace() -> None:
    """Two modules in the bundle use <math xmlns="...MathML"> without a prefix."""
    node = etree.fromstring(
        f'<math xmlns="{M}"><mfrac><mrow><mi>d</mi><mi>z</mi></mrow>'
        "<mrow><mi>d</mi><mi>t</mi></mrow></mfrac></math>"
    )
    assert MathMLConverter().render(node) == "$\\frac{dz}{dt}$"


def test_unknown_element_degrades_to_text() -> None:
    assert conv("<math><mi>a</mi><munknown><mi>b</mi></munknown></math>") == "$ab$"


def test_empty_math_is_dropped() -> None:
    """The source contains empty <m:math/> placeholders; they must not emit '$$'."""
    assert conv("<math/>") == ""
    assert conv("<math><mrow/></math>") == ""


def test_empty_script_base_is_braced() -> None:
    """<m:msup><m:mrow/><m:mi>n</m:mi></m:msup> must not produce a bare '^{n}'."""
    xml = (
        "<math><mrow><msup><mi>x</mi><mn>2</mn></msup><msup><mrow/><mi>n</mi></msup></mrow></math>"
    )
    assert conv(xml) == "$x^{2}{}^{n}$"


def test_nested_script_base_is_wrapped() -> None:
    xml = "<math><msup><mrow><msup><mi>x</mi><mn>2</mn></msup></mrow><mi>n</mi></msup></math>"
    assert conv(xml) == "${x^{2}}^{n}$"


def test_greek_and_invisible_characters() -> None:
    assert conv("<math><mi>π</mi></math>") == "$\\pi$"
    assert conv("<math><mi>θ</mi></math>") == "$\\theta$"
    assert conv("<math><mo>⟨</mo><mi>x</mi><mo>⟩</mo></math>") == "$\\langle x\\rangle$"
    # zero-width space / function application must be stripped
    assert conv("<math><mi>x</mi><mo>⁡</mo><mi>y</mi></math>") == "$xy$"


def test_mspace_commands_are_terminated() -> None:
    xml = (
        '<math><mrow><mspace width="1em"/><mi>y</mi><mspace width="0.2em"/><mi>n</mi></mrow></math>'
    )
    assert conv(xml) == "$\\quad y\\,n$"


def test_mtable_matrix_and_cases() -> None:
    matrix_xml = (
        "<math><mtable>"
        "<mtr><mtd><mn>1</mn></mtd><mtd><mn>2</mn></mtd></mtr>"
        "<mtr><mtd><mn>3</mn></mtd><mtd><mn>4</mn></mtd></mtr>"
        "</mtable></math>"
    )
    assert "\\begin{matrix}" in conv(matrix_xml)
    assert "1 & 2 \\\\ 3 & 4" in conv(matrix_xml)

    cases_xml = (
        '<math><mfenced open="{"><mtable>'
        "<mtr><mtd><mn>1</mn></mtd></mtr>"
        "<mtr><mtd><mn>2</mn></mtd></mtr>"
        "</mtable></mfenced></math>"
    )
    assert "\\begin{cases}" in conv(cases_xml)


def test_limits_and_underover() -> None:
    lim_xml = (
        "<math><munder><mi>lim</mi><mrow><mi>x</mi><mo>→</mo><mn>0</mn></mrow></munder></math>"
    )
    assert "\\lim_{" in conv(lim_xml)

    sum_xml = "<math><munderover><mo>∑</mo><mrow><mi>i</mi><mo>=</mo><mn>1</mn></mrow><mi>n</mi></munderover></math>"
    assert "\\sum_{" in conv(sum_xml)


def test_menclose_and_delimiters() -> None:
    boxed = '<math><menclose notation="box"><mi>x</mi></menclose></math>'
    assert "\\boxed{x}" in conv(boxed)

    c_bracket = MathMLConverter(delimiters="bracket")
    assert c_bracket.render(etree.fromstring("<math><mi>x</mi></math>")) == "\\(x\\)"
    assert (
        c_bracket.render(etree.fromstring("<math><mi>x</mi></math>"), force_display=True)
        == "\\[x\\]"
    )

    c_none = MathMLConverter(delimiters="none")
    assert c_none.render(etree.fromstring("<math><mi>x</mi></math>")) == "x"
    assert c_none.render(etree.fromstring("<math></math>")) == ""
