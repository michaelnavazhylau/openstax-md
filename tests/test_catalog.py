"""Unit tests for catalog search, target resolution, and remote textbook pulling."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest

from openstax_md.catalog import (
    get_cache_dir,
    list_catalog,
    load_catalog,
    pull,
    resolve_target,
    search_catalog,
)


def test_load_catalog() -> None:
    cat = load_catalog()
    assert "metadata" in cat
    assert "repositories" in cat
    assert cat["metadata"]["total_repositories"] >= 50
    assert len(cat["repositories"]) >= 50
    assert len(cat["metadata"]["categories"]) >= 5


def test_get_cache_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # 1. Custom path
    custom = tmp_path / "custom_cache"
    assert get_cache_dir(custom) == custom.resolve()
    assert custom.is_dir()

    # 2. OPENSTAX_MD_CACHE env var
    env_cache = tmp_path / "env_cache"
    monkeypatch.setenv("OPENSTAX_MD_CACHE", str(env_cache))
    assert get_cache_dir() == env_cache.resolve()
    assert env_cache.is_dir()


def test_resolve_target_slug() -> None:
    res = resolve_target("astronomy-2e")
    assert res is not None
    repo, book = res
    assert repo["name"] == "osbooks-astronomy"
    assert book is not None
    assert book["slug"] == "astronomy-2e"


def test_resolve_target_volume_aliases() -> None:
    res1 = resolve_target("calculus-volume-1")
    assert res1 is not None
    assert res1[0]["name"] == "osbooks-calculus-bundle"
    assert res1[1] is not None
    assert res1[1]["slug"] == "calculus-volume-1"

    # calculus-1 should resolve to calculus-volume-1
    res2 = resolve_target("calculus-1")
    assert res2 is not None
    assert res2[0]["name"] == "osbooks-calculus-bundle"
    assert res2[1] is not None
    assert res2[1]["slug"] == "calculus-volume-1"

    # university-physics-1 should resolve to university-physics-volume-1
    res3 = resolve_target("university-physics-1")
    assert res3 is not None
    assert res3[0]["name"] == "osbooks-university-physics-bundle"
    assert res3[1] is not None
    assert res3[1]["slug"] == "university-physics-volume-1"


def test_resolve_target_repo_name() -> None:
    # Single book repo
    res = resolve_target("osbooks-astronomy")
    assert res is not None
    assert res[0]["name"] == "osbooks-astronomy"
    assert res[1] is not None
    assert res[1]["slug"] == "astronomy-2e"

    # Multi book bundle repo
    res_bundle = resolve_target("osbooks-calculus-bundle")
    assert res_bundle is not None
    assert res_bundle[0]["name"] == "osbooks-calculus-bundle"
    assert res_bundle[1] is None


def test_resolve_target_short_name() -> None:
    # 'astronomy'
    res = resolve_target("astronomy")
    assert res is not None
    assert res[0]["name"] == "osbooks-astronomy"

    # 'python'
    res_py = resolve_target("python")
    assert res_py is not None
    assert res_py[0]["name"] == "osbooks-introduction-python-programming"


def test_resolve_target_github_urls() -> None:
    # URL in catalog
    url = "https://github.com/openstax/osbooks-astronomy.git"
    res = resolve_target(url)
    assert res is not None
    assert res[0]["name"] == "osbooks-astronomy"

    # Custom external repo
    ext_url = "https://github.com/custom-org/my-book.git"
    res_ext = resolve_target(ext_url)
    assert res_ext is not None
    assert res_ext[0]["name"] == "my-book"
    assert res_ext[0]["category"] == "External"

    # Custom user/repo shorthand
    res_shorthand = resolve_target("user/my-custom-book")
    assert res_shorthand is not None
    assert res_shorthand[0]["name"] == "my-custom-book"
    assert res_shorthand[0]["full_name"] == "user/my-custom-book"


def test_resolve_target_unresolved_and_empty() -> None:
    assert resolve_target("") is None
    assert resolve_target("   ") is None
    assert resolve_target("completely-non-existent-xyz-book-999") is None


def test_search_catalog() -> None:
    hits = search_catalog("physics")
    assert len(hits) >= 4
    slugs = [h["slug"] for h in hits]
    assert "physics" in slugs
    assert "university-physics-volume-1" in slugs

    # Top hit has high score
    assert hits[0]["score"] >= hits[-1]["score"]

    # Non-matching
    no_hits = search_catalog("unmatched_xyz_query_nonexistent")
    assert len(no_hits) == 0


def test_search_and_list_filters() -> None:
    polish = list_catalog(lang="pl")
    assert len(polish) == 6
    for item in polish:
        assert item["language"] == "pl"

    spanish = list_catalog(lang="es")
    assert len(spanish) == 11
    for item in spanish:
        assert item["language"] == "es"

    math_books = list_catalog(category="Mathematics")
    assert len(math_books) >= 8
    for item in math_books:
        assert item["category"] == "Mathematics"


def test_pull_unresolved_raises(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Could not resolve target"):
        pull("non_existent_book_slug_12345", cache_dir=tmp_path)


def test_pull_already_cached(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Setup fake cached repo
    cached_dir = tmp_path / "osbooks-astronomy"
    (cached_dir / "META-INF").mkdir(parents=True)
    (cached_dir / "META-INF" / "books.xml").write_text("<books/>", encoding="utf-8")
    (cached_dir / "collections").mkdir(parents=True)

    repo_dir, col_slug = pull("astronomy-2e", cache_dir=tmp_path, quiet=True)
    assert repo_dir == cached_dir
    assert col_slug == "astronomy-2e"


def test_pull_cached_add_media(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cached_dir = tmp_path / "osbooks-astronomy"
    (cached_dir / "META-INF").mkdir(parents=True)
    (cached_dir / "META-INF" / "books.xml").write_text("<books/>", encoding="utf-8")
    (cached_dir / "collections").mkdir(parents=True)

    calls: list[list[str]] = []

    def mock_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append(cmd)
        if "media" in cmd:
            (cached_dir / "media").mkdir(parents=True, exist_ok=True)
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", mock_run)

    repo_dir, col_slug = pull("astronomy-2e", cache_dir=tmp_path, include_media=True, quiet=True)
    assert repo_dir == cached_dir
    assert col_slug == "astronomy-2e"
    assert any("sparse-checkout" in c and "media" in c for c in calls)


def test_pull_clone_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def mock_run_fail(cmd: list[str], **kwargs: Any) -> Any:
        raise subprocess.CalledProcessError(1, cmd, stderr="Network unreachable")

    monkeypatch.setattr(subprocess, "run", mock_run_fail)

    with pytest.raises(RuntimeError, match="Git checkout failed"):
        pull("astronomy-2e", cache_dir=tmp_path, force=True, quiet=True)
