"""openstax_md -- High-fidelity compiler transforming OpenStax CNXML/COLLXML to Markdown."""

from __future__ import annotations

from pathlib import Path

from lxml import etree

from .book import BuildContext, Builder, Bundle, CollectionInfo, Entry, find_bundle_root
from .catalog import (
    get_cache_dir,
    list_catalog,
    load_catalog,
    pull,
    resolve_target,
    search_catalog,
)
from .cnxml_bridge import CnxmlLib
from .convert import ModuleInfo, ModuleRenderer, RenderOptions, Target
from .mathml import MathMLConverter

#: Convenience aliases
search = search_catalog
list_books = list_catalog

__version__ = "0.2.0"


def convert_mathml(
    mathml: str | etree._Element,
    *,
    display: bool = False,
    delimiters: str = "dollar",
) -> str:
    """Convert a MathML XML string or element into a LaTeX math expression."""
    if isinstance(mathml, str):
        text = mathml.strip()
        if text.startswith("<m:") and "xmlns:m" not in text:
            text = text.replace(
                "<m:math", '<m:math xmlns:m="http://www.w3.org/1998/Math/MathML"', 1
            )
        node = etree.fromstring(text.encode("utf-8"))
    else:
        node = mathml
    return MathMLConverter(delimiters=delimiters).render(node, force_display=display)


def convert_cnxml(
    source: str | Path,
    *,
    options: RenderOptions | None = None,
) -> str:
    """Convert a single CNXML document or file into Markdown.

    Parameters
    ----------
    source : str | Path
        Either a path to a CNXML file, or an XML string containing the CNXML document.
    options : RenderOptions, optional
        Rendering configuration options.

    Returns
    -------
    str
        Rendered GitHub Flavored Markdown.
    """
    opts = options or RenderOptions()
    if isinstance(source, Path) or (
        isinstance(source, str) and not source.strip().startswith("<") and Path(source).is_file()
    ):
        path = Path(source).resolve()
        bundle = Bundle.from_module(path)
        module = next(iter(bundle.modules.values()))
        builder = Builder(bundle, path.parent, options=opts)
        return builder.render_module(module)

    root = etree.fromstring(source.encode("utf-8") if isinstance(source, str) else source)
    bundle = Bundle(Path.cwd())
    module = ModuleInfo(id="module", source=Path("index.cnxml"))
    builder = Builder(bundle, Path.cwd(), options=opts)
    ctx = BuildContext(builder, module, Path("module.md"))
    return ModuleRenderer(module, ctx).render(root=root)


__all__ = [
    "Builder",
    "Bundle",
    "CnxmlLib",
    "CollectionInfo",
    "Entry",
    "MathMLConverter",
    "ModuleInfo",
    "ModuleRenderer",
    "RenderOptions",
    "Target",
    "__version__",
    "convert_cnxml",
    "convert_mathml",
    "find_bundle_root",
    "get_cache_dir",
    "list_books",
    "list_catalog",
    "load_catalog",
    "pull",
    "resolve_target",
    "search",
    "search_catalog",
]
