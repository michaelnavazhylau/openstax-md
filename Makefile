.PHONY: all install test test-all battle-test battle-test-all coverage lint format check typecheck build clean help

all: check

install:
	uv sync --all-groups
	uv pip install -e .

test:
	uv run pytest -m "not bundle"

test-all:
	uv run pytest

battle-test:
	uv run python scripts/bulk_test.py --sample

battle-test-all:
	uv run python scripts/bulk_test.py --all --workers 6

coverage:
	uv run pytest --cov=src/openstax_md --cov-report=term-missing

lint:
	uv run ruff check .

format:
	uv run ruff format .

typecheck:
	uv run mypy src

check: lint typecheck test
	uv run ruff format --check .

build:
	uv build

clean:
	rm -rf build/ dist/ *.egg-info/ .coverage coverage.xml htmlcov/ .pytest_cache/ .mypy_cache/ .ruff_cache/
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

help:
	@echo "Available commands:"
	@echo "  make install    Install all dev dependencies and editable package"
	@echo "  make test       Run fast unit tests (excluding real textbook bundle)"
	@echo "  make test-all   Run all tests (including bundle integration tests if present)"
	@echo "  make coverage   Run pytest with branch coverage report"
	@echo "  make lint       Run ruff linter"
	@echo "  make format     Format all code using ruff"
	@echo "  make typecheck  Run mypy type checker"
	@echo "  make check      Run lint, typecheck, format check, and tests"
	@echo "  make build      Build sdist and wheel distributions"
	@echo "  make clean      Clean build caches, distributions, and temp files"
