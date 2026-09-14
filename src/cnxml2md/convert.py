"""CNXML -> Markdown conversion.

The renderer walks a CNXML ``<document>`` with ``lxml`` (namespace aware, so both
``<m:math>`` and unprefixed ``<math xmlns="...MathML">`` work) and emits clean
GitHub-flavoured Markdown.

Differences from the original JavaScript ``cnxml2md`` this replaces:

* MathML becomes LaTeX (instead of being flattened to plain text).
* ``<link>`` cross references resolve to Markdown links + anchors.
* Worked examples, exercises, solutions, hints, tables, equations and glossary
  entries are preserved instead of being dropped.
* Media paths are rewritten relative to each output file.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from lxml import etree

from .cnxml_bridge import MATHML_NS
from .mathml import MathMLConverter

_WS_RE = re.compile(r"[ \t\r\f\v]+")
_MULTI_NL_RE = re.compile(r"\n{3,}")

#: CNXML block level elements handled explicitly.
_BLOCK_TAGS = (
    "document",
    "content",
    "section",
    "para",
    "title",
    "list",
    "item",
    "table",
    "figure",
    "subfigure",
    "caption",
    "equation",
    "example",
    "exercise",
    "problem",
    "solution",
    "commentary",
    "note",
    "glossary",
    "definition",
    "meaning",
    "term",
    "metadata",
    "label",
    "target",
    "blockquote",
    "preformat",
    "codeblock",
)

_EMPHASIS = {
    "italics": ("*", "*"),
    "italic": ("*", "*"),
    "bold": ("**", "**"),
    "underline": ("<u>", "</u>"),
}

_KIND_LABELS = {
    "section": "Section",
    "figure": "Figure",
    "table": "Table",
    "equation": "Equation",
    "example": "Example",
    "exercise": "Exercise",
    "note": "Note",
    "solution": "Solution",
    "problem": "Problem",
    "commentary": "Hint",
    "definition": "Definition",
    "glossary": "Glossary",
    "chapter": "Chapter",
    # untitled targets read better as prose
    "para": "this passage",
    "media": "this figure",
    "meaning": "this definition",
    "list": "this list",
    "item": "this item",
}

_NOTE_CLASS_LABELS = {
    "checkpoint": "Checkpoint",
    "theorem": "Theorem",
    "problem-solving": "Problem-Solving Strategy",
    "project": "Project",
}


def localname(node) -> str:
    tag = node.tag
    return etree.QName(tag).localname if isinstance(tag, str) else ""


@dataclass
class RenderOptions:
    math: str = "dollar"  # dollar | bracket | none
    anchors: str = "referenced"  # referenced | always | none
    admonitions: str = "bold"  # bold | block | heading
    media: str = "link"  # link | original | copy
    front_matter: bool = True
    escape_markdown: bool = False


@dataclass
class Target:
    """A linkable element somewhere in the bundle."""

    id: str
    module_id: str
    kind: str
    label: str


@dataclass
class ModuleInfo:
    id: str
    source: Path
    metadata: dict = field(default_factory=dict)

    @property
    def title(self) -> str:
        return self.metadata.get("title") or self.id


class ModuleRenderer:
    """Renders one CNXML module to Markdown."""

    def __init__(self, module: ModuleInfo, ctx: Any) -> None:
        self.module = module
        self.ctx = ctx
        self.opts: RenderOptions = ctx.options
        self.math = MathMLConverter(self.opts.math)
        self._consumed_titles: set = set()
        self._in_example = 0
        self._exercise_counter = 0
        self._blocks = {
            "document": self._document,
            "content": self._container,
            "section": self._section,
            "para": self._para,
            "title": self._title_block,
            "list": self._list,
            "item": self._item_block,
            "table": self._table,
            "figure": self._figure,
            "subfigure": self._figure,
            "caption": self._caption_block,
            "equation": self._equation,
            "example": self._example,
            "exercise": self._exercise,
            "problem": self._problem,
            "solution": self._solution,
            "commentary": self._commentary,
            "note": self._note,
            "glossary": self._glossary,
            "definition": self._definition,
            "meaning": self._meaning,
            "metadata": self._metadata_block,
            "label": self._label_block,
            "target": self._container,
        }
        self._inline = {
            "emphasis": self._emphasis,
            "term": self._term,
            "sup": self._sup,
            "sub": self._sub,
            "link": self._link,
            "math": self._math_inline,
            "newline": self._newline,
            "media": self._media,
            "image": self._image,
            "caption": self._caption_block,
        }

    # ------------------------------------------------------------------
    # entry point
    # ------------------------------------------------------------------

    def render(self, root=None) -> str:
        if root is None:
            with open(self.module.source, "rb") as fh:
                root = etree.parse(fh).getroot()
        parts: list[str] = []
        if self.opts.front_matter:
            parts.append(self.front_matter())
        doc_title = self._document_title(root)
        if doc_title:
            parts.append(f"# {doc_title}")
        parts.append(self.objectives(root))
        parts.append(
            self._content(root, depth=0, skip_first_title=bool(doc_title))
            if localname(root) == "document"
            else self.block(root, 0)
        )
        return self._join(parts)

    def objectives(self, root) -> str:
        """``<md:abstract>`` holds the section's learning objectives."""
        abstract = None
        for el in root.iter():
            if localname(el) == "abstract":
                abstract = el
                break
        if abstract is None or not "".join(abstract.itertext()).strip():
            return ""
        numbers = self.ctx.objective_numbers()
        items = [el for el in abstract.iter() if localname(el) == "item"]
        if items:
            lines = []
            for index, item in enumerate(items):
                prefix = f"**{numbers[index]}** " if index < len(numbers) else ""
                lines.append(f"- {prefix}{self._inline_of(item).strip()}")
            body = "\n".join(lines)
        else:
            body = self._content(abstract, depth=0)
        if not body:
            return ""
        return self._join(["**Learning Objectives**", body])

    def front_matter(self) -> str:
        meta = self.module.metadata or {}
        rows = [
            ("title", meta.get("title")),
            ("module_id", self.module.id),
            ("book", getattr(self.ctx, "book_title", None)),
            ("book_slug", getattr(self.ctx, "book_slug", None)),
            ("uuid", meta.get("uuid")),
            ("language", meta.get("language")),
            ("license", meta.get("license_text")),
            ("license_url", meta.get("license_url")),
            ("source", str(self.module.source.relative_to(self.ctx.bundle_root))
                if self.ctx.bundle_root and self._is_relative(self.module.source, self.ctx.bundle_root)
                else str(self.module.source)),
            ("generator", "cnxml2md (python)"),
        ]
        lines = ["---"]
        for key, value in rows:
            if value in (None, ""):
                continue
            text = str(value).replace("\\", "\\\\").replace('"', '\\"')
            lines.append(f'{key}: "{text}"')
        lines.append("---")
        return "\n".join(lines)

    @staticmethod
    def _is_relative(path: Path, root: Path | None) -> bool:
        if root is None:
            return False
        try:
            path.relative_to(root)
            return True
        except ValueError:
            return False

    def _document_title(self, root) -> str:
        for child in root:
            if localname(child) == "title":
                return self._inline_of(child).strip()
        return self.module.metadata.get("title") or ""

    # ------------------------------------------------------------------
    # block level
    # ------------------------------------------------------------------

    def block(self, el, depth: int = 0) -> str:
        name = localname(el)
        handler = self._blocks.get(name)
        if handler is not None:
            body = handler(el, depth)
        else:
            inline_handler = self._inline.get(name)
            if inline_handler is not None:
                # inline element appearing in a block position (e.g. <math> as a
                # direct child of <item>)
                body = inline_handler(el)
            else:
                self.ctx.count_unhandled(name)
                body = self._inline_of(el).strip()
        return self._with_anchor(el, body)

    def _with_anchor(self, el, text: str, block: bool = True) -> str:
        if not text:
            return text
        anchor_id = el.get("id")
        if not anchor_id or self.opts.anchors == "none":
            return text
        if self.opts.anchors == "referenced" and anchor_id not in self.ctx.referenced_ids:
            return text
        separator = "\n\n" if block else ""
        return f'<a id="{anchor_id}"></a>{separator}{text}'

    def _content(self, el, depth: int = 0, skip_first_title: bool = False) -> str:
        """Render the children of a container as blocks.

        Runs of inline content (text, <math>, <emphasis>, ...) are merged into a
        single paragraph so that sentences interleaved with inline math are not
        split apart.
        """
        blocks: list[str] = []
        buffer: list[str] = []

        def flush() -> None:
            if buffer:
                text = self._clean_inline("".join(buffer))
                if text:
                    blocks.append(text)
                buffer.clear()

        def add_text(text: str | None) -> None:
            if text:
                buffer.append(self._text(text))

        add_text(el.text)
        seen_title = False
        for child in el:
            name = localname(child)
            if name == "metadata":
                continue
            if name == "title" and skip_first_title and not seen_title:
                seen_title = True
                add_text(child.tail)
                continue
            if name == "title":
                seen_title = True
            if name in self._blocks:
                flush()
                blocks.append(self.block(child, depth))
            else:
                buffer.append(self.inline_node(child))
            add_text(child.tail)
        flush()
        return self._join(blocks)

    def _clean_inline(self, text: str) -> str:
        if "\n" in text:
            return "\n".join(
                _WS_RE.sub(" ", line).strip() for line in text.split("\n")
            ).strip()
        return _WS_RE.sub(" ", text).strip()

    @staticmethod
    def _join(blocks: Iterable[str]) -> str:
        kept = [b.strip("\n") for b in blocks if b and b.strip()]
        return _MULTI_NL_RE.sub("\n\n", "\n\n".join(kept)).strip()

    def _inline_of(self, el) -> str:
        parts: list[str] = []
        if el.text:
            parts.append(self._text(el.text))
        for child in el:
            parts.append(self.inline_node(child))
            if child.tail:
                parts.append(self._text(child.tail))
        return self._clean_inline("".join(parts))

    def inline_node(self, el) -> str:
        name = localname(el)
        handler = self._inline.get(name)
        if handler is not None:
            return self._with_anchor(el, handler(el), block=False)
        if name in self._blocks or name in _BLOCK_TAGS:
            return self._with_anchor(el, self.block(el).replace("\n", " ").strip(), block=False)
        self.ctx.count_unhandled(name)
        return self._inline_of(el)

    def _text(self, text: str) -> str:
        # A literal '$' in prose (e.g. "$2.35 per tube") would otherwise open a math
        # span and swallow the following text in any Markdown/LaTeX renderer.
        text = text.replace("$", "\\$")
        if not self.opts.escape_markdown:
            return text
        return text.replace("\\", "\\\\").replace("`", "\\`")

    # -- structural --------------------------------------------------------

    def _document(self, el, depth: int) -> str:
        return self._content(el, depth)

    def _container(self, el, depth: int) -> str:
        return self._content(el, depth)

    def _metadata_block(self, el, depth: int) -> str:
        return ""

    def _label_block(self, el, depth: int) -> str:
        text = self._inline_of(el).strip()
        return f"**{text}**" if text else ""

    def _title_block(self, el, depth: int) -> str:
        if el in self._consumed_titles:
            return ""
        return self._inline_of(el).strip()

    def _section(self, el, depth: int) -> str:
        title = ""
        for child in el:
            if localname(child) == "title":
                title = self._inline_of(child).strip()
                break
        level = min(2 + depth, 6)
        body = self._content(el, depth + 1, skip_first_title=True)
        heading = f"{'#' * level} {title}" if title else ""
        return self._join([heading, body])

    def _para(self, el, depth: int) -> str:
        return self._inline_of(el)

    def _caption_block(self, el, depth: int) -> str:
        text = self._inline_of(el).strip()
        return f"*{text}*" if text else ""

    def _list(self, el, depth: int) -> str:
        ordered = (el.get("list-type") or "") == "enumerated"
        style = el.get("number-style") or ""
        lines: list[str] = []
        number = int(el.get("start-value") or 1)
        for child in el:
            if localname(child) != "item":
                continue
            if ordered:
                if style in ("upper-alpha", "lower-alpha", "upper-roman", "lower-roman"):
                    marker = self._alpha_marker(number, style) + "."
                else:
                    marker = f"{number}."
                number += 1
            else:
                marker = "-"
            body = self._content(child, depth + 1)
            lines.append(self._indent(body, marker + " "))
        return "\n".join(lines)

    @staticmethod
    def _alpha_marker(number: int, style: str) -> str:
        upper = style.startswith("upper")
        if "roman" in style:
            values = (
                (1000, "m"), (900, "cm"), (500, "d"), (400, "cd"),
                (100, "c"), (90, "xc"), (50, "l"), (40, "xl"),
                (10, "x"), (9, "ix"), (5, "v"), (4, "iv"), (1, "i"),
            )
            out, n = "", max(number, 1)
            for value, letters in values:
                while n >= value:
                    out += letters
                    n -= value
            return out.upper() if upper else out
        out = ""
        n = max(number, 1)
        while n > 0:
            n, rem = divmod(n - 1, 26)
            out = chr(ord("a") + rem) + out
        return out.upper() if upper else out

    def _item_block(self, el, depth: int) -> str:
        return self._indent(self._content(el, depth), "- ")

    @staticmethod
    def _indent(text: str, marker: str) -> str:
        lines = text.split("\n")
        pad = " " * len(marker)
        out = [marker + lines[0]] if lines else [marker.strip()]
        out.extend(pad + line if line.strip() else "" for line in lines[1:])
        return "\n".join(line.rstrip() for line in out)

    # -- tables ------------------------------------------------------------

    def _table(self, el, depth: int) -> str:
        table = self._find(el, "tgroup")
        if table is None:
            return self._content(el, depth)
        header_rows: list[list[str]] = []
        body_rows: list[list[str]] = []
        for group in table:
            name = localname(group)
            if name not in ("thead", "tbody", "tfoot"):
                continue
            target = header_rows if name == "thead" else body_rows
            for row in group:
                if localname(row) != "row":
                    continue
                target.append(self._row(row))
        if not header_rows and body_rows:
            header_rows, body_rows = body_rows[:1], body_rows[1:]
        width = max((len(r) for r in header_rows + body_rows), default=0)
        if not width:
            return ""

        lines: list[str] = []
        header = header_rows[0] if header_rows else [f"c{i}" for i in range(width)]
        lines.append("| " + " | ".join(self._pad(header, width)) + " |")
        lines.append("| " + " | ".join(["---"] * width) + " |")
        for row in header_rows[1:] + body_rows:
            lines.append("| " + " | ".join(self._pad(row, width)) + " |")

        prefix = self._block_title(el)
        number = self._number(el)
        if number:
            title = self._title_text(el)
            prefix = f"**{number} {title}**" if title else f"**{number}**"
        label = self._label_text(el)
        caption = ""
        for child in el:
            if localname(child) == "caption":
                text = self._inline_of(child).strip()
                if text:
                    caption = f"*{text}*"
                break
        return self._join([label, prefix, "\n".join(lines), caption])

    @staticmethod
    def _pad(row: list[str], width: int) -> list[str]:
        return row + [""] * (width - len(row))

    def _row(self, row) -> list[str]:
        return [
            self._cell(child)
            for child in row
            if localname(child) == "entry"
        ]

    def _cell(self, entry) -> str:
        text = re.sub(r"\s*\n+\s*", " ", self._inline_of(entry)).strip()
        return text.replace("|", "\\|")

    def _block_title(self, el) -> str:
        text = self._title_text(el)
        return f"**{text}**" if text else ""

    def _title_text(self, el) -> str:
        for child in el:
            if localname(child) == "title":
                return self._inline_of(child).strip()
        return ""

    def _label_text(self, el) -> str:
        for child in el:
            if localname(child) == "label":
                text = self._inline_of(child).strip()
                return f"**{text}**" if text else ""
        return ""

    # -- figures / media ---------------------------------------------------

    def _figure(self, el, depth: int) -> str:
        parts: list[str] = []
        title = self._block_title(el)
        label = self._label_text(el)
        caption = ""
        for child in el:
            if localname(child) == "caption":
                caption = self._inline_of(child).strip()

        subfigures = [c for c in el if localname(c) == "subfigure"]
        if subfigures:
            for sub in subfigures:
                parts.append(self._figure(sub, depth))
            if caption:
                parts.append(f"*{caption}*")
            caption = ""

        media = [m for m in el.iter() if localname(m) == "media"]
        images = [self.inline_node(m) for m in media]
        if not media:
            images = [
                self.inline_node(img)
                for img in el.iter()
                if localname(img) == "image"
            ]
        images = [img for img in images if img]
        if images:
            parts.append("\n\n".join(images))
        if caption:
            number = self._number(el)
            parts.append(f"*{number} {caption}*" if number else f"*{caption}*")
        return self._join([label, title, *parts])

    def _media(self, el, alt_override: str = "") -> str:
        image = None
        for child in el:
            if localname(child) == "image":
                image = child
                break
        if image is None:
            for child in el.iter():
                if localname(child) == "image":
                    image = child
                    break
        if image is None:
            return ""
        alt = alt_override or el.get("alt") or ""
        return self._image(image, alt_override=alt)

    def _image(self, el, alt_override: str = "") -> str:
        src = el.get("src") or ""
        if not src:
            return ""
        href = self.ctx.media_href(self.module, src)
        alt = (alt_override or el.get("alt") or "").strip()
        alt = re.sub(r"\s+", " ", alt)
        alt = (
            alt.replace("\\", "\\\\")
            .replace("[", "\\[")
            .replace("]", "\\]")
            .replace("$", "\\$")
        )
        return f"![{alt}]({href})"

    # -- equations ---------------------------------------------------------

    def _equation(self, el, depth: int) -> str:
        self.ctx.stat("equations")
        math_el = self._find(el, "math")
        if math_el is None:
            return self._content(el, depth)
        latex = self.math.to_latex(math_el).strip()
        if not latex:
            return ""
        label = self._number(el) or self._label_text(el).strip("*").strip()
        tag = label[1:-1] if label.startswith("(") and label.endswith(")") else label
        if self.opts.math == "none":
            # keep the equation number visible when there are no math delimiters
            return self._join([self._label_text(el), latex])
        if tag:
            latex = f"{latex} \\tag{{{tag}}}"
        if self.opts.math == "bracket":
            return f"\\[{latex}\\]"
        return f"$$\n{latex}\n$$"

    # -- admonitions -------------------------------------------------------

    def _admonition(self, label: str, body: str, kind: str = "note") -> str:
        body = body.strip()
        if not body and not label:
            return ""
        style = self.opts.admonitions
        if style == "block":
            head = f"**{label}**" if label else ""
            inner = self._join([head, body])
            return self._quote(inner)
        if style == "heading":
            return self._join([f"#### {label}" if label else "", body])
        head = f"**{label}**" if label else ""
        return self._join([head, body])

    @staticmethod
    def _quote(text: str) -> str:
        lines = []
        for line in text.split("\n"):
            lines.append(f"> {line}".rstrip() if line.strip() else ">")
        return "\n".join(lines)

    def _example(self, el, depth: int) -> str:
        title = self._problem_title(el)
        base = self._number(el) or "Example"
        label = f"{base}: {title}" if title else base
        self._in_example += 1
        try:
            body = self._content(el, depth)
        finally:
            self._in_example -= 1
        return self._admonition(label, body, "example")

    def _exercise(self, el, depth: int) -> str:
        title = self._problem_title(el)
        parent = localname(el.getparent()) if el.getparent() is not None else ""
        if self._in_example or parent == "note":
            # the enclosing example/note already carries the label
            label = ""
        else:
            # review exercises are numbered sequentially within the section,
            # exactly as on the published pages (1. 2. 3. ...)
            self._exercise_counter += 1
            label = f"{self._exercise_counter}."
        body = self._content(el, depth)
        if not label:
            return body
        return self._admonition(label, body, "exercise")

    def _problem(self, el, depth: int) -> str:
        title_el = None
        for child in el:
            if localname(child) == "title":
                title_el = child
                break
        body = self._content(el, depth, skip_first_title=True)
        if title_el is not None and title_el in self._consumed_titles:
            return body
        title = self._inline_of(title_el).strip() if title_el is not None else ""
        if title_el is not None:
            self._consumed_titles.add(title_el)
        return self._join([f"**{title}**" if title else "", body])

    def _problem_title(self, el) -> str:
        problem = self._find(el, "problem")
        if problem is None:
            return ""
        for child in problem:
            if localname(child) == "title":
                if child in self._consumed_titles:
                    return ""
                self._consumed_titles.add(child)
                return self._inline_of(child).strip()
        return ""

    def _solution(self, el, depth: int) -> str:
        return self._admonition("Solution", self._content(el, depth), "solution")

    def _commentary(self, el, depth: int) -> str:
        title = self._inline_of_children_title(el) or (el.get("type") or "Hint").capitalize()
        body = self._content(el, depth, skip_first_title=True)
        return self._admonition(title, body, "commentary")

    def _note(self, el, depth: int) -> str:
        title = (
            self._number(el)
            or self._inline_of_children_title(el)
            or _NOTE_CLASS_LABELS.get(el.get("class") or "", "")
            or "Note"
        )
        body = self._content(el, depth, skip_first_title=True)
        return self._admonition(title, body, "note")

    def _number(self, el) -> str:
        """OpenStax-generated label for an element (``Figure 1.2``, ``Table 1.1``)."""
        return self.ctx.number(el.get("id"))

    def _inline_of_children_title(self, el) -> str:
        for child in el:
            if localname(child) == "title":
                return self._inline_of(child).strip()
        return ""

    # -- glossary ----------------------------------------------------------

    def _glossary(self, el, depth: int) -> str:
        level = min(2 + depth, 6)
        items = [self._definition(d, depth + 1) for d in el if localname(d) == "definition"]
        return self._join([f"{'#' * level} Glossary", "\n".join(i for i in items if i)])

    def _definition(self, el, depth: int) -> str:
        term = ""
        meaning = ""
        for child in el:
            if localname(child) == "term":
                term = self._inline_of(child).strip()
            elif localname(child) == "meaning":
                meaning = self._inline_of(child).strip()
        if not term and not meaning:
            return ""
        if term and meaning:
            return f"- **{term}** — {meaning}"
        return f"- **{term}**" if term else meaning

    def _meaning(self, el, depth: int) -> str:
        return self._inline_of(el)

    # -- inline ------------------------------------------------------------

    def _emphasis(self, el) -> str:
        effect = (el.get("effect") or "italics").lower()
        opener, closer = _EMPHASIS.get(effect, ("*", "*"))
        return f"{opener}{self._inline_of(el)}{closer}"

    def _term(self, el) -> str:
        text = self._inline_of(el)
        parent = localname(el.getparent()) if el.getparent() is not None else ""
        if parent in ("definition", "glossary"):
            return text
        return f"**{text}**"

    def _sup(self, el) -> str:
        return f"<sup>{self._inline_of(el)}</sup>"

    def _sub(self, el) -> str:
        return f"<sub>{self._inline_of(el)}</sub>"

    def _newline(self, el) -> str:
        return "<br/>"

    def _math_inline(self, el) -> str:
        self.ctx.stat("math")
        display = (el.get("display") or "").strip() == "block"
        if not display and self._is_standalone_math(el):
            display = True
        return self.math.render(el, force_display=display)

    def _is_standalone_math(self, el) -> bool:
        """True for a multi-line/aligned expression that sits alone in its block."""
        multi_line = any(
            localname(node) == "mtable"
            or (localname(node) == "mspace" and node.get("linebreak"))
            for node in el.iter()
        )
        if not multi_line:
            return False
        parent = el.getparent()
        if parent is None:
            return True
        if (parent.text or "").strip():
            return False
        for child in parent:
            if (child.tail or "").strip():
                return False
            if child is el or localname(child) in ("math", "newline", "label"):
                continue
            return False
        return True

    def _link(self, el) -> str:
        target_id = el.get("target-id")
        document = el.get("document")
        url = el.get("url")
        text = self._inline_of(el).strip()
        kind = el.get("link-type") or ""

        if url and not document:
            label = text or url
            if url.startswith("#"):
                return f"[{label}]({url})"
            self.ctx.stat("links_external")
            return f"[{label}]({url})"

        if document:
            return self._link_document(document, target_id, text, kind)
        if target_id:
            return self._link_target(None, target_id, text, kind)
        return text

    def _link_document(self, document: str, target_id: str | None, text: str, kind: str) -> str:
        target = self.ctx.lookup_target(document, target_id)
        label = text or (target.label if target else "") or self.ctx.module_titles.get(document, document)
        if target_id and target is None:
            self.ctx.warn(
                f"{self.module.id}: unresolved target '{target_id}' in link to {document}"
            )
        href = self.ctx.module_href(self.ctx.module_id, document, target_id)
        if href is None:
            # target module is not part of this build (partial build): keep the
            # label as plain text rather than emitting a dangling link
            self.ctx.stat("links_outside_build")
            self.ctx.warn(f"{self.module.id}: link to module {document} is outside this build")
            return label
        self.ctx.stat("links_resolved")
        return f"[{label}]({href})"

    def _link_target(self, _module: str | None, target_id: str, text: str, kind: str) -> str:
        target = self.ctx.lookup_target(self.module.id, target_id)
        if target is None:
            self.ctx.warn(f"{self.module.id}: unresolved local reference '{target_id}'")
            self.ctx.stat("links_unresolved")
            label = text or target_id
            return f"[{label}](#{target_id})"
        label = text or target.label
        if target.module_id != self.module.id:
            href = self.ctx.module_href(self.module.id, target.module_id, target_id)
            if href is not None:
                self.ctx.stat("links_resolved")
                return f"[{label}]({href})"
            self.ctx.stat("links_outside_build")
            self.ctx.warn(
                f"{self.module.id}: reference to {target.module_id} is outside this build"
            )
            return label
        self.ctx.stat("links_resolved")
        return f"[{label}](#{target_id})"

    @staticmethod
    def _find(el, name: str):
        for child in el.iter():
            if child is not el and localname(child) == name:
                return child
        return None


def target_label(el, module_id: str, number: str = "") -> Target:
    """Build a :class:`Target` (used by the bundle index) for element ``el``.

    ``number`` is the OpenStax-style generated label (``Figure 1.2``, ``(1.1)``).
    """
    kind = localname(el)
    title = ""
    label_text = ""
    for child in el:
        name = localname(child)
        if name == "title" and not title:
            title = "".join(child.itertext()).strip()
        elif name == "label" and not label_text:
            label_text = "".join(child.itertext()).strip()
    base = _KIND_LABELS.get(kind, kind.capitalize())
    if number:
        # published pages link to "Figure 1.2" / "Example 1.7" / "Equation (1.1)"
        label = f"Equation {number}" if kind == "equation" else number
    elif label_text:
        label = f"{base} {label_text}"
    elif title and base not in ("this passage", "this figure"):
        label = f"{base}: {title}"
    elif title:
        label = f"{base} ({title})"
    else:
        label = base
    return Target(id=el.get("id") or "", module_id=module_id, kind=kind, label=label)
