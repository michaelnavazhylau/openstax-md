"""MathML (Presentation) -> LaTeX conversion.

Written for OpenStax CNXML content: handles the constructs that actually occur
in the calculus bundle (see ``docs/gap-report.md``), and degrades gracefully to
plain text for anything it does not know.

Public API::

    conv = MathMLConverter()
    conv.render(math_element)          # -> "$...$" / "$$...$$"
    conv.to_latex(math_element)        # -> raw latex, no delimiters
"""

from __future__ import annotations

import re

from lxml import etree

MATHML_NS = "http://www.w3.org/1998/Math/MathML"

# ---------------------------------------------------------------------------
# symbol tables
# ---------------------------------------------------------------------------

#: operators / relation symbols as they appear in MathML text nodes
_OPERATORS: dict[str, str] = {
    "\u2212": "-",  # minus sign
    "\u2013": "-",
    "\u2014": "-",
    "\u00d7": r"\times",
    "\u00f7": r"\div",
    "\u22c5": r"\cdot",
    "\u2219": r"\cdot",
    "\u00b7": r"\cdot",
    "\u2217": "*",
    "\u2218": r"\circ",
    "\u2264": r"\le",
    "\u2265": r"\ge",
    "\u2260": r"\ne",
    "\u2248": r"\approx",
    "\u2245": r"\cong",
    "\u2261": r"\equiv",
    "\u223c": r"\sim",
    "\u221d": r"\propto",
    "\u2208": r"\in",
    "\u2209": r"\notin",
    "\u220b": r"\ni",
    "\u2282": r"\subset",
    "\u2286": r"\subseteq",
    "\u2283": r"\supset",
    "\u2287": r"\supseteq",
    "\u222a": r"\cup",
    "\u2229": r"\cap",
    "\u2205": r"\emptyset",
    "\u221e": r"\infty",
    "\u2192": r"\to",
    "\u2190": r"\leftarrow",
    "\u2194": r"\leftrightarrow",
    "\u21d2": r"\Rightarrow",
    "\u21d4": r"\Leftrightarrow",
    "\u21a6": r"\mapsto",
    "\u2032": "'",
    "\u2033": "''",
    "|": "|",
    "\u2202": r"\partial",
    "\u2207": r"\nabla",
    "\u0394": r"\Delta",
    "\u2206": r"\Delta",
    "\u03c0": r"\pi",
    "\u03b8": r"\theta",
    "\u03bb": r"\lambda",
    "\u03bc": r"\mu",
    "\u03c3": r"\sigma",
    "\u03c6": r"\varphi",
    "\u03c9": r"\omega",
    "\u2211": r"\sum",
    "\u220f": r"\prod",
    "\u222b": r"\int",
    "\u222e": r"\oint",
    "\u2210": r"\coprod",
    "\u22c3": r"\bigcup",
    "\u22c2": r"\bigcap",
    "\u00b1": r"\pm",
    "\u2213": r"\mp",
    # greek (lower case)
    "\u03b1": r"\alpha",
    "\u03b2": r"\beta",
    "\u03b3": r"\gamma",
    "\u03b4": r"\delta",
    "\u03b5": r"\varepsilon",
    "\u03b6": r"\zeta",
    "\u03b7": r"\eta",
    "\u03b9": r"\iota",
    "\u03ba": r"\kappa",
    "\u03bd": r"\nu",
    "\u03be": r"\xi",
    "\u03c1": r"\rho",
    "\u03c2": r"\varsigma",
    "\u03c4": r"\tau",
    "\u03c5": r"\upsilon",
    "\u03c7": r"\chi",
    "\u03d5": r"\phi",
    "\u03c8": r"\psi",
    # greek (upper case)
    "\u0393": r"\Gamma",
    "\u0398": r"\Theta",
    "\u039b": r"\Lambda",
    "\u039e": r"\Xi",
    "\u03a0": r"\Pi",
    "\u03a3": r"\Sigma",
    "\u03a5": r"\Upsilon",
    "\u03a6": r"\Phi",
    "\u03a8": r"\Psi",
    "\u03a9": r"\Omega",
    # fences, norms, big operators, misc symbols
    "\u27e8": r"\langle",
    "\u27e9": r"\rangle",
    "\u2329": r"\langle",
    "\u232a": r"\rangle",
    "\u2016": r"\|",
    "\u222c": r"\iint",
    "\u222d": r"\iiint",
    "\u22ef": r"\cdots",
    "\u2026": r"\ldots",
    "\u2243": r"\simeq",
    "\u25e6": r"\circ",
    "\u2022": r"\bullet",
    "\u2113": r"\ell",
    "\u2034": "'''",
    "\u23de": r"\overbrace{}",
    "\u23df": r"\underbrace{}",
    # invisible/zero width characters are dropped
    "\u200b": "",
    "\u200c": "",
    "\u200d": "",
    "\ufeff": "",
    "\u2220": r"\angle",
    "\u22a5": r"\perp",
    "\u2225": r"\parallel",
    "\u2200": r"\forall",
    "\u2203": r"\exists",
    "\u00ac": r"\neg",
    "\u2227": r"\wedge",
    "\u2228": r"\vee",
    "\u226a": r"\ll",
    "\u226b": r"\gg",
    "\u224d": r"\asymp",
    "\u221a": r"\sqrt{}",
    "\u211d": r"\mathbb{R}",
    "\u2115": r"\mathbb{N}",
    "\u2124": r"\mathbb{Z}",
    "\u211a": r"\mathbb{Q}",
    "\u00b0": r"^{\circ}",
    "\u00ba": r"^{\circ}",
}

#: operator-like multi-character text inside <mo>
_BIG_OPERATORS = {
    "\u2211": r"\sum",
    "\u220f": r"\prod",
    "\u222b": r"\int",
    "\u222e": r"\oint",
    "\u2210": r"\coprod",
    "\u22c3": r"\bigcup",
    "\u22c2": r"\bigcap",
    "lim": r"\lim",
}

#: function names that take an underscript instead of a subscript
_FUNCTIONS = {
    "lim",
    "max",
    "min",
    "sup",
    "inf",
    "det",
    "gcd",
    "lcm",
    "sin",
    "cos",
    "tan",
    "csc",
    "sec",
    "cot",
    "sinh",
    "cosh",
    "tanh",
    "coth",
    "sech",
    "csch",
    "arcsin",
    "arccos",
    "arctan",
    "arcsinh",
    "arccosh",
    "arctanh",
    "arcsec",
    "arccsc",
    "arccot",
    "curl",
    "div",
    "grad",
    "ln",
    "log",
    "exp",
    "deg",
    "dim",
    "hom",
    "ker",
    "arg",
}

#: subset of the above that the renderer knows as native operators (\\sin, \\ln ...)
_NATIVE_OPERATORS = {
    "lim",
    "max",
    "min",
    "sup",
    "inf",
    "det",
    "gcd",
    "sin",
    "cos",
    "tan",
    "csc",
    "sec",
    "cot",
    "sinh",
    "cosh",
    "tanh",
    "coth",
    "arcsin",
    "arccos",
    "arctan",
    "ln",
    "log",
    "exp",
    "deg",
    "dim",
    "hom",
    "ker",
    "arg",
}

_ACCENTS = {
    "^": r"\hat",
    "\u02c6": r"\hat",
    "\u0302": r"\hat",
    "\u00af": r"\bar",
    "\u0304": r"\bar",
    "\u203e": r"\bar",
    "\u2192": r"\vec",
    "\u20d7": r"\vec",
    "\u02d9": r"\dot",
    "\u0307": r"\dot",
    "\u00a8": r"\ddot",
    "\u0308": r"\ddot",
    "\u007e": r"\tilde",
    "\u02dc": r"\tilde",
    "\u0303": r"\tilde",
}

_SCRIPTED = {"msup", "msub", "msubsup", "munder", "mover", "munderover", "mfrac"}

_MATHVARIANTS = {
    "bold": r"\mathbf",
    "bold-italic": r"\boldsymbol",
    "italic": r"\mathit",
    "double-struck": r"\mathbb",
    "fraktur": r"\mathfrak",
    "script": r"\mathcal",
    "sans-serif": r"\mathsf",
    "monospace": r"\mathtt",
}

_MATH_ONLY_ESCAPES = {"~": r"\sim"}

_TEXT_ESCAPES = {
    "\\": r"\backslash ",
    "{": r"\{",
    "}": r"\}",
    "$": r"\$",
    "&": r"\&",
    "#": r"\#",
    "%": r"\%",
    "_": r"\_",
    "^": r"\^{}",
    "~": r"\~{}",
    "|": r"\vert ",
    # normalise typographic characters that show up inside <mn>/<mi>/<mtext>
    "\u2212": "-",  # minus sign -> ascii hyphen (portable in every renderer)
    "\u00a0": " ",
}

_ALPHA_COMMAND_RE = re.compile(r"^\\[a-zA-Z]+$")
#: invisible formatting characters (zero width space, function application, ...)
_INVISIBLE_RE = re.compile("[\u00ad\u180e\u200b-\u200f\u202a-\u202e\u2060-\u206f\ufeff]")
#: a latex fragment that already ends in a script group, e.g. ``x^{2}``
_SCRIPT_TAIL_RE = re.compile(r"[\^_]\{[^{}]*\}$")

_SPACE_WIDTHS = (
    (0.2, r"\,"),
    (0.36, r"\:"),
    (0.6, r"\;"),
    (1.2, r"\quad"),
)


def _localname(node) -> str:
    tag = node.tag
    if not isinstance(tag, str):
        return ""
    return etree.QName(tag).localname


def _escape_text(text: str) -> str:
    return "".join(_TEXT_ESCAPES.get(ch, ch) for ch in _INVISIBLE_RE.sub("", text))


def _map_operator(text: str) -> str:
    """Map an ``<mo>``/``<mi>``/``<mn>`` text node to LaTeX, char by char when needed."""
    text = _INVISIBLE_RE.sub("", text)
    if text in _OPERATORS:
        return _terminate(_OPERATORS[text])
    out = []
    for ch in text:
        if ch in _OPERATORS:
            out.append(_terminate(_OPERATORS[ch]))
        elif ch in _MATH_ONLY_ESCAPES:
            out.append(_terminate(_MATH_ONLY_ESCAPES[ch]))
        elif ch in _TEXT_ESCAPES:
            out.append(_TEXT_ESCAPES[ch])
        else:
            out.append(ch)
    return "".join(out)


def _terminate(command: str) -> str:
    """Add a space after alphabetic commands so ``\\circ`` + ``f`` is not ``\\circf``."""
    return command + " " if _ALPHA_COMMAND_RE.match(command) else command


def _plain_text(node) -> str:
    return "".join(node.itertext())


def _function_command(name: str) -> str | None:
    """LaTeX for a function name, or ``None`` if it is not a function."""
    lowered = name.strip().lower()
    if not lowered or not lowered.isalpha() or lowered not in _FUNCTIONS:
        return None
    if lowered in _NATIVE_OPERATORS:
        return "\\" + lowered + " "
    return "\\operatorname{" + lowered + "}"


class MathMLConverter:
    """Convert a MathML subtree to LaTeX."""

    def __init__(self, delimiters: str = "dollar") -> None:
        """``delimiters``: ``dollar`` (``$``/``$$``), ``bracket`` (``\\(``/``\\[``) or ``none``."""
        self.delimiters = delimiters

    # -- public ------------------------------------------------------------

    def render(self, node, force_display: bool = False) -> str:
        """Render a ``<math>`` element, including delimiters."""
        display = force_display or (node.get("display") or "").strip() == "block"
        body = self.to_latex(node).strip()
        if not body:
            # the source contains empty <m:math/> placeholders; emitting bare
            # delimiters would corrupt every following display-math block
            return ""
        if self.delimiters == "none":
            return body
        if self.delimiters == "bracket":
            return f"\\[{body}\\]" if display else f"\\({body}\\)"
        return f"$$\n{body}\n$$" if display else f"${body}$"

    def to_latex(self, node) -> str:
        """Render any MathML element to raw LaTeX."""
        handler = getattr(self, "_" + _localname(node).replace("-", "_"), None)
        if handler is not None:
            return str(handler(node))
        return self._children(node)

    # -- generic helpers ---------------------------------------------------

    @staticmethod
    def _inside_table(node) -> bool:
        parent = node.getparent()
        while parent is not None:
            if _localname(parent) == "mtable":
                return True
            parent = parent.getparent()
        return False

    @staticmethod
    def _follows_function(node) -> bool:
        """True when the previous sibling is a function name (\\sin, \\operatorname{...})."""
        previous = node.getprevious()
        while previous is not None and _localname(previous) in ("mspace",):
            previous = previous.getprevious()
        if previous is None:
            return False
        return _function_command(_plain_text(previous)) is not None

    @staticmethod
    def _thin(width: str) -> bool:
        if not width:
            return True
        if width.endswith("em"):
            try:
                return float(width[:-2]) <= 0.36
            except ValueError:
                return True
        return False

    def _children(self, node) -> str:
        return "".join(self.to_latex(child) for child in node)

    def _child(self, node, index: int, default: str = "") -> str:
        kids = list(node)
        if index >= len(kids):
            return default
        return self.to_latex(kids[index])

    def _is_cases_table(self, node) -> bool:
        """True for the ``{ ... piecewise }`` pattern CNXML uses."""
        parent = node.getparent()
        for _ in range(3):
            if parent is None:
                return False
            if _localname(parent) == "mfenced":
                return (parent.get("open") or "(") in ("{", "(")
            sibling = parent.getprevious()
            while sibling is not None:
                if _localname(sibling) == "mo" and (sibling.text or "").strip() in ("{",):
                    return True
                sibling = sibling.getprevious()
            parent = parent.getparent()
        return False

    # -- token elements ----------------------------------------------------

    def _mi(self, node) -> str:
        text = _plain_text(node).strip()
        if not text:
            return ""
        if len(text) > 1 and text.isalpha() and all(ord(c) < 128 for c in text):
            return r"\mathit{" + _escape_text(text) + "}"
        return _map_operator(text)

    def _mn(self, node) -> str:
        return _map_operator(_plain_text(node).strip())

    def _mo(self, node) -> str:
        text = _plain_text(node)
        if not text:
            return ""
        return _map_operator(text)

    def _mtext(self, node) -> str:
        text = _plain_text(node)
        if not text.strip():
            return ""
        stripped = text.strip()
        # single symbols (\u221e, -, \u2264 ...) render better as math than inside \text
        if stripped in _OPERATORS:
            return _terminate(_OPERATORS[stripped])
        # \text{sin}\,x -> \sin x (proper operator spacing/rendering)
        command = _function_command(stripped)
        if command is not None:
            return command
        # bold unit vectors are written as <mstyle bold><mtext>i</mtext></mstyle>;
        # \mathbf{\text{i}} should be \mathbf{i}
        if len(stripped) == 1 and stripped.isalpha() and self._in_bold_context(node):
            return _escape_text(stripped)
        return self._text_with_symbols(text)

    @staticmethod
    def _in_bold_context(node) -> bool:
        parent = node.getparent()
        while parent is not None and _localname(parent) != "math":
            if _localname(parent) == "mstyle":
                variant = (parent.get("mathvariant") or "").strip()
                if variant.startswith("bold"):
                    return True
            parent = parent.getparent()
        return False

    @staticmethod
    def _text_with_symbols(text: str) -> str:
        """Wrap text in ``\\text{}``, lifting mapped non-ASCII symbols out of it.

        Keeps e.g. ``\\text{Ω}`` from becoming an unknown symbol for the renderer.
        """
        parts: list[str] = []
        buffer: list[str] = []

        def flush() -> None:
            if buffer:
                parts.append(r"\text{" + _escape_text("".join(buffer)) + "}")
                buffer.clear()

        for ch in text:
            mapped = _OPERATORS.get(ch)
            if mapped is not None and ord(ch) > 127:
                flush()
                parts.append(_terminate(mapped))
            else:
                buffer.append(ch)
        flush()
        return "".join(parts)

    def _ms(self, node) -> str:
        return r"\text{" + _escape_text(_plain_text(node)) + "}"

    def _mspace(self, node) -> str:
        if (node.get("linebreak") or "") in ("newline", "indentingnewline"):
            # only meaningful inside a table; at the top level of display math
            # LaTeX ignores "\\" (KaTeX warns)
            return r"\\" if self._inside_table(node) else ""
        width = (node.get("width") or "").strip()
        if self._follows_function(node) and self._thin(width):
            # \text{sin}\,x -> \sin x: the operator already provides the space
            return ""
        if not width:
            return r"\,"
        if width.endswith("em"):
            try:
                value = float(width[:-2])
            except ValueError:
                return r"\,"
            for limit, latex in _SPACE_WIDTHS:
                if value <= limit:
                    return _terminate(latex)
            return _terminate(r"\qquad")
        if width.endswith(("ex", "pt")):
            return _terminate(r"\," if width in ("0.2ex", "1pt") else r"\;")
        return r"\,"

    # -- layout schemata ---------------------------------------------------

    def _mrow(self, node) -> str:
        return self._children(node)

    def _mfrac(self, node) -> str:
        return r"\frac{" + self._child(node, 0) + "}{" + self._child(node, 1) + "}"

    def _msqrt(self, node) -> str:
        return r"\sqrt{" + self._children(node) + "}"

    def _mroot(self, node) -> str:
        return r"\sqrt[" + self._child(node, 1) + "]{" + self._child(node, 0) + "}"

    def _msup(self, node) -> str:
        return self._script_base(node, 0) + "^{" + self._child(node, 1) + "}"

    def _msub(self, node) -> str:
        return self._script_base(node, 0) + "_{" + self._child(node, 1) + "}"

    def _msubsup(self, node) -> str:
        return (
            self._script_base(node, 0)
            + "_{"
            + self._child(node, 1)
            + "}^{"
            + self._child(node, 2)
            + "}"
        )

    def _script_base(self, node, index: int) -> str:
        """Base of a script expression; needs braces when already scripted."""
        child = list(node)[index] if index < len(node) else None
        if child is None:
            return ""
        text = _plain_text(child).strip()
        if len(child) == 0 and not text:
            # <m:msup><m:mrow/><m:mi>n</m:mi></m:msup> occurs in the source: an
            # empty base must not emit a bare "^{n}" ("double superscript")
            return "{}"
        if len(child) == 0 and text:
            command = _function_command(text)
            if command is not None:
                return command
            return _map_operator(text)
        body = self.to_latex(child)
        if _localname(child) in _SCRIPTED or _SCRIPT_TAIL_RE.search(body):
            # (x^{2})^{2} / mrow ending in a superscript -- avoids "double superscript"
            return "{" + body + "}"
        return body

    def _mfenced(self, node) -> str:
        opener = node.get("open", "(")
        closer = node.get("close", ")")
        separators = node.get("separators", ",")

        children = list(node)
        # separators apply between the top-level children of the fence; CNXML
        # almost always wraps them in a single <mrow>.
        if len(children) == 1 and _localname(children[0]) == "mrow":
            children = list(children[0])
        if separators and separators != ",":
            joiner = " " + separators.strip() + " "
        else:
            joiner = ", "
        inner = joiner.join(self.to_latex(child) for child in children)

        left = "" if not opener else r"\left" + _brace(opener)
        right = "." if not closer else _brace(closer)
        return f"{left} {inner} \\right{right}"

    def _mstyle(self, node) -> str:
        body = self._children(node)
        variant = (node.get("mathvariant") or "").strip()
        command = _MATHVARIANTS.get(variant)
        # don't wrap bare operators/punctuation in \mathbf{...}
        has_alnum = any(ch.isalnum() for ch in _plain_text(node))
        if command and body and has_alnum:
            return f"{command}{{{body}}}"
        return body

    def _mover(self, node) -> str:
        base = self._child(node, 0)
        over = self._child(node, 1)
        over_text = _plain_text(list(node)[1]).strip() if len(node) > 1 else ""
        accent = _ACCENTS.get(over_text)
        if accent and node.get("accent") != "false":
            return f"{accent}{{{base}}}"
        return r"\overset{" + over + "}{" + base + "}"

    def _munder(self, node) -> str:
        base = self._child(node, 0)
        under = self._child(node, 1)
        base_text = _plain_text(next(iter(node))).strip() if len(node) else ""
        command = _function_command(base_text)
        if command is not None:
            return f"{command.strip()}_{{{under}}}"
        if base_text in _BIG_OPERATORS:
            return f"{_BIG_OPERATORS[base_text]}_{{{under}}}"
        return _terminate(r"\underset") + "{" + under + "}{" + base + "}"

    def _munderover(self, node) -> str:
        base = self._child(node, 0)
        under = self._child(node, 1)
        over = self._child(node, 2)
        base_text = _plain_text(next(iter(node))).strip() if len(node) else ""
        command = _function_command(base_text)
        if command is not None:
            return f"{command.strip()}_{{{under}}}^{{{over}}}"
        if base_text in _BIG_OPERATORS:
            return f"{_BIG_OPERATORS[base_text]}_{{{under}}}^{{{over}}}"
        return r"\overset{" + over + r"}{\underset{" + under + "}{" + base + "}}"

    def _mtable(self, node) -> str:
        rows = [self._mtr(child) for child in node if _localname(child) in ("mtr", "mlabeledtr")]
        env = "cases" if self._is_cases_table(node) else "matrix"
        body = r" \\ ".join(row for row in rows if row.strip())
        return f"\\begin{{{env}}} {body} \\end{{{env}}}"

    def _mtr(self, node) -> str:
        cells = [self.to_latex(child) for child in node if _localname(child) in ("mtd",)]
        return " & ".join(cells)

    def _mtd(self, node) -> str:
        return self._children(node)

    def _menclose(self, node) -> str:
        notation = (node.get("notation") or "").strip()
        body = self._children(node)
        if notation == "box":
            return r"\boxed{" + body + "}"
        if "updiagonalstrike" in notation or "downdiagonalstrike" in notation:
            return r"\cancel{" + body + "}"
        return r"\overline{" + body + "}"

    def _mpadded(self, node) -> str:
        return self._children(node)

    def _semantics(self, node) -> str:
        return self._child(node, 0) or self._children(node)

    def _annotation(self, node) -> str:  # pragma: no cover - not rendered
        return ""

    def _annotation_xml(self, node) -> str:  # pragma: no cover - not rendered
        return ""

    def _math(self, node) -> str:
        return self._children(node)


def _brace(char: str) -> str:
    """Escape a delimiter for use after ``\\left``/``\\right``."""
    if char in "()[]|":
        return char
    if char == ".":
        return "."
    if char in "{}":
        return "\\" + char
    if char == "\u27e8":
        return r"\langle"
    if char == "\u27e9":
        return r"\rangle"
    return char
