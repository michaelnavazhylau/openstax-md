"""Packaging invariants: what we publish must match the code that ships.

These tests guard the release path in ``.github/workflows/publish.yml`` -- a
mismatch between ``pyproject.toml``, ``__version__`` and the installed
distribution metadata is publishable-but-wrong, and a missing data file
(``catalog.json`` / ``py.typed``) silently degrades the wheel.
"""

from __future__ import annotations

import importlib.metadata as md_meta
import json
import re
from pathlib import Path
from typing import Any

import pytest

import openstax_md
import openstax_md.cnxml_bridge as bridge
from openstax_md.cli import main

DIST_NAME = "openstax-md"

CNXML = """<document xmlns="http://cnx.rice.edu/cnxml">
<title>Document title</title>
<metadata xmlns:md="http://cnx.rice.edu/mdml">
  <md:content-id>m1</md:content-id>
  <md:uuid>11111111-1111-1111-1111-111111111111</md:uuid>
  <md:title>Canonical title</md:title>
  <md:language>en</md:language>
  <md:slug>canonical-slug</md:slug>
  <md:license url="https://creativecommons.org/licenses/by/4.0/">CC BY 4.0</md:license>
</metadata>
<content><para id="p1">Body.</para></content>
</document>
"""


def _dist_version() -> str:
    try:
        return md_meta.version(DIST_NAME)
    except md_meta.PackageNotFoundError:  # pragma: no cover - bare src runs
        pytest.skip(f"{DIST_NAME} is not installed; distribution metadata unavailable")
        raise


def _canonical(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def test_dunder_version_matches_distribution_metadata() -> None:
    """``--version`` output must equal the version PyPI indexes for the release."""
    assert openstax_md.__version__ == _dist_version()


def test_cli_version_flag_matches_package_version(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """``openstax-md --version`` is intercepted before argparse; keep it in sync."""
    assert main(["--version"]) == 0
    captured = capsys.readouterr()
    assert f"openstax-md {openstax_md.__version__}" in captured.out


def test_console_scripts_are_declared() -> None:
    """Both entry points must be exposed to ``pip``/``uv``/``uvx``."""
    scripts = {
        ep.name
        for ep in md_meta.entry_points(group="console_scripts")
        if ep.dist is not None and _canonical(ep.dist.name) == DIST_NAME
    }
    assert {"openstax-md", "cnxml2md"} <= scripts


def test_package_data_ships_with_the_distribution() -> None:
    """``catalog.json`` drives remote pulling offline; ``py.typed`` enables typing."""
    package_dir = Path(openstax_md.__file__).parent
    assert (package_dir / "catalog.json").is_file()
    assert (package_dir / "py.typed").is_file()


def test_bundled_catalog_is_parseable_and_has_repositories() -> None:
    catalog = openstax_md.load_catalog()
    assert isinstance(catalog, dict)
    assert catalog["repositories"], "bundled catalog must list OpenStax repositories"


def test_bundled_catalog_matches_on_disk_copy() -> None:
    """The loader must not drift from the file that is packaged."""
    package_dir = Path(openstax_md.__file__).parent
    on_disk = json.loads((package_dir / "catalog.json").read_text(encoding="utf-8"))
    assert openstax_md.load_catalog() == on_disk


def test_bridge_degrades_gracefully_without_cnxml(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`pip install openstax-md` ships no cnxml: the compiler must still work.

    Simulated by hiding every candidate root, which is the state of a base
    install with no sibling checkout and no `validation` extra.
    """
    monkeypatch.setattr(bridge, "_candidates", lambda _paths: [])
    lib = bridge.CnxmlLib.load()

    assert lib.available is False
    assert lib.validation_available is False
    assert "validation" in lib.reason

    path = tmp_path / "index.cnxml"
    path.write_text(CNXML, encoding="utf-8")
    meta: dict[str, Any] = lib.parse_metadata(path)
    assert meta["id"] == "m1"
    assert meta["title"] == "Canonical title"
    assert meta["language"] == "en"
    assert meta["slug"] == "canonical-slug"
    assert meta["license_url"] == "https://creativecommons.org/licenses/by/4.0/"
    assert lib.validate_cnxml(path) == ()


def test_fallback_metadata_reader_reads_mdml_values(tmp_path: Path) -> None:
    """Guard the fallback reader that every non-`validation` install depends on."""
    path = tmp_path / "index.cnxml"
    path.write_text(CNXML, encoding="utf-8")
    meta = bridge.read_metadata(path)

    # `md:*` values win over the plain `<title>` document title.
    assert meta["title"] == "Canonical title"
    assert meta["uuid"] == "11111111-1111-1111-1111-111111111111"
    assert meta["license_text"] == "CC BY 4.0"
