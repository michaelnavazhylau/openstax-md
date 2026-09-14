#!/usr/bin/env python
"""Compare compiled Markdown against the *published* OpenStax pages.

This is the authoritative cross-check: openstax.org renders the very same CNXML
through OpenStax's own pipeline (Poet/cnx-easybake), so its labels
(``Figure 1.2``, ``Table 1.1``, ``Example 1.7``, objectives ``1.1.1``) and prose
are ground truth for the compiled output.

Page URLs are derived from the collection structure:
``https://openstax.org/books/<book-slug>/pages/<chapter>-<section>-<title-slug>``.

Usage::

    uv run python scripts/compare_with_openstax.py osbooks-calculus-bundle build/calculus \
        --book calculus-volume-1 --per-chapter 1

Fetched pages are cached under .cache/openstax/ (use --refresh to refetch).
"""

from __future__ import annotations

import argparse
import gzip
import re
import sys
import time
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

from lxml import etree

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cnxml2md.book import Bundle  # noqa: E402

BASE = "https://openstax.org/books/{book}/pages/{page}"
LABEL_RE = re.compile(r"\b(Figure|Table|Example|Checkpoint)\s+(\d+\.\d+)\b")
OBJECTIVE_RE = re.compile(r"\b(\d+\.\d+\.\d+)\s+([A-Z][^\n]{10,160})")
WORD_RE = re.compile(r"[A-Za-z][A-Za-z'’\-]{3,}")
#: site chrome only -- note that in-content titles live in <header> elements on
#: OpenStax pages, so that tag must *not* be skipped
SKIP_TAGS = {"script", "style", "noscript", "svg", "nav", "aside", "footer"}
MAIN_RE = re.compile(r"<main\b[^>]*>(.*?)</main>", re.S | re.I)


class _Text(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.chunks: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in SKIP_TAGS:
            self._skip += 1

    def handle_endtag(self, tag):
        if tag in SKIP_TAGS and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if not self._skip and data.strip():
            self.chunks.append(data.strip())

    @property
    def text(self) -> str:
        return "\n".join(self.chunks)


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def fetch(url: str, cache: Path, refresh: bool = False) -> str:
    if cache.is_file() and not refresh:
        return cache.read_text(encoding="utf-8")
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "cnxml2md-validator/0.2 (+https://github.com/openstax/cnxml)",
            "Accept-Encoding": "gzip",
            "Accept": "text/html",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        raw = response.read()
        if response.headers.get("Content-Encoding") == "gzip":
            raw = gzip.decompress(raw)
    html = raw.decode("utf-8", errors="replace")
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(html, encoding="utf-8")
    time.sleep(1.0)  # be polite
    return html


def page_text(html: str) -> str:
    # restrict to the page body: everything outside <main> is site chrome
    match = MAIN_RE.search(html)
    if match:
        html = match.group(1)
    parser = _Text()
    parser.feed(html)
    return parser.text


def section_pages(bundle: Bundle, book: str, per_chapter: int, sections: int | None):
    """Map ``(module_id, url)`` for the sections of one book."""
    collection = next((c for c in bundle.collections if c.slug == book), None)
    if collection is None:
        raise SystemExit(f"unknown book {book!r}; available: {[c.slug for c in bundle.collections]}")
    per_chapter_count: dict[str, int] = {}
    out = []
    for entry in collection.entries:
        # a module can belong to several books (shared appendix/preview modules);
        # the compiled file carries the numbering of its *preferred* book only
        owner = bundle.collection_of(entry.module_id)
        if owner is not None and owner.slug != book:
            continue
        key = entry.sections[0] if entry.sections else ""
        chapter = bundle.numbering.section_number(entry.module_id, book).split(".")[0] or ""
        if not chapter or chapter == "0":
            continue
        per_chapter_count[key] = per_chapter_count.get(key, 0) + 1
        if per_chapter_count[key] > per_chapter:
            continue
        module = bundle.modules.get(entry.module_id)
        if module is None:
            continue
        chapter_section = bundle.numbering.section_number(entry.module_id, book)
        page = f"{chapter_section.replace('.', '-')}-{slugify(module.title)}"
        out.append((entry.module_id, BASE.format(book=book, page=page)))
    return out[:sections] if sections else out


def compiled_text(build: Path, module_id: str) -> str | None:
    direct = build / "modules" / module_id / "index.md"
    if direct.is_file():
        return direct.read_text(encoding="utf-8")
    matches = list(build.rglob(f"*{module_id}*.md"))
    return matches[0].read_text(encoding="utf-8") if matches else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path)
    parser.add_argument("build", type=Path)
    parser.add_argument("--book", default=None, help="collection slug (default: every book)")
    parser.add_argument("--per-chapter", type=int, default=1, help="sections to check per chapter")
    parser.add_argument("--sections", type=int, default=None, help="stop after N sections in total")
    parser.add_argument("--cache", type=Path, default=Path(".cache/openstax"))
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--min-coverage", type=float, default=0.90, help="required published-word coverage")
    args = parser.parse_args(argv)

    bundle = Bundle.discover(args.bundle)
    books = [args.book] if args.book else [c.slug for c in bundle.collections]

    total_sections = failures = 0
    for book in books:
        targets = section_pages(bundle, book, args.per_chapter, args.sections)
        if not targets:
            continue
        print(f"\n== {book}: checking {len(targets)} section(s) against openstax.org")
        for module_id, url in targets:
            markdown = compiled_text(args.build, module_id)
            cache = args.cache / book / (url.rsplit("/", 1)[-1] + ".html")
            try:
                text = page_text(fetch(url, cache, args.refresh))
            except Exception as exc:  # network problems must not look like failures
                print(f"  {module_id:8s} SKIP  fetch failed: {exc}")
                continue
            total_sections += 1
            problems: list[str] = []

            published_labels = {f"{kind} {number}" for kind, number in LABEL_RE.findall(text)}
            missing_labels = sorted(label for label in published_labels if label not in markdown)
            if missing_labels:
                problems.append(f"{len(missing_labels)} published labels missing: {missing_labels[:5]}")
            compiled_labels = {f"{kind} {number}" for kind, number in LABEL_RE.findall(markdown)}
            extra_labels = sorted(label for label in compiled_labels if label not in published_labels)
            if extra_labels:
                problems.append(f"{len(extra_labels)} labels not on the published page: {extra_labels[:5]}")

            published_objectives = set(OBJECTIVE_RE.findall(text))
            missing_objectives = []
            for number, sentence in sorted(published_objectives):
                if sentence[:40] not in markdown or number not in markdown:
                    missing_objectives.append(f"{number} {sentence[:50]}")
            if missing_objectives:
                problems.append(f"{len(missing_objectives)} objectives missing: {missing_objectives[:2]}")

            words = {w.lower() for w in WORD_RE.findall(text)}
            missing_words = {w for w in words if w not in markdown.lower()}
            coverage = 1 - len(missing_words) / max(len(words), 1)
            if coverage < args.min_coverage:
                worst = sorted(missing_words)[:8]
                problems.append(f"coverage {coverage:.1%} < {args.min_coverage:.0%} (missing e.g. {worst})")

            status = "ok" if not problems else "FAIL"
            print(
                f"  {module_id:8s} {status}  coverage={coverage:5.1%}  "
                f"labels={len(published_labels)}/{len(compiled_labels)}  objectives={len(published_objectives)}"
            )
            for problem in problems:
                failures += 1
                print(f"            {problem}")

    print(f"\nchecked {total_sections} published section(s); {failures} mismatch group(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
