#!/usr/bin/env python
"""Verify a compiled bundle: no raw XML leftovers, balanced math spans, links and
images resolve.

Usage::

    uv run python scripts/verify_output.py build/calculus
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import unquote

RAW_XML_RE = re.compile(r"</?(m:|cnx:|col:|md:|c:)?(para|section|document|metadata|figure|caption|exercise|problem)\b")
MATHML_LEFTOVER_RE = re.compile(r"</?m:[a-z]+")
EMPTY_LINK_RE = re.compile(r"\[\s*\]\(")
LINK_RE = re.compile(r"!?\[[^\]]*\]\(([^)\s]+)\)")


def main(out_dir: str, media_root: str | None = None) -> int:
    out = Path(out_dir).resolve()
    if not out.is_dir():
        print(f"usage: verify_output.py <compiled-output-dir>\nnot a directory: {out}", file=sys.stderr)
        return 2
    files = sorted(out.rglob("*.md"))
    problems: list[str] = []
    checked_links = 0
    anchors = 0

    for path in files:
        text = path.read_text(encoding="utf-8")
        if MATHML_LEFTOVER_RE.search(text):
            problems.append(f"{path}: leftover MathML")
        if RAW_XML_RE.search(text):
            problems.append(f"{path}: leftover CNXML element")
        if EMPTY_LINK_RE.search(text):
            problems.append(f"{path}: empty link text")
        if text.replace("\\$", "").count("$") % 2:
            problems.append(f"{path}: unbalanced $ math delimiters")
        anchors += len(re.findall(r'<a id="[^"]+"></a>', text))
        for target in LINK_RE.findall(text):
            if re.match(r"^[a-z]+:", target, re.I):
                continue
            checked_links += 1
            file_part, _, fragment = target.partition("#")
            resolved = (path.parent / unquote(file_part)).resolve() if file_part else path
            if not resolved.exists():
                problems.append(f"{path}: broken link -> {target}")
                continue
            if fragment and fragment.startswith("fs-"):
                target_text = resolved.read_text(encoding="utf-8") if resolved != path else text
                if f'id="{fragment}"' not in target_text:
                    problems.append(f"{path}: missing anchor {fragment} in {resolved.name}")

    print(f"files: {len(files)}")
    print(f"links/images checked: {checked_links}")
    print(f"anchors emitted: {anchors}")
    print(f"problems: {len(problems)}")
    for problem in problems[:20]:
        print("  -", problem)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
