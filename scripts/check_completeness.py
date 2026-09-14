#!/usr/bin/env python
"""Independent completeness check: how much SOURCE prose reaches the output?

Walks every module's CNXML, collects the text of prose elements (paragraphs,
list items, table cells, captions, glossary meanings) *excluding* everything
inside MathML, and checks that every word still appears in the compiled
Markdown. This is deliberately not implemented with the converter's own code
path, so it catches content the converter drops.

Usage::

    uv run python scripts/check_completeness.py osbooks-calculus-bundle build/calculus
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from lxml import etree

PROSE = {"para", "item", "entry", "meaning", "caption", "title", "abstract"}
WORD = re.compile(r"[A-Za-z][A-Za-z'’\-]{2,}")


def localname(el) -> str:
    return etree.QName(el).localname


def source_text(path: Path) -> str:
    """All document text except MathML subtrees."""
    root = etree.parse(str(path)).getroot()
    chunks: list[str] = []

    def walk(el) -> None:
        if localname(el) == "math":
            return
        if el.text:
            chunks.append(el.text)
        for child in el:
            walk(child)
            if child.tail:
                chunks.append(child.tail)

    walk(root)
    return " ".join(chunks)


def main(bundle: str, out: str) -> int:
    bundle_path = Path(bundle)
    out_path = Path(out)
    module_dir = out_path / "modules"
    if not module_dir.is_dir():
        modules = sorted(out_path.rglob("*.md"))
    else:
        modules = sorted(module_dir.glob("*/index.md"))
    if not modules:
        print(f"no markdown found under {out_path}", file=sys.stderr)
        return 2

    total = missing_total = 0
    reports = []
    for md in modules:
        module_id = md.parent.name
        source = bundle_path / "modules" / module_id / "index.cnxml"
        if not source.is_file():
            continue
        text = source_text(source)
        words = [w.lower() for w in WORD.findall(text)]
        haystack = md.read_text(encoding="utf-8").lower()
        missing = sorted({w for w in words if w not in haystack})
        total += len(words)
        missing_total += len(missing)
        if words:
            reports.append((len(missing) / len(words), module_id, missing[:8]))

    reports.sort(reverse=True)
    pct = 100 * missing_total / total if total else 0.0
    print(f"modules: {len(reports)}")
    print(f"source prose words: {total}")
    print(f"words absent from output: {missing_total} ({pct:.2f}%)")
    for ratio, module_id, example in reports[:8]:
        if ratio > 0:
            print(f"  {module_id}: {ratio:.2%} missing, e.g. {example}")
    return 1 if pct > 1.0 else 0


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(sys.argv[1], sys.argv[2]))
