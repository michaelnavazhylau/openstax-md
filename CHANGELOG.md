# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2026-10-01

### Added
- **Full Python Reimplementation**: High-fidelity compiler transforming OpenStax CNXML/COLLXML textbooks into GitHub Flavored Markdown (GFM).
- **MathML to LaTeX Compiler (`cnxml2md.mathml`)**:
  - Full AST-based transformation of Presentation MathML into KaTeX/LaTeX math.
  - Supports fractions, nested sub/superscripts (`{x^{2}}^{n}`), roots (`\sqrt`, `\sqrt[n]`), dynamic fences (`\left[ \right]`), and piecewise cases (`\begin{cases}`).
  - Maps 30+ Unicode mathematical operators, Greek alphabets, and multiline matrices.
  - Configurable delimiter styling: `dollar` (`$`/`$$`), `bracket` (`\(`/`\[`), or `none`.
- **Collection & Multi-Volume Book Builder (`cnxml2md.book`)**:
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
  - `cnxml2md.convert_cnxml()` for one-line conversion from XML string or file path.
  - `cnxml2md.convert_mathml()` for direct MathML string to LaTeX rendering.
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

### Changed
- Replaced the abandoned 2016 Node.js/Gulp baseline (`Ravenstine/cnxml2md`) with modern, dependency-light Python (`lxml`, `setuptools<81`).

## [0.1.0] - 2026-09-14

### Added
- Initial proof of concept, benchmark harness, and gap analysis against legacy JavaScript tooling.
