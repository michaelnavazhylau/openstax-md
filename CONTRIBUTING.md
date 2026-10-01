# Contributing to cnxml2md

Thank you for your interest in contributing to `cnxml2md`! This document provides instructions for setting up your development environment, running tests, and submitting changes.

---

## 🛠️ Development Setup

The project uses [uv](https://docs.astral.sh/uv/) for Python dependency management and packaging.

### Prerequisites

- **Python**: `>= 3.10`
- **uv**: `>= 0.10` (install via `curl -LsSf https://astral.sh/uv/install.sh` or `brew install uv`)
- **Node.js** (optional, required only for KaTeX math validation): `>= 18`
- **Java** (optional, required only if running upstream Jing RNG validation via `--validate`)

### Installation

```bash
# Clone the repository
git clone https://github.com/michaelnavazhylau/openstax-md.git
cd openstax-md

# Install all dependencies and setup the virtual environment
make install
# or manually:
uv sync --all-groups
uv pip install -e .
```

---

## 🧪 Testing and Verification

We maintain a strict quality bar with unit tests, type checking, linting, and independent output validators.

### Running Fast Unit Tests

```bash
# Run the fast test suite (65+ tests, runs in < 0.5s)
make test
# or:
uv run pytest -m "not bundle"
```

### Running All Verification Checks

Before opening a PR, ensure all checks pass:

```bash
make check
```

This runs:
1. `ruff check .` (Linter)
2. `mypy src` (Strict type checking)
3. `ruff format --check .` (Code style)
4. `pytest -m "not bundle"` (Unit tests)

### Code Formatting

We use [Ruff](https://astral.sh/ruff) for code formatting and import sorting:

```bash
make format
```

### Full Bundle Integration & Validation

If you have downloaded the OpenStax Calculus bundle (see [`docs/sources.md`](docs/sources.md)):

```bash
# Run bundle integration tests
make test-all

# Compile the full volume
uv run cnxml2md osbooks-calculus-bundle --collection calculus-volume-1 -o build/calculus-vol1

# Verify output integrity (links, anchors, XML tags, dollar balances)
uv run python scripts/verify_output.py build/calculus-vol1

# Check 100% prose word preservation
uv run python scripts/check_completeness.py osbooks-calculus-bundle build/calculus-vol1

# Validate that KaTeX parses every mathematical formula without errors
npm install
node scripts/validate_latex.js build/calculus-vol1
```

---

## 📁 Repository Structure

```text
cnxml2md/
├── src/cnxml2md/           # Core library
│   ├── __init__.py         # Public exports (convert_cnxml, convert_mathml, etc.)
│   ├── mathml.py           # Presentation MathML -> LaTeX compiler
│   ├── convert.py          # CNXML element renderer to CommonMark/GFM
│   ├── book.py             # Book builder, TOC discovery, numbering engine, layouts
│   ├── cnxml_bridge.py     # Upstream openstax/cnxml library bridge & fallbacks
│   └── cli.py              # CLI driver (argument parser, reporting)
├── tests/                  # Unit and integration test suite
│   ├── conftest.py         # Test fixtures and mini CNXML bundle
│   ├── test_mathml.py      # MathML conversion unit tests
│   ├── test_convert.py     # Block and inline rendering tests
│   ├── test_cli.py         # CLI flags, layouts, and filters tests
│   └── test_bundle.py      # Real bundle integration tests (skipped if absent)
├── scripts/                # Independent verification tools
│   ├── verify_output.py    # Link, anchor, XML leftover validator
│   ├── check_completeness.py # Prose completeness checker
│   ├── validate_latex.js   # KaTeX syntax validation
│   └── compare_with_openstax.py # Diff checker against live openstax.org pages
└── docs/                   # Technical reports and documentation
    ├── gap-report.md       # Comprehensive 28-gap technical analysis
    └── sources.md          # Upstream source tracking and pinned SHAs
```

---

## 📝 Pull Request Guidelines

1. **Keep it focused**: One bug fix or feature per pull request.
2. **Add tests**: Any new feature or bug fix must include corresponding unit tests in `tests/`.
3. **Pass `make check`**: Ensure `make check` passes with 0 warnings or errors.
4. **Follow Conventional Commits**: e.g., `feat:`, `fix:`, `docs:`, `test:`, `refactor:`.
