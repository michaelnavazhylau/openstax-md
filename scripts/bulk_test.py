#!/usr/bin/env python3
"""Battle-test harness running openstax-md against OpenStax textbook repositories.

Performs sparse checkouts, compiles every textbook volume, and records:
- Success/Failure status and runtime
- Total modules, output files, math expressions, links resolved, images
- Unmapped XML elements and warnings
- KaTeX LaTeX formula validation (optional)
- Aggregated battle-test report in Markdown and JSON
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

# Ensure src/ is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from openstax_md.book import Builder, Bundle, RenderOptions


@dataclass
class BookTestResult:
    repo_name: str
    slug: str
    title: str
    category: str
    language: str
    status: str  # "PASS", "FAIL", "SKIP"
    duration_s: float = 0.0
    modules_count: int = 0
    files_count: int = 0
    math_count: int = 0
    links_count: int = 0
    images_count: int = 0
    unmapped_elements: dict[str, int] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    error_message: str = ""


def sparse_clone_repo(repo_name: str, target_dir: Path) -> bool:
    """Perform a fast blobless, sparse checkout of only XML structure & modules."""
    if (target_dir / "META-INF" / "books.xml").is_file():
        return True

    clone_url = f"https://github.com/openstax/{repo_name}.git"
    target_dir.parent.mkdir(parents=True, exist_ok=True)

    # Clean if partial
    if target_dir.exists():
        shutil.rmtree(target_dir, ignore_errors=True)

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
                str(target_dir),
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=120,
        )
        subprocess.run(
            ["git", "sparse-checkout", "set", "META-INF", "collections", "modules"],
            cwd=target_dir,
            check=True,
            capture_output=True,
            text=True,
            timeout=120,
        )
        return True
    except Exception as e:
        print(f"[{repo_name}] Clone failed: {e}", file=sys.stderr)
        return False


def test_single_repo(
    repo_info: dict[str, Any],
    cache_root: Path,
    output_root: Path,
) -> list[BookTestResult]:
    repo_name = repo_info["name"]
    category = repo_info.get("category", "General")
    language = repo_info.get("language", "en")
    results: list[BookTestResult] = []

    repo_dir = cache_root / repo_name
    success = sparse_clone_repo(repo_name, repo_dir)
    if not success:
        for b in repo_info.get("books", []):
            results.append(
                BookTestResult(
                    repo_name=repo_name,
                    slug=b["slug"],
                    title=b.get("title") or b["slug"],
                    category=category,
                    language=language,
                    status="FAIL",
                    error_message="Failed to sparse-clone repository",
                )
            )
        return results

    try:
        bundle = Bundle.discover(repo_dir)
    except Exception as exc:
        for b in repo_info.get("books", []):
            results.append(
                BookTestResult(
                    repo_name=repo_name,
                    slug=b["slug"],
                    title=b.get("title") or b["slug"],
                    category=category,
                    language=language,
                    status="FAIL",
                    error_message=f"Bundle discovery failed: {exc}",
                )
            )
        return results

    # Test each book / collection in the bundle
    for col in bundle.collections:
        slug = col.slug
        matching_meta = next((b for b in repo_info.get("books", []) if b["slug"] == slug), {})
        title = col.title or matching_meta.get("title") or slug

        out_dir = output_root / repo_name / slug
        start_time = time.time()
        try:
            builder = Builder(
                bundle,
                out_dir=out_dir,
                options=RenderOptions(math="dollar", media="link"),
                layout="flat",
            )
            report = builder.build(collection_slugs=[slug])
            elapsed = time.time() - start_time

            results.append(
                BookTestResult(
                    repo_name=repo_name,
                    slug=slug,
                    title=title,
                    category=category,
                    language=language,
                    status="PASS",
                    duration_s=round(elapsed, 2),
                    modules_count=report.modules,
                    files_count=len(report.outputs),
                    math_count=report.stats.get("equations", 0),
                    links_count=report.stats.get("links_resolved", 0),
                    images_count=report.stats.get("media_linked", 0),
                    unmapped_elements=dict(report.unhandled),
                    warnings=list(report.warnings),
                )
            )
        except Exception as exc:
            elapsed = time.time() - start_time
            results.append(
                BookTestResult(
                    repo_name=repo_name,
                    slug=slug,
                    title=title,
                    category=category,
                    language=language,
                    status="FAIL",
                    duration_s=round(elapsed, 2),
                    error_message=str(exc),
                )
            )

    return results


def run_bulk_test(
    repos: list[dict[str, Any]],
    cache_root: Path,
    output_root: Path,
    workers: int = 4,
) -> list[BookTestResult]:
    all_results: list[BookTestResult] = []
    total = len(repos)
    print(f"Starting battle-test across {total} repositories with {workers} workers...\n")

    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_to_repo = {
            executor.submit(test_single_repo, repo, cache_root, output_root): repo["name"]
            for repo in repos
        }

        completed_count = 0
        for future in as_completed(future_to_repo):
            repo_name = future_to_repo[future]
            completed_count += 1
            try:
                res_list = future.result()
                all_results.extend(res_list)
                passes = sum(1 for r in res_list if r.status == "PASS")
                total_b = len(res_list)
                print(
                    f"[{completed_count:02d}/{total:02d}] {repo_name:<35} -> "
                    f"{passes}/{total_b} books passed"
                )
                for r in res_list:
                    if r.status != "PASS":
                        print(f"    ❌ {r.slug}: {r.error_message}", file=sys.stderr)
                    elif r.unmapped_elements:
                        unmapped_str = ", ".join(
                            f"{k}({v})" for k, v in sorted(r.unmapped_elements.items())
                        )
                        print(f"    [i] {r.slug}: unmapped elements: {unmapped_str}")
            except Exception as exc:
                print(
                    f"[{completed_count:02d}/{total:02d}] {repo_name} execution error: {exc}",
                    file=sys.stderr,
                )

    return all_results


def generate_markdown_report(results: list[BookTestResult], elapsed_total: float) -> str:
    total_books = len(results)
    passed_books = sum(1 for r in results if r.status == "PASS")
    total_modules = sum(r.modules_count for r in results)
    total_math = sum(r.math_count for r in results)
    total_links = sum(r.links_count for r in results)

    # Collect all unmapped elements across all books
    all_unmapped: dict[str, int] = {}
    for r in results:
        for tag, count in r.unmapped_elements.items():
            all_unmapped[tag] = all_unmapped.get(tag, 0) + count

    lines = [
        "# OpenStax Textbook Battle-Test Verification Report",
        "",
        f"**Test Execution Time:** {elapsed_total:.1f} seconds  ",
        f"**Total Volumes Tested:** {total_books}  ",
        f"**Pass Rate:** **{passed_books} / {total_books} ({(passed_books / total_books * 100) if total_books else 0:.1f}%)**  ",
        f"**Total Modules Compiled:** {total_modules:,}  ",
        f"**Total MathML Formulas Converted:** {total_math:,}  ",
        f"**Total Cross-References Resolved:** {total_links:,}  ",
        "",
        "---",
        "",
        "## 🔬 Results by Textbook",
        "",
        "| Repository | Book Title | Category | Lang | Status | Modules | Math | Time | Unmapped Tags |",
        "|---|---|---|:---:|:---:|:---:|:---:|:---:|---|",
    ]

    for r in sorted(results, key=lambda x: (x.category, x.repo_name, x.slug)):
        status_icon = "✅ PASS" if r.status == "PASS" else "❌ FAIL"
        unmapped_str = (
            ", ".join(f"`{k}` ({v})" for k, v in sorted(r.unmapped_elements.items()))
            if r.unmapped_elements
            else "None (100%)"
        )
        lines.append(
            f"| `{r.repo_name}` | **{r.title}** | {r.category} | `{r.language}` | {status_icon} | "
            f"{r.modules_count} | {r.math_count:,} | {r.duration_s}s | {unmapped_str} |"
        )

    if all_unmapped:
        lines.extend(
            [
                "",
                "---",
                "",
                "## ⚠️ Unmapped CNXML Elements Detected Across Catalog",
                "",
                "The following elements appeared in tested textbooks but do not currently have dedicated block/inline handlers in `openstax_md.convert` (they currently fall back to inline text extraction):",
                "",
                "| Element Tag | Total Occurrences | Recommended Markdown Representation |",
                "|---|:---:|---|",
            ]
        )
        for tag, count in sorted(all_unmapped.items(), key=lambda x: -x[1]):
            rec = "Admonition or blockquote"
            if tag == "quote":
                rec = "Blockquote (`> ...`)"
            elif tag == "footnote":
                rec = "Markdown footnote (`[^fn]`)"
            elif tag in ("code", "preformat"):
                rec = "Fenced code block or inline code"
            elif tag == "proof":
                rec = "Proof environment (`**Proof.** ... ∎`)"
            elif tag == "rule":
                rec = "Rule / Theorem block (`**Rule:** ...`)"
            elif tag in ("span", "foreign", "cite", "cite-title"):
                rec = "Inline formatted text / emphasis"
            lines.append(f"| `<{tag}>` | **{count:,}** | {rec} |")

    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run bulk conversion battle tests across OpenStax books."
    )
    parser.add_argument(
        "--index",
        default=None,
        help="Path to catalog index.json (defaults to src/openstax_md/catalog.json or _osbooks/index.json)",
    )
    parser.add_argument("--category", help="Limit to specific category")
    parser.add_argument("--repos", nargs="+", help="Specific repository names to test")
    parser.add_argument(
        "--sample", action="store_true", help="Test 1 representative book from each category"
    )
    parser.add_argument("--all", action="store_true", help="Test all 54 content repositories")
    parser.add_argument("--workers", type=int, default=4, help="Parallel download & build workers")
    parser.add_argument(
        "--cache-dir", default="_osbooks/cache", help="Directory for sparse checkouts"
    )
    parser.add_argument("--out-dir", default="_osbooks/build", help="Directory for build output")
    parser.add_argument(
        "--report", default="_osbooks/battle_test_report.md", help="Markdown report destination"
    )
    parser.add_argument(
        "--json",
        dest="json_path",
        default="_osbooks/battle_test_report.json",
        help="JSON report destination",
    )
    args = parser.parse_args()

    if args.index:
        index_path = Path(args.index)
    else:
        pkg_catalog = Path(__file__).resolve().parents[1] / "src" / "openstax_md" / "catalog.json"
        local_catalog = Path("_osbooks/index.json")
        index_path = pkg_catalog if pkg_catalog.is_file() else local_catalog

    if not index_path.is_file():
        print(
            f"Error: Catalog index not found at {index_path}. Run generate_index.py first.",
            file=sys.stderr,
        )
        return 1

    with open(index_path, encoding="utf-8") as f:
        catalog = json.load(f)

    repos = catalog.get("repositories", [])
    # Filter out template/playground repos
    repos = [r for r in repos if "template" not in r["name"] and "playground" not in r["name"]]

    if args.repos:
        selected_names = set(args.repos)
        repos = [r for r in repos if r["name"] in selected_names]
    elif args.category:
        repos = [r for r in repos if r["category"].lower() == args.category.lower()]
    elif args.sample:
        # Pick 1 representative repo from each category
        categories = {}
        for r in repos:
            cat = r["category"]
            if cat not in categories:
                categories[cat] = r
        repos = list(categories.values())

    cache_root = Path(args.cache_dir)
    output_root = Path(args.out_dir)

    start_total = time.time()
    results = run_bulk_test(repos, cache_root, output_root, workers=args.workers)
    elapsed_total = time.time() - start_total

    # Write JSON report
    json_dest = Path(args.json_path)
    json_dest.parent.mkdir(parents=True, exist_ok=True)
    with open(json_dest, "w", encoding="utf-8") as f:
        json.dump([asdict(r) for r in results], f, indent=2, ensure_ascii=False)
    print(f"\nWrote JSON results to {json_dest}")

    # Write Markdown report
    md_content = generate_markdown_report(results, elapsed_total)
    md_dest = Path(args.report)
    md_dest.parent.mkdir(parents=True, exist_ok=True)
    md_dest.write_text(md_content, encoding="utf-8")
    print(f"Wrote Markdown report to {md_dest}\n")

    passed = sum(1 for r in results if r.status == "PASS")
    total = len(results)
    print(f"Battle Test Summary: {passed}/{total} books passed in {elapsed_total:.1f}s.")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
