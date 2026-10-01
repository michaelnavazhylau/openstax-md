<div align="center">

<picture>
  <img src="assets/logo.svg" alt="openstax-md logo" width="100%" style="max-width: 880px;" />
</picture>

<br/><br/>

[![CI](https://github.com/michaelnavazhylau/openstax-md/actions/workflows/ci.yml/badge.svg)](https://github.com/michaelnavazhylau/openstax-md/actions)
![Python 3.10 | 3.11 | 3.12 | 3.13 | 3.14](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.13%20%7C%203.14-blue)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Checked with mypy](https://img.shields.io/badge/mypy-checked-blue)](https://mypy-lang.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
![Coverage](https://img.shields.io/badge/coverage-85%25-brightgreen)
![KaTeX](https://img.shields.io/badge/KaTeX-47k%20formulas%20validated-success)

<p align="center">
  <strong>A high-fidelity compiler transforming OpenStax CNXML/COLLXML textbooks into GitHub Flavored Markdown with LaTeX math, publisher-accurate numbering, and cross-reference resolution.</strong>
</p>

</div>

---

## 📖 Overview

[OpenStax](https://openstax.org/) publishes world-class open-source textbooks encoded in **CNXML** (Connexions XML) and **COLLXML** (Collection XML) with embedded **MathML**. While CNXML provides rich pedagogical markup, converting it to Markdown has historically meant losing complex equations, dropping worked examples, breaking links, and losing textbook structure.

`cnxml2md` is a ground-up Python compiler that solves this. It compiles full OpenStax textbook bundles (such as the 3-volume Calculus curriculum, containing 133 modules, ~47,500 MathML expressions, and 1,600+ figures) into pristine Markdown with **zero content loss**, valid LaTeX math, publisher-accurate numbering, and multiple layout targets (developer mirror, PKM/Obsidian vaults, or single-file LLM context windows).

---

## ⚡ The Breakthrough: Closing 28 Legacy Gaps

The original 2016 converter (`Ravenstine/cnxml2md`) was abandoned, fails to run on modern Node.js (`primordials is not defined`), stripped MathML into unreadable text, dropped worked examples, and omitted book structures.

Here is the measured comparison compiling **OpenStax Calculus Volume 1** (55 modules):

| Metric | Legacy JS Converter (2016) | `cnxml2md` (Python) | Improvement |
|---|:---:|:---:|:---:|
| **Output Characters** | 860,270 | **1,736,675** | +101.8% content recovered |
| **Output Words** | 136,023 | **240,944** | +77.1% content recovered |
| **Math Expressions** | 56 (accidental `$`) | **19,844** | Complete MathML→LaTeX recovery |
| **LaTeX Commands** | 0 | **20,053** | Full formula typesetting |
| **Tables Preserved** | 0 | **148** | 100% GFM table reconstruction |
| **Figures Preserved** | 215 | **684** | Includes subfigures & admonitions |
| **Cross-References** | 208 (broken) | **1,305** | Relative file links + `<a id>` anchors |
| **Anchors Emitted** | 0 | **443** | Precise deep linking |
| **Missing Prose Words** | 2.71% dropped | **0.00%** | **100% prose preservation** |
| **KaTeX Parse Errors** | N/A (no math) | **0 errors (47k+ spans)** | Verified against KaTeX engine |

> For the comprehensive breakdown of all 28 identified gaps, root-cause analyses, and resolution details, see [`docs/gap-report.md`](docs/gap-report.md).

---

## 🏗️ Architecture

```mermaid
flowchart TD
    subgraph Inputs ["Input Bundle / Module"]
        B["books.xml (Container)"]
        C["*.collection.xml (Structure)"]
        M["index.cnxml (Content + MathML)"]
        A["media/* (Images & Diagrams)"]
    end

    subgraph Core ["cnxml2md Pipeline"]
        Discovery["Discovery & Indexing Engine\n(book.py)"]
        Numbering["Chapter-Scoped Numbering Plan\n(Examples, Figures, Tables, Objectives)"]
        MathML["MathML -> LaTeX AST Compiler\n(mathml.py)"]
        Convert["Block & Inline Renderer\n(convert.py)"]
        LinkResolver["Cross-Module Link & Anchor Resolver\n(book.py)"]
    end

    subgraph Outputs ["Layout Options"]
        Mirror["Mirror Layout\nmodules/<id>/index.md"]
        Flat["Flat Layout (Obsidian / PKM)\n<book>/<NN>-<title>.md"]
        Single["Single File (LLMs / Pandoc)\n<book>.md"]
    end

    B --> Discovery
    C --> Discovery
    M --> Discovery
    Discovery --> Numbering
    Numbering --> Convert
    M --> MathML
    MathML --> Convert
    A --> Convert
    Convert --> LinkResolver
    LinkResolver --> Mirror
    LinkResolver --> Flat
    LinkResolver --> Single
```

---

## ✨ Key Features

- **AST-Based MathML to LaTeX Compiler**:
  - Translates Presentation MathML elements into idiomatic LaTeX.
  - Handles fractions (`\frac`), nested sub/superscripts (`{x^2}^n`), radicals (`\sqrt[n]`), delimiters (`\left[ \right]`), piecewise functions (`\begin{cases}`), and matrices.
  - Maps 30+ Unicode mathematical operators, Greek letters, and multiline expressions.
  - Supports configurable delimiters: `dollar` (`$...$` / `$$...$$`), `bracket` (`\(...\)` / `\[...\]`), or `none`.
- **Publisher-Accurate Chapter Numbering**:
  - Automatically reconstructs OpenStax's chapter-scoped numbering scheme (`Example 1.1`, `Figure 1.2`, `Table 1.1`, `(1.1)`, objectives `1.1.1`).
  - Isolated module scopes prevent element ID collisions across multi-book bundles.
- **3 Flexible Output Layouts**:
  - `mirror`: Preserves the upstream module layout (`out/modules/<id>/index.md`).
  - `flat`: Flattens into numbered chapters (`out/<book>/<NN>-<title>.md`) tailored for Obsidian, Logseq, and PKM vaults.
  - `single`: Merges an entire textbook into a single Markdown file, ideal for feeding into LLM context windows or compiling to PDF with Pandoc.
- **Full Cross-Reference & Anchor Resolution**:
  - Inter-module links (`<link document="m1" target-id="fig1"/>`) are resolved to relative file paths with target `<a id="...">` anchors.
  - `--with-deps` flag transitively pulls in referenced modules during partial builds to ensure zero broken links.
- **Asset & Media Bundling**:
  - Relative image paths are rewritten per output file.
  - Modes: `link` (relative in-tree link), `copy` (copies all assets into `<out>/media/`), or `original` (keeps XML `src` attribute).
- **100% Prose Preservation Guarantee**:
  - Verified by an independent test harness checking every prose word from the source XML against the compiled output (0 words dropped across 297k+ words).
- **Dual Interface**:
  - Ergonomic CLI with JSON build reports and Jing RNG validation.
  - High-level Python library API for programmatic conversion.

---

## 🚀 Installation

`cnxml2md` is managed with [uv](https://docs.astral.sh/uv/) and requires Python `>= 3.10`.

```bash
# Clone the repository
git clone https://github.com/michaelnavazhylau/openstax-md.git
cd openstax-md

# Install dependencies and CLI tool
uv sync
uv pip install -e .
```

---

## 💻 CLI Usage

The CLI accepts a bundle root directory, a `*.collection.xml` file, a module directory, or a single `index.cnxml` file.

```bash
# 1. Compile an entire bundle (all volumes), mirroring the source layout
cnxml2md osbooks-calculus-bundle -o build/calculus

# 2. Compile one book into an Obsidian/Logseq-friendly flat vault with copied images
cnxml2md osbooks-calculus-bundle --collection calculus-volume-1 \
    --layout flat --media copy -o vault/calculus

# 3. Compile an entire book as a single Markdown file (for LLMs or Pandoc PDF export)
cnxml2md osbooks-calculus-bundle --collection calculus-volume-1 \
    --layout single -o build/books

# 4. Compile a single module with RNG schema validation and a JSON report
cnxml2md osbooks-calculus-bundle/modules/m53477 \
    --validate --report build/report.json -o build/one
```

### CLI Flag Reference

| Flag | Values | Default | Description |
|---|---|:---:|---|
| `-o`, `--out` | `<path>` | `build/<name>` | Output destination directory |
| `--layout` | `mirror`, `flat`, `single` | `mirror` | Directory layout: mirror source tree, flat chapter files, or single-file |
| `--media` | `link`, `copy`, `original` | `link` | Relative link into source tree, copy into `out/media/`, or keep verbatim |
| `--anchors` | `referenced`, `always`, `none` | `referenced` | Emit `<a id="...">` anchors for link targets, all IDs, or none |
| `--math` | `dollar`, `bracket`, `none` | `dollar` | Delimiter style: `$`/`$$`, `\(`/`\[`, or plain LaTeX |
| `--admonitions` | `bold`, `block`, `heading` | `bold` | Formatting style for examples, notes, and solutions |
| `--collection` | `<slug>` | – | Filter build to specific collection slug (repeatable) |
| `--module` | `<id>` | – | Filter build to specific module ID (repeatable) |
| `--with-deps` | flag | `false` | Transitively pull in referenced modules so cross-links stay intact |
| `--validate` | flag | `false` | Run `jing.jar` RNG validation (requires Java) |
| `--strict` | flag | `false` | Exit with non-zero status on warnings, missing media, or schema errors |
| `--report` | `<path>` | – | Write comprehensive JSON build metrics and statistics |
| `-v`, `--version` | flag | – | Show program's version number and exit |

---

## 🐍 Python Library API

In addition to the command line, `cnxml2md` provides a clean Python API:

```python
import cnxml2md

# 1. Convert MathML string to LaTeX
latex = cnxml2md.convert_mathml("<m:math><m:msup><m:mi>x</m:mi><m:mn>2</m:mn></m:msup></m:math>")
print(latex)
# => "$x^{2}$"

# 2. Convert MathML with display delimiters
display_latex = cnxml2md.convert_mathml(
    "<m:math><m:mfrac><m:mn>1</m:mn><m:mn>2</m:mn></m:mfrac></m:math>", display=True
)
print(display_latex)
# => "$$\n\\frac{1}{2}\n$$"

# 3. Convert CNXML string or file directly to Markdown
xml = """
<document xmlns="http://cnx.rice.edu/cnxml" xmlns:m="http://www.w3.org/1998/Math/MathML">
  <title>Derivatives</title>
  <content>
    <para>The derivative of <m:math><m:msup><m:mi>x</m:mi><m:mn>2</m:mn></m:msup></m:math> is <m:math><m:mrow><m:mn>2</m:mn><m:mi>x</m:mi></m:mrow></m:math>.</para>
  </content>
</document>
"""
markdown = cnxml2md.convert_cnxml(xml)
print(markdown)

# 4. Programmatic bundle compilation
bundle = cnxml2md.Bundle.discover("path/to/bundle")
builder = cnxml2md.Builder(
    bundle,
    out_dir="build/calculus",
    options=cnxml2md.RenderOptions(math="dollar", media="copy"),
    layout="flat",
)
report = builder.build()
print(f"Compiled {report.modules} modules, {report.stats['math']} equations.")
```

---

## 🔬 Independent Verification & Quality Benchmarks

Unit tests only test what developers anticipate. To guarantee production-grade fidelity, `cnxml2md` includes **four independent validation checkers** that share no code with the converter:

| Checker | Validation Goal | Measured Result |
|---|---|:---:|
| [`scripts/check_completeness.py`](scripts/check_completeness.py) | Verifies every source prose word appears in the output | **0 of 297,986 words missing (0.00%)** |
| [`scripts/validate_latex.js`](scripts/validate_latex.js) | Parses every emitted formula with KaTeX (the engine used by openstax.org) | **47,478 formulas parsed: 0 errors** |
| [`scripts/verify_output.py`](scripts/verify_output.py) | Confirms no leftover XML tags, balanced `$` delimiters, and that all 3,351 links/media resolve | **0 broken links, 0 leftover tags** |
| [`scripts/compare_with_openstax.py`](scripts/compare_with_openstax.py) | Compares generated headings, objectives, and numbering against live openstax.org pages | **34 sections across all 3 volumes: 0 mismatches** (coverage ≥ 99.2%) |

### Full-Bundle Benchmark (Calculus Volumes 1, 2, and 3)

```text
$ cnxml2md osbooks-calculus-bundle -o build/calculus --report build/report.json --validate
cnxml2md: 133 modules, 137 files, 47,523 math expressions, 1,631 links resolved, 1,617 images -> build/calculus
report.json: words=612,562, unhandled_elements={}, missing_media=[], warnings=[], validation_errors=[]

$ python scripts/verify_output.py build/calculus
files: 137 | links/images checked: 3,351 | anchors emitted: 1,113 | problems: 0

$ python scripts/check_completeness.py osbooks-calculus-bundle build/calculus
modules: 133 | source prose words: 297,986 | words absent from output: 0 (0.00%)

$ node scripts/validate_latex.js build/calculus
files: 137 | math spans parsed by KaTeX: 47,478 | parse errors: 0
```

---

## 🛠️ Development & Testing

A complete [`Makefile`](Makefile) is provided for common development tasks:

```bash
make test       # Run fast unit test suite (70+ tests, < 0.5s)
make test-all   # Run all tests, including full bundle integration
make lint       # Run ruff check
make format     # Format code with ruff
make typecheck  # Run mypy strict type checks
make check      # Run lint, typecheck, format check, and tests
make build      # Build wheel and sdist distributions
```

---

## 📄 License

This project is licensed under the **MIT License**. See the [`LICENSE`](LICENSE) file for details.

The OpenStax textbooks used for test verification are licensed under [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/) by Rice University.
