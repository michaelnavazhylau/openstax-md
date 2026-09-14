# Gap report: JS `cnxml2md` -> Python `cnxml2md`

Scope: compile `osbooks-calculus-bundle` (Calculus Vols 1-3, CC BY-NC-SA 4.0) to
Markdown with the [`cnxml`](https://github.com/openstax/cnxml) library as the
schema/metadata authority.

Environment: `uv 0.10.8`, Python 3.14, lxml 6.1.3, Node 26.6.0 (for the JS
baseline), Java (for `jing.jar` validation).

## Reproducing

```bash
# baseline (JS 2016 converter, gulp 3 bypassed because it crashes on Node >= 12)
cd cnxml2md && npm install && node -e "..."            # see "Baseline" below
# current implementation
uv sync
uv run cnxml2md osbooks-calculus-bundle -o build/calculus --report build/report.json --validate
uv run python scripts/verify_output.py build/calculus
uv run python scripts/check_completeness.py osbooks-calculus-bundle build/calculus
npm install && node scripts/validate_latex.js build/calculus
uv run python scripts/compare_with_openstax.py osbooks-calculus-bundle build/calculus --per-chapter 2
uv run pytest                 # 64 unit tests
uv run pytest -m bundle       # 7 integration tests against the real bundle
```

Baseline was produced with a 20-line harness that `eval`s the converter half of
`cnxml2md.js` (stubbing `gulp`, `gulp-rename`, `pretty-data2`) and applies the same
`render()` + newline normalisation the original `filter()` stream does. This is
the *best case* for the JS version: running `node cnxml2md.js` fails outright.

## Baseline facts

| Fact | Value |
|---|---|
| `node cnxml2md.js` on Node 26 | `ReferenceError: primordials is not defined` (gulp 3 -> graceful-fs@1.2.3) |
| Bundle size | 133 modules, 1,937 media files (192 MB), 3 collections |
| MathML `<m:math>` | 47,480 occurrences in 116/133 modules |
| `<equation>` | 4,043 |
| `<exercise>` / `<problem>` | 7,742 each |
| `<table>` | 244 |
| `<media>` / `<image>` | 1,548 / 1,617 |
| `<label>` | 3,754 (all empty in this bundle) |
| `<link>` variants | 1,480 `target-id` only, 97 `document`, 48 `url`, 43 `document`+`target-id` |

## Gaps found, and how they are closed

| # | Gap in `cnxml2md.js` | Evidence before | After | Where |
|---|---|---|---|---|
| 1 | Does not run on modern Node (gulp 3) | `primordials is not defined` | pure Python + `uv`, no Node | `pyproject.toml` |
| 2 | MathML flattened into text | `x1,x2∈I,f(x1)≤f(x2)` | `$x_{1},x_{2}\in I,f(x_{1})\le f(x_{2})$` | `src/cnxml2md/mathml.py` |
| 3 | No display math | 0 `$$` blocks | 4,043 display equations, aligned `m:mtable` -> `\begin{matrix}`, piecewise -> `\begin{cases}` | `mathml.py`, `convert.py::_is_standalone_math` |
| 4 | `<link document=… target-id=…/>` produced nothing | `(see )` | `[Example](../m53495/index.md#fs-id1169739204154)` + `<a id>` anchors | `convert.py::_link*`, `book.py::build_index` |
| 5 | Worked examples/exercises dropped | no `Example`/`Solution`/`Hint` labels | `**Example: …**`, `**Solution**`, `**Hint**`, `**Checkpoint**` | `convert.py::_example/_exercise/_problem/_solution/_commentary/_note` |
| 6 | `<table>` dropped | 0 tables | 148 GFM tables with titles, anchors, escaped pipes, inline math in cells | `convert.py::_table` |
| 7 | `<equation>` dropped | 0 | `$$\n…\n$$`, `\tag{n}` for labelled equations | `convert.py::_equation` |
| 8 | `<glossary>`/`<definition>` dropped | only inline `term` bold | `## Glossary` + `- **term** — meaning` | `convert.py::_glossary/_definition` |
| 9 | Half the figures lost (only direct children of visited nodes) | 215 images (Vol 1) | 684 images (Vol 1): `<figure>`, `<subfigure>`, bare `<media>`/`<image>`, media inside notes | `convert.py::_figure/_media` |
| 10 | No book structure | flat `**/index.cnxml` glob | `META-INF/books.xml` -> collections -> ordering + TOC + `index.md`; `--layout mirror\|flat\|single` | `book.py` |
| 11 | Media paths relied on source-relative `src` | `../../media/x.jpg` only works in-tree | rewritten per output file; `--media link\|copy\|original` | `book.py::media_href` |
| 12 | Unknown elements silently swallowed | n/a (nothing reported) | counter + JSON report; content still rendered | `convert.py::block/inline_node` |
| 13 | No metadata | none | YAML front matter from `cnxml`'s `parse_metadata` (title, uuid, license, language, source) | `convert.py::front_matter`, `cnxml_bridge.py` |
| 14 | No validation | none | `--validate` runs upstream RNG checks via `jing.jar` | `cnxml_bridge.py`, `book.py::_validate` |
| 15 | Sentence-splitting bug (ours, found by tests) | inline math between prose became separate paragraphs | runs of inline content merge into one paragraph | `convert.py::_content` |
| 16 | Literal `$` in prose/alt text ("costs $5", "groups of $10,000") opened math spans | 15 modules with unbalanced `$` | escaped as `\$`, all math spans balanced | `convert.py::_text/_image` |
| 17 | `<table><caption>` (source attribution, 19 tables) dropped | words from captions absent from output | captions rendered as `*…*` under the table | `convert.py::_table` |
| 18 | `<md:abstract>` (per-section learning objectives, all 133 modules) dropped | "Recognize when to apply L'Hôpital's rule." missing | `**Learning Objectives**` block per module | `convert.py::objectives` |
| 19 | `\quad`/`\qquad` from `<mspace>` glued to the next letter (`\qquadx`) | ~200 spans failed to parse in KaTeX | commands terminated with a space | `mathml.py::_mspace` |
| 20 | Empty `<m:math/>` placeholders emitted bare `$$` | broke display-math pairing in 2 modules | empty math renders as nothing | `mathml.py::render` |
| 21 | `<m:msup><m:mrow/><m:mi>n</m:mi></m:msup>` (invalid but present) emitted `^{n}` on the previous script | 2 spans "Double superscript" | empty base emits `{}^{n}` | `mathml.py::_script_base` |
| 22 | Nested/`mrow` script bases emitted `x^{2}^{n}` | "Double superscript" | bases wrapped as `{x^{2}}^{n}` | `mathml.py::_script_base` |
| 23 | Unicode math symbols passed through verbatim (30+ distinct: `π θ α β 〈 〉 ‖ ∬ ⋯ • ℓ º ¢`, plus zero-width/function-application chars) | "Unrecognized Unicode character" from KaTeX, invisible chars broke scripts | mapped to LaTeX commands; invisible formatting chars stripped | `mathml.py` symbol tables, `_INVISIBLE_RE` |
| 24 | **No generated numbering**: CNXML ships empty `<label/>`s, so nothing was numbered | published pages read `Example 1.1`, `Figure 1.2`, `Table 1.1`, `(1.1)`, objectives `1.1.1`; compiled output had none | chapter-scoped counters reproducing OpenStax's rules (openers are not sections; `class="unnumbered"` tables/equations are skipped; `column-header` tables count) | `book.py::_build_numbering`, `convert.py` |
| 25 | Function names rendered as `\text{sin}\,x`, bold vectors as `\mathbf{\text{i}}` | 9,715 `\text{sin}`-style and ~6,300 `\mathbf{\text{i}}` fragments | `\sin x`, `\mathbf{i}`, `\operatorname{sech}`, `\operatorname{curl}` | `mathml.py::_function_command/_mtext` |
| 26 | Module ids repeat across the bundle (76 collisions) → numbering/target labels leaked between modules | `Example 6.55` in a 13-example section, wrong table tags | numbering is module-scoped with an explicit no-fallback for planned modules | `book.py::Numbering.label` |
| 27 | Partial builds degraded cross references to plain text | 6 dangling links when building Volume 1 alone | `--with-deps` pulls referenced modules in transitively (55 → 64 modules, 0 refs outside the build) | `book.py::_expand_dependencies`, `cli.py` |
| 28 | Tables were labelled/numbered even when OpenStax doesn't | `**Table 5.1**`…`**Table 5.5**` on pages that show no table numbers | `class="unnumbered"` tables neither consume a number nor show one | `book.py::_numbered_kind`, `convert.py::_table` |

## Measured result (Calculus Volume 1, 55 modules)

| Metric | JS 2016 | Python |
|---|---|---|
| characters | 860,270 | 1,736,675 |
| words | 136,023 | 240,944 |
| math spans | 56 (accidental `$`) | 19,844 |
| LaTeX commands | 0 | 20,053 |
| tables | 0 | 148 |
| images | 215 | 684 |
| links | 208 | 1,305 |
| anchors emitted | 0 | 443 |
| empty link text | 3 | 0 |
| raw XML left in output | 0 | 0 |
| unbalanced `$` delimiters | n/a (no math) | 0 |

## Full-bundle verification (all three volumes)

```
cnxml2md: 133 modules, 137 files, 47523 math expressions, 1631 links resolved, 1617 images
report.json: words=612562, unhandled_elements={}, missing_media=[], warnings=[],
             validation_errors=[] (jing, cnxml 0.7 / collxml 2.0)
verify_output.py: 3351 links+images checked, 1113 anchors, 0 problems
check_completeness.py: 0 of 297986 source prose words missing (0.00%)
validate_latex.js: 47478 spans parsed by KaTeX, 0 parse errors,
                   5 spans with a cosmetic 'unknown symbol' warning (¢)
compare_with_openstax.py: 34 published sections (all 3 volumes), 0 mismatches
pytest: 71 tests pass
```

"0 problems" in `scripts/verify_output.py` means: no MathML/CNXML leftovers, no
empty link text, every relative link resolves to a file, and every `#fs-…`/
`#CNX_…` anchor exists in the target document.

## Independent validation and what it caught

Gaps 17-28 above were **not** found by the unit tests — they were found by the
four independent checkers, which do not share the converter's code path:

| Checker | Question it answers | Result before | Result now |
|---|---|---|---|
| `scripts/check_completeness.py` | Does every source word survive into the Markdown? | 2.71% of prose words missing (learning objectives, table captions) | **0.00%** (0 of 297,986) |
| `scripts/validate_latex.js` (KaTeX) | Is the emitted LaTeX actually parseable by a real math renderer? | 229 parse errors at first run, 4 after the first fixes | **0 errors** on 47,478 spans |
| `scripts/verify_output.py` | Do links/anchors/media resolve, is any XML left, are `$` balanced? | 164 broken collection-TOC links, then 15 unbalanced-`$` modules | **0 problems** |
| `scripts/compare_with_openstax.py` | Do labels, objectives and prose match the **published** book? | numbering completely absent; table/example counters wrong; `Example 6.55` from id collisions | **34 sections across all 3 volumes: 0 mismatches**, coverage ≥99.2% |

Unit tests remain the fast regression net (71 tests, 2 s) but they only assert
what I already thought to assert; every item in the table above was missed by
them initially.

### How the published-page comparison works

openstax.org renders the same CNXML through OpenStax's own pipeline, so it is
ground truth. `scripts/compare_with_openstax.py` derives each section's URL from
the collection structure
(`/books/<slug>/pages/<chapter>-<section>-<title>`), fetches it (cached under
`.cache/openstax/`), extracts the page body from `<main>` and then asserts:

* every published label (`Figure 1.2`, `Table 1.1`, `Example 1.7`,
  `Checkpoint 1.3`) also appears in the compiled Markdown — and vice versa;
* every published learning objective (number **and** text) appears;
* ≥90% of published prose words appear (actual: 99.2-100%).

```
$ uv run python scripts/compare_with_openstax.py osbooks-calculus-bundle build/calculus --per-chapter 2
...
checked 34 published section(s); 0 mismatch group(s)
```

## Residual limitations

* Typography is "good LaTeX", not LaTeX-style-perfect: multi-letter identifiers
  become `\mathit{…}`; `°`/`º` become `^{\circ}`; `¢` stays a literal (KaTeX has no
  metrics for it — 5 cosmetic warnings).
* Numbering matches the published pattern for figures/tables/examples/
  checkpoints/equations and learning objectives, but generated numbers are only
  applied where the element has an `id` (all do in this bundle).
* Review-exercise labels are plain per-section counters (`1.`, `2.`, …) matching
  the published pages; cross-references to individual review problems are not
  reconstructed as anchors unless the source has a `target-id`.
* MathML `menclose` -> `\overline`/`\boxed`/`\cancel`, `mfenced` separators
  handled for the simple cases; no `semantics`/`annotation` (content MathML)
  support beyond "first child wins".
* Without `--with-deps`, links leaving a partial build are plain text plus a
  warning rather than dangling links.
* `setuptools<81` is pinned because upstream `cnxml` imports `pkg_resources`
  (removed in setuptools 81); validation also needs `java` on `PATH`.
* No EPUB/HTML/DOCX export (Markdown is the interchange format; use pandoc or
  the OpenStax toolchain downstream).
