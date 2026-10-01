"""Catalog management, remote textbook pulling, and caching for openstax-md.

Provides Docker-style remote pulling of OpenStax repositories with blobless,
sparse checkouts, catalog search, and local cache management.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, cast

#: Path to the bundled offline catalog
CATALOG_PATH = Path(__file__).resolve().parent / "catalog.json"

_CATALOG_CACHE: dict[str, Any] | None = None


def load_catalog(custom_path: Path | str | None = None) -> dict[str, Any]:
    """Load the OpenStax catalog from JSON.

    Uses bundled catalog by default, with caching in memory.
    """
    global _CATALOG_CACHE
    if custom_path is not None:
        path = Path(custom_path).resolve()
        with open(path, encoding="utf-8") as f:
            return cast(dict[str, Any], json.load(f))
    if _CATALOG_CACHE is None:
        if not CATALOG_PATH.is_file():
            raise FileNotFoundError(f"OpenStax catalog not found at {CATALOG_PATH}")
        with open(CATALOG_PATH, encoding="utf-8") as f:
            _CATALOG_CACHE = cast(dict[str, Any], json.load(f))
    return _CATALOG_CACHE


def get_cache_dir(custom_path: Path | str | None = None) -> Path:
    """Return the directory used for caching pulled OpenStax repositories.

    Priority:
    1. custom_path argument
    2. OPENSTAX_MD_CACHE environment variable
    3. ./_osbooks/cache if ./_osbooks exists in current working directory
    4. ~/.cache/openstax-md
    """
    if custom_path:
        cache_dir = Path(custom_path).expanduser().resolve()
    elif os.environ.get("OPENSTAX_MD_CACHE"):
        cache_dir = Path(os.environ["OPENSTAX_MD_CACHE"]).expanduser().resolve()
    elif (Path.cwd() / "_osbooks").is_dir():
        cache_dir = (Path.cwd() / "_osbooks" / "cache").resolve()
    else:
        cache_dir = (Path.home() / ".cache" / "openstax-md").resolve()

    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def _normalize_token(text: str) -> str:
    """Normalize strings for tolerant slug matching."""
    s = text.lower().strip()
    s = re.sub(r"[-_]+", "-", s)
    s = re.sub(r"-(?:volume|vol|tom|volumen)-(\d+)", r"-\1", s)
    return s


def resolve_target(
    target: str, catalog: dict[str, Any] | None = None
) -> tuple[dict[str, Any], dict[str, Any] | None] | None:
    """Resolve a user-provided target string to a repository and optional book.

    Supports:
    - Exact slug (e.g. 'astronomy-2e', 'calculus-volume-1')
    - Repository name (e.g. 'osbooks-astronomy', 'osbooks-calculus-bundle')
    - Short topic alias (e.g. 'astronomy', 'python', 'calculus')
    - GitHub URL or shorthand (e.g. 'openstax/osbooks-astronomy', 'https://github.com/...')

    Returns:
        (repo_info, book_info_or_None) if resolved, or None if unresolved.
    """
    target = target.strip()
    if not target:
        return None

    cat = catalog or load_catalog()
    repos: list[dict[str, Any]] = cat.get("repositories", [])

    # 1. Direct Git / GitHub URLs
    clean_target = target.rstrip("/")
    if clean_target.endswith(".git"):
        clean_target = clean_target[:-4]

    for r in repos:
        repo_urls = (
            r.get("url", ""),
            r.get("clone_url", "").removesuffix(".git"),
            r.get("full_name", ""),
            r.get("name", ""),
        )
        if clean_target in repo_urls or clean_target.lower() in [u.lower() for u in repo_urls]:
            books = r.get("books", [])
            selected_book = books[0] if len(books) == 1 else None
            return r, selected_book

    # External Git URL or custom owner/repo
    if clean_target.startswith(("http://", "https://", "git@", "ssh://")):
        repo_name = clean_target.split("/")[-1].removesuffix(".git")
        synthetic_repo = {
            "name": repo_name,
            "full_name": repo_name,
            "url": clean_target,
            "clone_url": clean_target if clean_target.endswith(".git") else f"{clean_target}.git",
            "category": "External",
            "language": "en",
            "is_bundle": False,
            "books": [],
        }
        return synthetic_repo, None

    if "/" in clean_target and not clean_target.startswith("."):
        parts = clean_target.split("/")
        if len(parts) == 2 and not any(c in parts[0] for c in " :\\"):
            owner, repo_name = parts
            synthetic_repo = {
                "name": repo_name,
                "full_name": f"{owner}/{repo_name}",
                "url": f"https://github.com/{owner}/{repo_name}",
                "clone_url": f"https://github.com/{owner}/{repo_name}.git",
                "category": "External",
                "language": "en",
                "is_bundle": False,
                "books": [],
            }
            return synthetic_repo, None

    # 2. Exact slug match
    target_lower = target.lower()
    for r in repos:
        for b in r.get("books", []):
            if b["slug"].lower() == target_lower:
                return r, b

    # 3. Normalized slug match (e.g. calculus-1 -> calculus-volume-1)
    norm_target = _normalize_token(target)
    for r in repos:
        for b in r.get("books", []):
            if _normalize_token(b["slug"]) == norm_target:
                return r, b

    # 4. Repo name match (with or without 'osbooks-' / '-bundle')
    for r in repos:
        r_name = r["name"].lower()
        short_name = r_name.removeprefix("osbooks-").removesuffix("-bundle")
        if target_lower in (r_name, short_name):
            books = r.get("books", [])
            selected_book = books[0] if len(books) == 1 else None
            return r, selected_book

    # 5. Unique partial slug or title match
    matches: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for r in repos:
        for b in r.get("books", []):
            slug_lower = b["slug"].lower()
            title_lower = b.get("title", "").lower()
            if target_lower in slug_lower or target_lower in title_lower:
                matches.append((r, b))

    if len(matches) == 1:
        return matches[0]

    # If target matches multiple books in the exact same bundle (e.g. 'calculus' -> calculus bundle)
    if matches:
        first_repo = matches[0][0]["name"]
        if all(m[0]["name"] == first_repo for m in matches):
            return matches[0][0], None

    return None


def pull(
    target: str,
    *,
    cache_dir: Path | str | None = None,
    include_media: bool = False,
    quiet: bool = False,
    force: bool = False,
    timeout: int = 180,
    catalog: dict[str, Any] | None = None,
) -> tuple[Path, str | None]:
    """Pull an OpenStax textbook repository into local cache using blobless sparse checkout.

    Parameters
    ----------
    target : str
        Textbook slug, repository name, topic alias, or GitHub URL.
    cache_dir : Path | str, optional
        Custom cache root directory.
    include_media : bool, optional
        Whether to checkout the media/ asset directory (defaults to False for fast pulling).
    quiet : bool, optional
        Suppress informational console messages.
    force : bool, optional
        Re-clone even if already cached.
    timeout : int, optional
        Git operation timeout in seconds.
    catalog : dict, optional
        Custom catalog dictionary.

    Returns
    -------
    tuple[Path, str | None]
        (repository_directory_path, collection_slug_or_None)
    """
    res = resolve_target(target, catalog=catalog)
    if not res:
        raise ValueError(
            f"Could not resolve target '{target}'. "
            "Use 'openstax-md search <query>' or 'openstax-md list' to view available textbooks."
        )

    repo_info, book_info = res
    repo_name = repo_info["name"]
    clone_url = repo_info.get("clone_url") or f"https://github.com/openstax/{repo_name}.git"
    collection_slug = book_info["slug"] if book_info else None

    cache_root = get_cache_dir(cache_dir)
    repo_dir = cache_root / repo_name

    # Check existing cache
    is_cached = (repo_dir / "META-INF" / "books.xml").is_file() or (
        repo_dir / "collections"
    ).is_dir()
    if is_cached and not force:
        if include_media and not (repo_dir / "media").is_dir():
            if not quiet:
                print(
                    f"Adding media sparse-checkout to cached {repo_info.get('full_name', repo_name)}..."
                )
            try:
                subprocess.run(
                    ["git", "sparse-checkout", "add", "media"],
                    cwd=repo_dir,
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                )
            except Exception as e:
                if not quiet:
                    print(f"Warning: failed to fetch media assets: {e}")
        elif not quiet:
            print(f"Using cached {repo_info.get('full_name', repo_name)} ({repo_dir})")
        return repo_dir, collection_slug

    # Clone fresh
    if not quiet:
        print(f"Pulling {repo_info.get('full_name', repo_name)}...")

    if repo_dir.exists():
        shutil.rmtree(repo_dir, ignore_errors=True)

    try:
        subprocess.run(
            [
                "git",
                "clone",
                "--depth",
                "1",
                "--filter=blob:none",
                "--sparse",
                clone_url,
                str(repo_dir),
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        sparse_dirs = ["META-INF", "collections", "modules"]
        if include_media:
            sparse_dirs.append("media")
        subprocess.run(
            ["git", "sparse-checkout", "set", *sparse_dirs],
            cwd=repo_dir,
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.CalledProcessError as exc:
        err_msg = exc.stderr.strip() if exc.stderr else str(exc)
        raise RuntimeError(f"Git checkout failed for {clone_url}: {err_msg}") from exc
    except Exception as exc:
        raise RuntimeError(f"Failed to pull {clone_url}: {exc}") from exc

    if not quiet:
        print(f"Repository cached at {repo_dir}")
        if collection_slug:
            print(f"Target collection: {collection_slug}")

    return repo_dir, collection_slug


def search_catalog(
    query: str,
    *,
    category: str | None = None,
    lang: str | None = None,
    catalog: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Search the OpenStax catalog for textbooks matching a query.

    Returns a list of matching entries sorted by relevance.
    """
    cat = catalog or load_catalog()
    q = query.lower().strip()
    results: list[dict[str, Any]] = []

    for r in cat.get("repositories", []):
        r_category = r.get("category", "")
        r_lang = r.get("language", "en")

        if category and category.lower() not in r_category.lower():
            continue
        if lang and lang.lower() != r_lang.lower():
            continue

        books = r.get("books", [])
        if not books:
            # Repo without book metadata (e.g. sandbox/template)
            if q in r["name"].lower():
                results.append(
                    {
                        "repo": r["name"],
                        "slug": r["name"],
                        "title": r.get("description") or r["name"],
                        "language": r_lang,
                        "category": r_category,
                        "score": 10,
                    }
                )
            continue

        for b in books:
            slug = b["slug"]
            title = b.get("title", slug)
            b_lang = b.get("language", r_lang)
            if lang and lang.lower() != b_lang.lower():
                continue

            score = 0
            if q == slug.lower():
                score = 100
            elif q == title.lower():
                score = 90
            elif slug.lower().startswith(q):
                score = 70
            elif q in slug.lower():
                score = 50
            elif q in title.lower():
                score = 40
            elif q in r["name"].lower():
                score = 30
            elif q in r_category.lower():
                score = 20

            if score > 0 or not q:
                results.append(
                    {
                        "repo": r["name"],
                        "slug": slug,
                        "title": title,
                        "language": b_lang,
                        "category": r_category,
                        "score": score,
                    }
                )

    results.sort(key=lambda item: (-item["score"], item["slug"]))
    return results


def list_catalog(
    *,
    category: str | None = None,
    lang: str | None = None,
    catalog: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """List all textbooks in the catalog, optionally filtered by category or language."""
    return search_catalog("", category=category, lang=lang, catalog=catalog)
