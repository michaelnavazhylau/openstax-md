# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **PyPI distribution**: `openstax-md` now publishes to PyPI (and TestPyPI) via GitHub Actions Trusted Publishing (`.github/workflows/publish.yml`), triggered by a `v*` tag. `pip install openstax-md` and `uv tool install openstax-md` are now the supported install paths.
- **`validation` extra**: `pip install "openstax-md[validation]"` pulls the upstream `cnxml` library (and the `setuptools<81` it needs for `pkg_resources`) for CNXML/COLLXML RNG validation and metadata extraction. The bridge now also discovers an installed `cnxml` distribution, not just a sibling checkout.

### Changed
- **Slimmed runtime dependencies**: `setuptools>=68,<81` moved from required dependencies to the `validation` extra. Installing `openstax-md` no longer downgrades `setuptools` in unrelated environments.
- Adopted PEP 639 license metadata (`license = "MIT"`, `license-files`) and added `Changelog` / `Documentation` project URLs.
- sdist no longer ships `uv.lock`, npm manifests, or CI workflow files.

### Removed
- Dropped stale `cnxml2md.*` module paths from this changelog in favour of the canonical `openstax_md.*` names.

## [0.2.0] - 2026-10-01

> First public release on PyPI.

### Added
- **Full Python Reimplementation**: High-fidelity compiler transforming OpenStax CNXML/COLLXML textbooks into GitHub Flavored Markdown (GFM).
- **MathML to LaTeX Compiler (`openstax_md.mathml`)**:
  - Full AST-based transformation of Presentation MathML into KaTeX/LaTeX math.
  - Supports fractions, nested sub/superscripts (`{x^{2}}^{n}`), roots (`\sqrt`, `\sqrt[n]`), dynamic fences (`\left[ \right]`), and piecewise cases (`\begin{cases}`).
  - Maps 30+ Unicode mathematical operators, Greek alphabets, and multiline matrices.
  - Configurable delimiter styling: `dollar` (`$`/`$$`), `bracket` (`\(`/`\[`), or `none`.
- **Collection & Multi-Volume Book Builder (`openstax_md.book`)**:
  - Automatically parses `META-INF/books.xml` and `*.collection.xml` hierarchies.
  - 3 flexible output layouts:
    - `mirror`: Preserves the upstream module folder structure (`modules/<id>/index.md`).
    - `flat`: Obsidian/Logseq/PKM vault-friendly structure (`<book>/<NN>-<title>.md`).
    - `single`: Compiles an entire multi-chapter textbook into a single Markdown document (optimized for LLM context windows and pandoc PDF compilation).
- **Publisher-Accurate Numbering Engine**:
  - Reproduces OpenStax chapter-scoped numbering rules for Figures, Tables, Examples, Exercises, Checkpoints, Equations, and Learning Objectives (`Figure 1.2`, `Table 1.1`, `Example 1.7`, `1.1.1`).
  - Module-scoped counter isolation preventing cross-module ID collisions.
- **Cross-Reference & Anchor Resolution**:
  - Rewrites internal `<link>` elements to point to relative file paths with `<a id="...">` HTML anchor targets.
  - Handles external URLs and inter-module cross-links.
  - Added `--with-deps` flag to pull transitive dependency modules into partial builds.
- **Media Asset Management**:
  - Asset path rewriting supporting `link` (relative in-tree), `copy` (self-contained export to `<out>/media/`), and `original` modes.
- **High-Level Functional Python API**:
  - `openstax_md.convert_cnxml()` for one-line conversion from XML string or file path.
  - `openstax_md.convert_mathml()` for direct MathML string to LaTeX rendering.
- **Independent 4-Tier Verification Suite (`scripts/`)**:
  - `check_completeness.py`: Verifies zero dropped source prose words (100% preservation across 297k+ words).
  - `validate_latex.js`: KaTeX parser checking every emitted LaTeX expression (0 errors across 47k+ formulas).
  - `verify_output.py`: Checks for leftover XML tags, balanced `$` delimiters, and validates every file link and anchor.
  - `compare_with_openstax.py`: Directly verifies compiled sections against published live pages on openstax.org.
- **Modern Packaging & Tooling**:
  - Fast environment management via `uv`.
  - Type checking with `mypy` (clean type annotations across all modules).
  - Linting and formatting with `ruff`.
  - Multi-version CI matrix for Python 3.10 through 3.14 via GitHub Actions.
  - PEP 561 typing marker (`py.typed`) and bundled `catalog.json` shipped in the wheel.

### Changed
- Replaced the abandoned 2016 Node.js/Gulp baseline (`Ravenstine/cnxml2md`) with modern, dependency-light Python (`lxml`).

## [0.1.0] - 2026-09-14

### Added
- Initial proof of concept, benchmark harness, and gap analysis against legacy JavaScript tooling.
