"""cnxml2md -- compile OpenStax CNXML/COLLXML to Markdown."""

from .book import Builder, Bundle, Entry, CollectionInfo, find_bundle_root
from .cnxml_bridge import CnxmlLib
from .convert import ModuleInfo, ModuleRenderer, RenderOptions, Target
from .mathml import MathMLConverter

__version__ = "0.2.0"

__all__ = [
    "Builder",
    "Bundle",
    "CollectionInfo",
    "CnxmlLib",
    "Entry",
    "MathMLConverter",
    "ModuleInfo",
    "ModuleRenderer",
    "RenderOptions",
    "Target",
    "__version__",
    "find_bundle_root",
]
