"""cnxml2md -- compile OpenStax CNXML/COLLXML to Markdown."""

from .mathml import MathMLConverter

__version__ = "0.2.0"

__all__ = [
    "MathMLConverter",
    "__version__",
]
