# AGENTS.md — Developer & Agent Directives for openstax-md

Welcome to **openstax-md**. This document serves as the operational handbook, architectural guide, and engineering standard for AI agents and human contributors working within this codebase.

---

## 1. Project Identity & Purpose

**openstax-md** is a ground-up Python compiler transforming [OpenStax](https://openstax.org/) textbooks (encoded in CNXML/COLLXML with embedded MathML) into pristine, GitHub Flavored Markdown (GFM) with:
- **Zero prose loss** (100% prose preservation verified by independent checkers).
- **AST-based MathML to LaTeX translation** with zero KaTeX parse errors.
- **Publisher-accurate chapter-scoped numbering** (`Example 1.1`, `Figure 1.2`, `Table 1.1`, objectives `1.1.1`).
- **Deep link & anchor resolution** across multi-module collections.
- **Docker-style remote pulling** via blobless sparse checkouts across the entire 89-volume OpenStax catalog.

---

## 2. Invariants & Engineering Directives (Non-Negotiable)

When authoring or modifying code in this repository, you **MUST** adhere to the following invariants:

### Rule 1: Zero Prose Loss
- All text content inside CNXML elements (`<para>`, `<section>`, `<item>`, `<note>`, `<example>`, `<term>`, `<quote>`) must be faithfully emitted in Markdown.
- No prose may be discarded silently. Run `python scripts/check_completeness.py` against sample books to verify 0 dropped words.

### Rule 2: KaTeX Mathematical Fidelity
- All MathML must parse into valid LaTeX formulas accepted by the KaTeX engine without syntax errors.
- Delimiters must be balanced: `$...$` (inline) and `$$...$$` (display).
- Formula parsing is verified across 47k+ spans by `node scripts/validate_latex.js`.

### Rule 3: Chapter-Scoped Numbering Plan
- Numbering is scoped per chapter (`1.1`, `1.2`, etc.) matching OpenStax print/web publications.
- Module ID namespaces must remain isolated to prevent collisions across multi-book bundles.

### Rule 4: Docker CLI Remote Pulling Convention
- When a user provides a textbook target (e.g. `astronomy-2e`, `calculus-volume-1`, `python`) that does not exist locally on disk, `openstax-md` must transparently resolve and pull the repository via blobless sparse checkout into cache.
- Local paths always take precedence over remote catalog lookups.

### Rule 5: Strict Code Quality & Matrix Testing
- All code must pass `make check` (`ruff check`, `ruff format --check`, `mypy src`, and `pytest`).
- GitHub Actions CI must stay green across Python 3.10 through 3.14.

---

## 3. Architecture & Code Layout

```
integrating-cnxml/ (openstax-md)
├── .github/workflows/ci.yml # Multi-version CI + KaTeX + Battle Test workflow
├── pyproject.toml           # Package configuration & entry points
├── Makefile                 # Standard developer targets
├── src/
│   └── openstax_md/
│       ├── __init__.py      # Public library API
│       ├── __main__.py      # Package execution entry point
│       ├── book.py          # Bundle discovery, collection parsing, Builder, Numbering
│       ├── catalog.json     # Bundled offline catalog of 89 OpenStax volumes
│       ├── catalog.py       # Remote pulling engine, search, list, cache management
│       ├── cli.py           # Command-line interface frontend (compile, pull, search, list)
│       ├── cnxml_bridge.py  # Bridge to Rice University cnxml RNG validation library
│       ├── convert.py       # CNXML block & inline AST Markdown renderer
│       ├── mathml.py        # MathML -> LaTeX AST converter
│       └── py.typed         # PEP 561 typing marker
├── tests/                   # Pytest test suite (100+ tests, < 2.5s)
└── scripts/
    ├── bulk_test.py         # Full catalog battle-test harness (87 volumes)
    ├── check_completeness.py# Prose preservation verification
    ├── validate_latex.js    # Node.js KaTeX formula validation
    └── verify_output.py     # Link and anchor integrity verifier
```

---

## 4. Key Workflows & Commands

```bash
# Run fast test suite
make test

# Run all tests (including full bundle integration)
make test-all

# Run linting, type checks, and formatting verification
make check

# Format code
make format

# Run catalog battle test
make battle-test

# Build wheel and source distributions
make build
```
