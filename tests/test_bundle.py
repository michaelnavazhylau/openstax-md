"""Integration tests against the real osbooks-calculus-bundle checkout.

Marked ``bundle``: run with ``uv run pytest -m bundle`` (they are skipped when the
bundle is not present next to this repository).
"""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import unquote

import pytest

from openstax_md.book import Builder, Bundle
from openstax_md.cnxml_bridge import CnxmlLib
from openstax_md.convert import RenderOptions

REPO_ROOT = Path(__file__).resolve().parents[1]
BUNDLE = REPO_ROOT / "osbooks-calculus-bundle"

pytestmark = pytest.mark.bundle

MATHML_LEFTOVER = re.compile(r"</?m:[a-zA-Z]+")
CNXML_LEFTOVER = re.compile(
    r"</?(para|section|exercise|problem|solution|commentary|glossary|caption)\b"
)
LINK = re.compile(r"!?\[[^\]]*\]\(([^)\s]+)\)")


@pytest.fixture(scope="module")
def built(tmp_path_factory) -> tuple[Path, object, object]:
    if not BUNDLE.is_dir():
        pytest.skip("osbooks-calculus-bundle not checked out")
    out = tmp_path_factory.mktemp("calculus")
    bundle = Bundle.discover(BUNDLE)
    builder = Builder(bundle, out, options=RenderOptions())
    report = builder.build(collection_slugs=["calculus-volume-1"])
    return out, bundle, report


def test_every_module_converts(built) -> None:
    out, bundle, report = built
    collection = next(c for c in bundle.collections if c.slug == "calculus-volume-1")
    files = sorted(out.glob("modules/*/index.md"))
    assert len(files) == len(set(collection.module_ids))
    assert report.stats["math"] > 10_000
    assert report.stats["equations"] > 500
    assert report.unhandled == {}


def test_no_xml_leftovers(built) -> None:
    out, _, _ = built
    for path in out.rglob("*.md"):
        text = path.read_text(encoding="utf-8")
        assert not MATHML_LEFTOVER.search(text), path
        assert not CNXML_LEFTOVER.search(text), path


def test_latex_is_emitted(built) -> None:
    out, _, _ = built
    text = (out / "modules" / "m53477" / "index.md").read_text(encoding="utf-8")
    assert "\\frac{3}{x-2}" in text  # mfrac
    assert "\\sqrt{" in text
    assert "\\lim_" in (out / "modules" / "m53493" / "index.md").read_text(encoding="utf-8")
    assert "\\begin{cases}" in text  # piecewise absolute value


def test_worked_examples_are_preserved(built) -> None:
    out, _, _ = built
    text = (out / "modules" / "m53477" / "index.md").read_text(encoding="utf-8")
    assert "**Example 1.1: Evaluating Functions**" in text
    assert "**Example 1.11:" in text
    assert "**Solution**" in text
    assert "**Hint**" in text
    assert "**Checkpoint 1.1**" in text
    assert "**Learning Objectives**" in text
    assert "## Glossary" in text
    assert "**Table 1.1 Temperature as a Function of Time of Day**" in text
    assert "*Figure 1.2 A function can be visualized" in text


def test_links_and_images_resolve(built) -> None:
    out, _bundle, _ = built
    broken: list[str] = []
    checked = 0
    for path in out.rglob("*.md"):
        text = path.read_text(encoding="utf-8")
        for target in LINK.findall(text):
            if re.match(r"^[a-z]+:", target, re.IGNORECASE):
                continue
            checked += 1
            file_part, _, fragment = target.partition("#")
            resolved = (path.parent / unquote(file_part)).resolve() if file_part else path
            if not resolved.exists():
                broken.append(f"{path.name}: {target}")
                continue
            if fragment.startswith(("fs-", "CNX")):
                target_text = resolved.read_text(encoding="utf-8")
                if f'id="{fragment}"' not in target_text:
                    broken.append(f"{path.name}: missing anchor {fragment}")
    assert checked > 1000
    assert broken == []


def test_cross_module_link_points_at_the_right_module(built) -> None:
    out, _, _ = built
    text = (out / "modules" / "m53494" / "index.md").read_text(encoding="utf-8")
    assert "../m53495/index.md#fs-id1169739204154" in text


def test_metadata_front_matter_comes_from_cnxml_lib(built) -> None:
    out, _bundle, _ = built
    lib = CnxmlLib.load([BUNDLE.parent / "cnxml"])
    if not lib.available:
        pytest.skip("cnxml library not importable")
    meta = lib.parse_metadata(BUNDLE / "modules" / "m53477" / "index.cnxml")
    text = (out / "modules" / "m53477" / "index.md").read_text(encoding="utf-8")
    assert f'uuid: "{meta["uuid"]}"' in text
    assert f'title: "{meta["title"]}"' in text
