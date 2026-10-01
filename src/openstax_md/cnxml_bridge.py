"""Bridge to the upstream ``cnxml`` python library (openstax/cnxml).

The sibling checkout at ``<workspace>/cnxml`` is the authority for CNXML/COLLXML
namespaces, RNG validation (via ``jing.jar``) and metadata extraction.  We use it
when it is importable and fall back to an internal implementation otherwise, so
the compiler keeps working standalone.

Note: the upstream package still imports ``pkg_resources``, which was removed in
setuptools 81 -- hence the ``setuptools<81`` pin in ``pyproject.toml``.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _localname(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


#: Same namespace map the upstream library ships (used when it is unavailable).
FALLBACK_NSMAP: dict[str, str] = {
    "bib": "http://bibtexml.sf.net/",
    "c": "http://cnx.rice.edu/cnxml",
    "cnxorg": "http://cnx.rice.edu/system-info",
    "col": "http://cnx.rice.edu/collxml",
    "data": "http://www.w3.org/TR/html5/dom.html#custom-data-attribute",
    "datadev": "http://dev.w3.org/html5/spec/#custom",
    "dc": "http://purl.org/dc/elements/1.1/",
    "epub": "http://www.idpf.org/2007/ops",
    "lrmi": "http://lrmi.net/the-specification",
    "m": "http://www.w3.org/1998/Math/MathML",
    "md": "http://cnx.rice.edu/mdml",
    "mod": "http://cnx.rice.edu/#moduleIds",
    "qml": "http://cnx.rice.edu/qml/1.0",
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
}

CNXML_NS = FALLBACK_NSMAP["c"]
COLLXML_NS = FALLBACK_NSMAP["col"]
MDML_NS = FALLBACK_NSMAP["md"]
MATHML_NS = FALLBACK_NSMAP["m"]


def _candidates(search_paths: list[Path]) -> list[Path]:
    """Directories that might hold the ``cnxml`` *project* (containing ``cnxml/``)."""
    env = os.environ.get("CNXML_REPO")
    roots: list[Path] = []
    if env:
        roots.append(Path(env).expanduser())
    roots.extend(search_paths)
    this_file = Path(__file__).resolve()
    roots.extend(
        [
            this_file.parents[2] / "cnxml",  # <workspace>/cnxml
            this_file.parents[3] / "cnxml",
            Path.cwd() / "cnxml",
        ]
    )
    out: list[Path] = []
    for root in roots:
        if (root / "cnxml" / "parse.py").is_file():
            out.append(root)
    return out


class CnxmlLib:
    """Thin facade over the upstream library with graceful degradation."""

    def __init__(
        self,
        source: Path | None = None,
        nsmap: dict[str, str] | None = None,
        reason: str = "",
    ) -> None:
        self.source = source
        self.nsmap = dict(nsmap or FALLBACK_NSMAP)
        self.reason = reason
        self.available = source is not None
        self._parse_metadata = None
        self._validate_cnxml = None
        self._validate_collxml = None

    # -- loading -----------------------------------------------------------

    @classmethod
    def load(cls, search_paths: list[Path] | None = None) -> CnxmlLib:
        for root in _candidates(list(search_paths or [])):
            root_str = str(root)
            added = root_str not in sys.path
            if added:
                sys.path.insert(0, root_str)
            try:
                from cnxml.parse import NSMAP, parse_metadata  # type: ignore
            except Exception:  # pragma: no cover - depends on env
                if added:
                    sys.path.remove(root_str)
                continue

            lib = cls(source=root, nsmap=dict(NSMAP))
            lib._parse_metadata = parse_metadata
            try:
                from cnxml.validation import (  # type: ignore
                    validate_cnxml,
                    validate_collxml,
                )

                lib._validate_cnxml = validate_cnxml
                lib._validate_collxml = validate_collxml
            except Exception as exc:  # pragma: no cover - depends on env
                lib.reason = f"validation unavailable: {exc}"
            return lib
        return cls(reason="cnxml library not found; using built-in fallbacks")

    # -- features ----------------------------------------------------------

    @property
    def validation_available(self) -> bool:
        return self._validate_cnxml is not None

    def parse_metadata(self, path: Path) -> dict:
        """Metadata for a CNXML/COLLXML file (upstream first, fallback second)."""
        if self._parse_metadata is not None:
            try:
                from lxml import etree

                with open(path, "rb") as fh:
                    return dict(self._parse_metadata(etree.parse(fh)))
            except Exception:  # pragma: no cover - malformed input
                pass
        return read_metadata(path)

    def validate_cnxml(self, *paths: Path):
        if self._validate_cnxml is None:
            return ()
        return self._validate_cnxml(*[str(p) for p in paths])

    def validate_collxml(self, *paths: Path):
        if self._validate_collxml is None:
            return ()
        return self._validate_collxml(*[str(p) for p in paths])


def read_metadata(path: Path) -> dict:
    """Minimal namespace-aware metadata reader (mirrors upstream's shape).

    Like :func:`cnxml.parse.parse_metadata`, ``md:*`` elements take
    precedence: a module carries both ``<title>`` (the document title) and
    ``<md:title>`` (the canonical title), and only the latter is authoritative.
    """
    from lxml import etree

    with open(path, "rb") as fh:
        root = etree.parse(fh).getroot()

    def find_text(local: str):
        preferred = f"{{{MDML_NS}}}{local}"
        fallback = None
        for el in root.iter():
            if not isinstance(el.tag, str) or not (el.text and el.text.strip()):
                continue
            if el.tag == preferred:
                return el.text.strip()
            if fallback is None and _localname(el.tag) == local:
                fallback = el.text.strip()
        return fallback

    license_el = None
    for el in root.iter():
        if _localname(el.tag) == "license":
            license_el = el
            break

    return {
        "id": find_text("content-id"),
        "uuid": find_text("uuid"),
        "title": find_text("title"),
        "language": find_text("language"),
        "slug": find_text("slug"),
        "license_url": (license_el.get("url") if license_el is not None else None),
        "license_text": (
            (license_el.text or "").strip() if license_el is not None and license_el.text else None
        ),
    }
