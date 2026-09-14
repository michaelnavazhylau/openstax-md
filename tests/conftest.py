"""Shared fixtures: a tiny but representative CNXML bundle."""

from __future__ import annotations

from pathlib import Path

import pytest

from cnxml2md.book import Builder, Bundle
from cnxml2md.convert import RenderOptions

M1 = """<document xmlns="http://cnx.rice.edu/cnxml" xmlns:m="http://www.w3.org/1998/Math/MathML">
<title>Functions</title>
<metadata xmlns:md="http://cnx.rice.edu/mdml">
  <md:content-id>m1</md:content-id>
  <md:title>Functions</md:title>
  <md:uuid>11111111-1111-1111-1111-111111111111</md:uuid>
  <md:language>en</md:language>
  <md:abstract><list id="list-obj"><item>Recognize a function when you see one.</item><item>Evaluate functions.</item></list></md:abstract>
  <md:license url="http://creativecommons.org/licenses/by-nc-sa/4.0/">Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International</md:license>
</metadata>
<content>
<para id="p1">A <term id="t1">function</term> maps <emphasis effect="bold">inputs</emphasis> to outputs, e.g. <m:math><mrow><mi>f</mi><mo stretchy="false">(</mo><mi>x</mi><mo stretchy="false">)</mo></mrow></m:math> and x<sup>2</sup> and x<sub>n</sub>, with a break<newline/>after it. See <link url="https://openstax.org">OpenStax</link>.</para>
<section id="s1">
<title>Graphs</title>
<para id="p2">Inline math with <m:math><mi>x</mi></m:math> mid-sentence stays one paragraph.</para>
<list id="l1" list-type="enumerated" number-style="lower-alpha">
<item>first <m:math><mn>1</mn></m:math></item>
<item>second</item>
</list>
<list id="l2"><item>bullet one</item></list>
<equation id="eq1" class="unnumbered"><label/><m:math><mrow><mi>y</mi><mo>=</mo><msup><mi>x</mi><mn>2</mn></msup></mrow></m:math></equation>
<equation id="eq2"><label>(1.1)</label><m:math><mrow><mi>z</mi><mo>=</mo><mn>1</mn></mrow></m:math></equation>
<table id="tbl1" summary="x and y">
<title>Values</title>
<caption>Source: http://www.census.gov/data.</caption>
<tgroup cols="2">
<colspec colnum="1" colname="c1"/><colspec colnum="2" colname="c2"/>
<thead><row><entry>x</entry><entry>y</entry></row></thead>
<tbody>
<row><entry>1</entry><entry><m:math><mn>2</mn></m:math></entry></row>
<row><entry>a | b</entry><entry>4</entry></row>
</tbody>
</tgroup>
</table>
<figure id="fig1">
<media id="media1" alt="A picture of a graph."><image mime-type="image/png" src="../../media/pic.png"/></media>
<caption>A caption.</caption>
</figure>
<para id="p11">A unit costs $5 (about $10,000 for a pallet).</para>
<figure id="fig3">
<media id="media3" alt="Bills wrapped in groups of $10,000."><image mime-type="image/png" src="../../media/pic.png"/></media>
<caption>Money.</caption>
</figure>
<example id="ex1">
<exercise id="exr1">
<problem id="prb1">
<title>Evaluating Functions</title>
<para id="p3">Evaluate <m:math><mi>f</mi></m:math>.</para>
</problem>
<solution id="sol1"><para id="p4">It is <m:math><mn>7</mn></m:math>.</para></solution>
<commentary id="com1" type="hint"><title>Hint</title><para id="p5">Substitute.</para></commentary>
</exercise>
</example>
<note id="note1" class="theorem"><title>Theorem 1</title><para id="p6">Statement.</para></note>
<note id="note2" class="checkpoint">
<exercise id="exr2"><problem id="prb2"><para id="p7">Try it.</para></problem><solution id="sol2"><para id="p8">Done.</para></solution></exercise>
</note>
<glossary>
<definition id="def1"><term>range</term><meaning id="mean1">the set of outputs</meaning></definition>
</glossary>
<para id="p9">See <link document="m1" target-id="fig1"/>, <link document="m2" target-id="sec2"/> and a dangling <link document="m2" target-id="nope"/>.</para>
<mystery id="p10"><para>unknown element text</para></mystery>
</section>
</content>
</document>
"""

M2 = """<document xmlns="http://cnx.rice.edu/cnxml" xmlns:m="http://www.w3.org/1998/Math/MathML">
<title>Uses</title>
<metadata xmlns:md="http://cnx.rice.edu/mdml">
  <md:content-id>m2</md:content-id>
  <md:title>Uses of Functions</md:title>
  <md:uuid>22222222-2222-2222-2222-222222222222</md:uuid>
  <md:language>en</md:language>
</metadata>
<content>
<section id="sec2">
<title>Uses</title>
<para id="p20">Body text.</para>
<figure id="fig2"><media id="media2" alt="Second figure."><image mime-type="image/png" src="../../media/pic.png"/></media><caption>Second caption.</caption></figure>
</section>
</content>
</document>
"""

COLLECTION = """<col:collection xmlns="http://cnx.rice.edu/collxml" xmlns:md="http://cnx.rice.edu/mdml" xmlns:col="http://cnx.rice.edu/collxml" xml:lang="en">
<metadata xmlns:md="http://cnx.rice.edu/mdml" mdml-version="0.5">
  <md:title>Demo Book</md:title>
  <md:language>en</md:language>
  <md:slug>demo-book</md:slug>
  <md:license url="http://creativecommons.org/licenses/by-nc-sa/4.0/">Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International</md:license>
</metadata>
<col:content>
  <col:subcollection>
    <md:title>Chapter 1</md:title>
    <col:content>
      <col:module document="m1"/>
      <col:module document="m2"/>
    </col:content>
  </col:subcollection>
</col:content>
</col:collection>
"""

CONTAINER = """<container xmlns="https://openstax.org/namespaces/book-container" version="1">
  <book slug="demo-book" collection-id="col1" style="calculus" href="../collections/demo.collection.xml"/>
</container>
"""


@pytest.fixture
def mini_bundle(tmp_path: Path) -> Path:
    root = tmp_path / "bundle"
    (root / "META-INF").mkdir(parents=True)
    (root / "collections").mkdir()
    (root / "media").mkdir()
    (root / "modules" / "m1").mkdir(parents=True)
    (root / "modules" / "m2").mkdir(parents=True)
    (root / "META-INF" / "books.xml").write_text(CONTAINER, encoding="utf-8")
    (root / "collections" / "demo.collection.xml").write_text(COLLECTION, encoding="utf-8")
    (root / "modules" / "m1" / "index.cnxml").write_text(M1, encoding="utf-8")
    (root / "modules" / "m2" / "index.cnxml").write_text(M2, encoding="utf-8")
    (root / "media" / "pic.png").write_bytes(b"\x89PNG\r\n\x1a\n fake")
    return root


@pytest.fixture
def build_mini(mini_bundle: Path):
    """Return ``run(out_dir, **builder_kwargs) -> Report``."""

    def run(out_dir: Path, **kwargs):
        options = kwargs.pop("options", None) or RenderOptions()
        bundle = Bundle.discover(mini_bundle)
        builder = Builder(bundle, out_dir, options=options, **kwargs)
        report = builder.build()
        return bundle, builder, report

    return run


@pytest.fixture
def module_markdown(build_mini, tmp_path: Path) -> str:
    build_mini(tmp_path / "out")
    return (tmp_path / "out" / "modules" / "m1" / "index.md").read_text(encoding="utf-8")
