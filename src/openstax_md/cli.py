"""Command line interface: ``openstax-md [COMMAND | INPUT ...]``.

Supports compiling local CNXML bundles/modules and Docker-style remote pulling
of OpenStax textbooks directly from the catalog.

Commands:
  pull        Pull a textbook repository into local cache
  search      Search the OpenStax catalog for textbooks
  list        List available textbooks in the catalog
  compile     Compile CNXML/COLLXML to Markdown (default action)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from . import __version__
from .book import Builder, Bundle, Report, find_bundle_root
from .catalog import list_catalog, pull, resolve_target, search_catalog
from .cnxml_bridge import CnxmlLib
from .convert import RenderOptions

#: sibling checkout of the ``cnxml`` library, used when it is not already on the path
REPO_ROOT_HINT = Path(__file__).resolve().parents[2] / "cnxml"


def build_parser() -> argparse.ArgumentParser:
    """Build parser for default compilation mode."""
    parser = argparse.ArgumentParser(
        prog="openstax-md",
        description=(
            "Compile OpenStax CNXML/COLLXML content to Markdown "
            "(MathML -> LaTeX, cross references resolved, collection aware). "
            "Transparently pulls remote textbooks if not found locally."
        ),
        epilog=(
            "Textbook discovery commands:\n"
            "  openstax-md pull <slug|repo|url>   Pull textbook into cache\n"
            "  openstax-md search <query>         Search catalog for textbooks\n"
            "  openstax-md list                   List catalog textbooks\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("-v", "--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument(
        "inputs",
        nargs="*",
        type=Path,
        help="bundle root, collection, module dir, index.cnxml, or catalog slug (e.g. astronomy-2e)",
    )
    parser.add_argument(
        "-o", "--out", type=Path, default=None, help="output directory (default: ./build/<name>)"
    )
    parser.add_argument(
        "--layout",
        choices=("mirror", "flat", "single"),
        default="mirror",
        help="mirror: out/modules/<id>/index.md; flat: out/<book>/<NN>-<title>.md; single: one file per book",
    )
    parser.add_argument(
        "--media",
        choices=("link", "copy", "original"),
        default="link",
        help="link: relative path into the source tree; copy: copy into <out>/media; original: keep src attribute",
    )
    parser.add_argument(
        "--anchors",
        choices=("referenced", "always", "none"),
        default="referenced",
        help="emit <a id> anchors for referenced elements only (default), all ids, or none",
    )
    parser.add_argument(
        "--math", choices=("dollar", "bracket", "none"), default="dollar", help="math delimiters"
    )
    parser.add_argument(
        "--admonitions",
        choices=("bold", "block", "heading"),
        default="bold",
        help="how examples/notes/solutions are labelled",
    )
    parser.add_argument("--no-front-matter", action="store_true", help="omit YAML front matter")
    parser.add_argument(
        "--collection",
        action="append",
        default=None,
        help="limit to this collection slug (repeatable)",
    )
    parser.add_argument(
        "--module", action="append", default=None, help="limit to this module id (repeatable)"
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="validate CNXML/COLLXML with the cnxml library (needs java)",
    )
    parser.add_argument(
        "--with-deps",
        action="store_true",
        help="also build modules referenced from the selection, so cross refs stay links",
    )
    parser.add_argument(
        "--strict", action="store_true", help="exit non-zero on warnings or validation errors"
    )
    parser.add_argument(
        "--report", type=Path, default=None, help="write a JSON build report to this path"
    )
    parser.add_argument(
        "-c",
        "--cache-dir",
        type=Path,
        default=None,
        help="custom cache directory for remote textbooks",
    )
    parser.add_argument("-q", "--quiet", action="store_true", help="only print the summary line")
    return parser


def _build_pull_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="openstax-md pull",
        description="Pull an OpenStax textbook repository into local cache using blobless sparse checkout.",
    )
    parser.add_argument(
        "target",
        help="Textbook slug (e.g. astronomy-2e), repository name, topic alias, or GitHub URL",
    )
    parser.add_argument("-c", "--cache-dir", type=Path, default=None, help="custom cache directory")
    parser.add_argument(
        "--media", action="store_true", help="include media/ asset directory in sparse checkout"
    )
    parser.add_argument(
        "-f", "--force", action="store_true", help="force re-clone even if already cached"
    )
    parser.add_argument("-q", "--quiet", action="store_true", help="suppress progress output")
    return parser


def _build_search_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="openstax-md search",
        description="Search OpenStax catalog for textbooks.",
    )
    parser.add_argument("query", help="search keyword (title, slug, topic, category)")
    parser.add_argument("--category", default=None, help="filter by academic discipline")
    parser.add_argument("--lang", default=None, help="filter by language code (en, es, pl)")
    parser.add_argument("--json", action="store_true", help="output results as JSON")
    return parser


def _build_list_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="openstax-md list",
        description="List available OpenStax textbooks in catalog.",
    )
    parser.add_argument("--category", default=None, help="filter by academic discipline")
    parser.add_argument("--lang", default=None, help="filter by language code (en, es, pl)")
    parser.add_argument("--json", action="store_true", help="output results as JSON")
    return parser


def _classify(path: Path) -> tuple[str, Path]:
    """Return ``(kind, root)`` where kind is bundle | collection | module."""
    path = path.resolve()
    if path.is_dir():
        if (path / "META-INF" / "books.xml").is_file() or (
            (path / "modules").is_dir() and (path / "collections").is_dir()
        ):
            return "bundle", path
        if (path / "index.cnxml").is_file():
            return "module", path
        raise SystemExit(f"error: {path} is not a CNXML bundle, collection or module directory")
    if path.suffix == ".xml" and path.name.endswith(".collection.xml"):
        return "collection", path
    if path.name == "index.cnxml" or path.suffix == ".cnxml":
        return "module", path
    raise SystemExit(f"error: cannot tell what {path} is")


def _print_catalog_table(results: list[dict[str, Any]]) -> None:
    """Format and print catalog entries as an aligned terminal table."""
    if not results:
        return
    cols = [
        ("slug", "SLUG", 24),
        ("repo", "REPO", 26),
        ("title", "TITLE", 30),
        ("language", "LANG", 5),
        ("category", "CATEGORY", 18),
    ]
    col_widths = []
    for key, header, min_w in cols:
        max_val_w = max((len(str(r.get(key, ""))) for r in results), default=0)
        w = max(min_w, min(max_val_w, 45 if key in ("title", "category") else 38))
        col_widths.append((key, header, w))

    header_line = "  ".join(h.ljust(w) for _, h, w in col_widths)
    sep_line = "  ".join("-" * w for _, _, w in col_widths)
    print(header_line)
    print(sep_line)
    for r in results:
        parts = []
        for k, _, w in col_widths:
            val = str(r.get(k, ""))
            if len(val) > w:
                val = val[: w - 1] + "…"
            parts.append(val.ljust(w))
        print("  ".join(parts))


def _run_pull(argv: list[str]) -> int:
    parser = _build_pull_parser()
    args = parser.parse_args(argv)
    try:
        repo_dir, col_slug = pull(
            args.target,
            cache_dir=args.cache_dir,
            include_media=args.media,
            quiet=args.quiet,
            force=args.force,
        )
        if not args.quiet:
            print(f"Ready: {repo_dir}")
            if col_slug:
                print(f"Collection: {col_slug}")
        return 0
    except (ValueError, RuntimeError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


def _run_search(argv: list[str]) -> int:
    parser = _build_search_parser()
    args = parser.parse_args(argv)
    results = search_catalog(args.query, category=args.category, lang=args.lang)
    if args.json:
        print(json.dumps(results, indent=2, ensure_ascii=False))
        return 0
    if not results:
        print(f"No textbooks found matching '{args.query}'")
        return 0
    _print_catalog_table(results)
    return 0


def _run_list(argv: list[str]) -> int:
    parser = _build_list_parser()
    args = parser.parse_args(argv)
    results = list_catalog(category=args.category, lang=args.lang)
    if args.json:
        print(json.dumps(results, indent=2, ensure_ascii=False))
        return 0
    _print_catalog_table(results)
    return 0


def _run_compile(argv: list[str]) -> int:
    args = build_parser().parse_args(argv)
    inputs = args.inputs or [Path.cwd()]

    reports: list[Report] = []
    for raw in inputs:
        target_collection: str | None = None
        if not raw.exists():
            resolved = resolve_target(str(raw))
            if resolved is None:
                raise SystemExit(
                    f"error: cannot tell what {raw} is (not found locally or in OpenStax catalog)"
                )
            include_media = args.media == "copy"
            repo_dir, col_slug = pull(
                str(raw),
                cache_dir=args.cache_dir,
                include_media=include_media,
                quiet=args.quiet,
            )
            raw = repo_dir
            target_collection = col_slug

        kind, root = _classify(raw)
        bundle_root = root if kind == "bundle" else find_bundle_root(root)
        lib = CnxmlLib.load([root, root.parent, REPO_ROOT_HINT])
        if bundle_root is not None:
            bundle = Bundle.discover(bundle_root, lib)
            default_name = target_collection or bundle.root.name
        elif kind == "module":
            bundle = Bundle.from_module(root, lib)
            default_name = next(iter(bundle.modules), "module")
        else:
            raise SystemExit(f"error: no CNXML bundle found for {root}")

        out_dir = args.out or (Path.cwd() / "build" / default_name)
        options = RenderOptions(
            math=args.math,
            anchors=args.anchors,
            admonitions=args.admonitions,
            media=args.media,
            front_matter=not args.no_front_matter,
        )
        builder = Builder(
            bundle,
            out_dir,
            options=options,
            layout=args.layout,
            single_file=args.layout == "single",
            validate=args.validate,
            with_deps=args.with_deps,
        )

        module_ids = args.module
        collection_slugs = args.collection
        if target_collection and collection_slugs is None:
            collection_slugs = [target_collection]

        if kind == "module" and module_ids is None:
            requested = root.parent.name if root.is_file() else root.name
            module_ids = [requested] if requested in bundle.modules else list(bundle.modules)
        elif kind == "collection":
            slugs = [c.slug for c in bundle.collections if c.source == Path(root)]
            collection_slugs = sorted(set((collection_slugs or []) + slugs))

        report = builder.build(module_ids=module_ids, collection_slugs=collection_slugs)
        reports.append(report)
        _print_report(report, out_dir, quiet=args.quiet)

    if args.report and reports:
        merged = reports[0] if len(reports) == 1 else _merge(reports)
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(
            json.dumps(merged.to_dict(), indent=2, sort_keys=True), encoding="utf-8"
        )

    if args.strict:
        for report in reports:
            if report.warnings or report.validation_errors or report.missing_media:
                return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    args_list = sys.argv[1:] if argv is None else list(argv)

    if args_list and args_list[0] in ("-v", "--version"):
        print(f"openstax-md {__version__}")
        return 0

    if args_list and args_list[0] == "pull":
        return _run_pull(args_list[1:])
    if args_list and args_list[0] == "search":
        return _run_search(args_list[1:])
    if args_list and args_list[0] == "list":
        return _run_list(args_list[1:])
    if args_list and args_list[0] == "compile":
        args_list = args_list[1:]

    return _run_compile(args_list)


def _merge(reports: list[Report]) -> Report:
    merged = Report()
    for report in reports:
        merged.modules += report.modules
        merged.words += report.words
        merged.outputs.extend(report.outputs)
        merged.stats.update(report.stats)
        merged.unhandled.update(report.unhandled)
        merged.missing_media.extend(report.missing_media)
        merged.validation_errors.extend(report.validation_errors)
        merged.warnings.extend(report.warnings)
    return merged


def _print_report(report: Report, out_dir: Path, quiet: bool = False) -> None:
    stats = report.stats
    print(
        f"openstax-md: {report.modules} modules, {len(report.outputs)} files, "
        f"{stats.get('math', 0) + stats.get('equations', 0)} math expressions, "
        f"{stats.get('links_resolved', 0)} links resolved, "
        f"{stats.get('media_linked', 0) + stats.get('media_copied', 0)} images -> {out_dir}"
    )
    if report.unhandled:
        top = ", ".join(f"{name}({count})" for name, count in report.unhandled.most_common(8))
        print(f"  unmapped elements: {top}")
    if report.missing_media:
        print(f"  missing media: {len(report.missing_media)}")
    if report.validation_errors:
        print(f"  validation errors: {len(report.validation_errors)}")
    if report.validation_skipped:
        print(f"  validation skipped: {report.validation_skipped}")
    if report.warnings and not quiet:
        limit = 10
        for warning in report.warnings[:limit]:
            print(f"  warning: {warning}")
        if len(report.warnings) > limit:
            print(f"  ... {len(report.warnings) - limit} more warnings")


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
