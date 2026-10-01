"""Bundle/collection discovery, output layout and the build driver."""

from __future__ import annotations

import os
import re
import shutil
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from pathlib import Path
from urllib.parse import quote

from lxml import etree

from .cnxml_bridge import CnxmlLib
from .convert import (
    ModuleInfo,
    ModuleRenderer,
    RenderOptions,
    Target,
    localname,
    target_label,
)

CONTAINER_NS = "https://openstax.org/namespaces/book-container"

#: element kinds that OpenStax numbers, and how the label reads
_NUMBERED_KINDS = {
    "figure": "Figure",
    "table": "Table",
    "example": "Example",
    "checkpoint": "Checkpoint",
    "equation": "Equation",
}

_HEADING_RE = re.compile(r"^(#{1,6})(\s)", re.MULTILINE)
_SLUG_RE = re.compile(r"[^a-z0-9]+")


def demote_headings(text: str, levels: int = 1) -> str:
    """Push every ATX heading down ``levels`` steps (max h6)."""

    def repl(match: re.Match) -> str:
        hashes = "#" * min(6, len(match.group(1)) + levels)
        return hashes + str(match.group(2))

    return _HEADING_RE.sub(repl, text)


def slugify(text: str, fallback: str = "section") -> str:
    slug = _SLUG_RE.sub("-", (text or "").lower()).strip("-")
    return slug or fallback


@dataclass
class Numbering:
    """Generated labels (``Example 1.1``, ``Figure 1.2``, ``Table 1.1``, ``(1.1)``).

    OpenStax ships empty ``<label/>`` elements: their pipeline generates the
    numbers. Counters are chapter-scoped and run across the chapter's sections in
    collection order (verified against the published pages -- see
    ``scripts/compare_with_openstax.py``).
    """

    labels: dict[str, dict[str, dict[str, str]]] = field(
        default_factory=dict
    )  # collection -> module -> id -> label
    objectives: dict[str, dict[str, list[str]]] = field(default_factory=dict)
    sections: dict[str, dict[str, str]] = field(default_factory=dict)  # module id -> "1.1"
    fallback: dict[str, str] = field(default_factory=dict)

    def label(
        self,
        element_id: str | None,
        collection_slug: str | None = None,
        module_id: str | None = None,
    ) -> str:
        """Label for an element; module-scoped first (ids repeat across modules)."""
        if not element_id:
            return ""
        if collection_slug and module_id:
            module_map = self.labels.get(collection_slug, {}).get(module_id)
            if module_map is not None:
                # authoritative for this module: an element that is deliberately
                # unnumbered there must not inherit the label of a same-id element
                # in another module
                return module_map.get(element_id, "")
        return self.fallback.get(element_id, "")

    def objective_labels(self, module_id: str, collection_slug: str | None = None) -> list[str]:
        if collection_slug:
            found = self.objectives.get(collection_slug, {}).get(module_id)
            if found:
                return found
        for per_module in self.objectives.values():
            if module_id in per_module:
                return per_module[module_id]
        return []

    def section_number(self, module_id: str, collection_slug: str | None = None) -> str:
        if collection_slug:
            found = self.sections.get(collection_slug, {}).get(module_id)
            if found:
                return found
        for per_module in self.sections.values():
            if module_id in per_module:
                return per_module[module_id]
        return ""


@dataclass
class Entry:
    """A module reference inside a collection."""

    module_id: str
    sections: list[str] = field(default_factory=list)

    @property
    def section_path(self) -> str:
        return " / ".join(self.sections)


@dataclass
class CollectionInfo:
    slug: str
    source: Path
    title: str
    entries: list[Entry] = field(default_factory=list)

    @property
    def module_ids(self) -> list[str]:
        return [entry.module_id for entry in self.entries]


class Bundle:
    """An OpenStax bundle checkout (``META-INF/books.xml`` + collections + modules)."""

    def __init__(self, root: Path, lib: CnxmlLib | None = None) -> None:
        self.root = Path(root).resolve()
        self.lib = lib or CnxmlLib.load([self.root])
        self.modules: dict[str, ModuleInfo] = {}
        self.collections: list[CollectionInfo] = []
        self.media_root = self.root / "media"
        self.book_titles: dict[str, str] = {}
        self.referenced_ids: set[str] = set()
        self.targets: dict[str, Target] = {}
        self.targets_by_module: dict[str, dict[str, Target]] = {}
        self.numbering = Numbering()
        self._loaded = False

    # -- discovery ---------------------------------------------------------

    @classmethod
    def discover(cls, root: Path, lib: CnxmlLib | None = None) -> Bundle:
        bundle = cls(root, lib)
        bundle._discover_collections()
        bundle.load_modules()
        bundle.build_index()
        return bundle

    @classmethod
    def from_module(cls, path: Path, lib: CnxmlLib | None = None) -> Bundle:
        """Wrap a single CNXML file (no collection context)."""
        path = path.resolve()
        source = path if path.is_file() else path / "index.cnxml"
        root = (
            source.parent.parent.parent if source.parent.parent.name == "modules" else source.parent
        )
        bundle = cls(root, lib)
        module = ModuleInfo(id=source.parent.name, source=source)
        module.metadata = _safe_metadata(bundle.lib, source)
        bundle.modules[module.id] = module
        bundle.load_modules()
        bundle.build_index()
        return bundle

    def _discover_collections(self) -> None:
        container = self.root / "META-INF" / "books.xml"
        collection_paths: list[Path] = []
        if container.is_file():
            tree = etree.parse(str(container))
            for book in tree.getroot():
                if localname(book) != "book":
                    continue
                slug = book.get("slug") or ""
                href = book.get("href")
                if slug:
                    self.book_titles[slug] = slug
                if href:
                    candidate = (container.parent.parent / href).resolve()
                    if candidate.is_file():
                        collection_paths.append(candidate)
        if not collection_paths:
            collections_dir = self.root / "collections"
            if collections_dir.is_dir():
                collection_paths = sorted(collections_dir.glob("*.collection.xml"))
        for path in collection_paths:
            self.collections.append(self._parse_collection(path))
        for collection in self.collections:
            self.book_titles[collection.slug] = collection.title

    def _parse_collection(self, path: Path) -> CollectionInfo:
        tree = etree.parse(str(path))
        root = tree.getroot()
        title = ""
        for el in root.iter():
            if localname(el) == "title" and el.text and el.text.strip():
                title = el.text.strip()
                break
        slug = ""
        for el in root.iter():
            if localname(el) == "slug" and el.text and el.text.strip():
                slug = el.text.strip()
                break
        if not slug:
            slug = path.name.replace(".collection.xml", "")
        entries: list[Entry] = []
        content = None
        for el in root.iter():
            if localname(el) == "content":
                content = el
                break
        if content is not None:
            self._walk_collection(content, [], entries)
        return CollectionInfo(slug=slug, source=path, title=title or slug, entries=entries)

    def _walk_collection(self, node, sections: list[str], entries: list[Entry]) -> None:
        for child in node:
            name = localname(child)
            if name == "module":
                module_id = child.get("document") or child.get("id") or ""
                if module_id:
                    entries.append(Entry(module_id=module_id, sections=list(sections)))
            elif name == "subcollection":
                title = ""
                for sub in child:
                    if localname(sub) == "title":
                        title = " ".join("".join(sub.itertext()).split())
                        break
                nested = sections + ([title] if title else [])
                for sub in child:
                    if localname(sub) == "content":
                        self._walk_collection(sub, nested, entries)

    # -- modules -----------------------------------------------------------

    def load_modules(self) -> None:
        if self._loaded:
            return
        modules_dir = self.root / "modules"
        if modules_dir.is_dir():
            for path in sorted(modules_dir.glob("*/index.cnxml")):
                module_id = path.parent.name
                if module_id in self.modules:
                    continue
                module = ModuleInfo(id=module_id, source=path.resolve())
                module.metadata = _safe_metadata(self.lib, module.source)
                self.modules[module_id] = module
        self._loaded = True

    # -- index -------------------------------------------------------------

    def build_index(self) -> None:
        """Collect cross-reference targets: element id -> label."""
        link_ids: set[str] = set()
        trees: dict[str, etree._Element] = {}
        for module in self.modules.values():
            try:
                with open(module.source, "rb") as fh:
                    root = etree.parse(fh).getroot()
            except Exception:  # pragma: no cover - malformed input
                continue
            trees[module.id] = root
            for el in root.iter():
                if localname(el) == "link":
                    target_id = el.get("target-id")
                    if target_id:
                        link_ids.add(target_id)
        self.referenced_ids = link_ids
        self.numbering = self._build_numbering()
        for module_id, root in trees.items():
            collection = self.collection_of(module_id)
            slug = collection.slug if collection else None
            module_targets: dict[str, Target] = {}
            for el in root.iter():
                element_id = el.get("id")
                if not element_id or element_id not in link_ids:
                    continue
                target = target_label(
                    el,
                    module_id,
                    number=self.numbering.label(element_id, slug, module_id),
                )
                module_targets[element_id] = target
                # global map: first module wins (used for same-module lookups)
                self.targets.setdefault(element_id, target)
            self.targets_by_module[module_id] = module_targets

    def _build_numbering(self) -> Numbering:
        plan = Numbering()
        for collection in self.collections:
            counters: dict[int, Counter] = {}
            chapter_of: dict[str, int] = {}
            section_counters: Counter = Counter()
            chapter_number = 0
            per_element: dict[str, dict[str, str]] = {}
            per_objectives: dict[str, list[str]] = {}
            per_sections: dict[str, str] = {}
            for entry in collection.entries:
                module = self.modules.get(entry.module_id)
                if module is None:
                    continue
                key = entry.sections[0] if entry.sections else ""
                if not key:
                    chapter = 0
                    section = 0
                else:
                    if key not in chapter_of:
                        chapter_number += 1
                        chapter_of[key] = chapter_number
                    chapter = chapter_of[key]
                try:
                    with open(module.source, "rb") as fh:
                        root = etree.parse(fh).getroot()
                except Exception:  # pragma: no cover - malformed input
                    continue
                opener = "introduction" in (root.get("class") or "")
                if not chapter:
                    section = 0
                elif opener:
                    # the chapter opener is the first module of a chapter but is not
                    # a numbered section (published pages: /1-introduction vs /1-1-…)
                    section = 0
                else:
                    section_counters[chapter] += 1
                    section = section_counters[chapter]
                if chapter and section:
                    per_sections[module.id] = f"{chapter}.{section}"
                chapter_counters = counters.setdefault(chapter, Counter())
                for el in root.iter():
                    kind = _numbered_kind(el)
                    if kind is None:
                        continue
                    chapter_counters[kind] += 1
                    if not chapter or not section:
                        continue
                    number = f"{chapter}.{chapter_counters[kind]}"
                    label = (
                        f"({number})" if kind == "equation" else f"{_NUMBERED_KINDS[kind]} {number}"
                    )
                    element_id = el.get("id")
                    if element_id:
                        per_element.setdefault(module.id, {})[element_id] = label
                        plan.fallback.setdefault(element_id, label)
                per_objectives[module.id] = self._objective_labels(root, chapter, section)
            plan.labels[collection.slug] = per_element
            plan.objectives[collection.slug] = per_objectives
            plan.sections[collection.slug] = per_sections
        return plan

    @staticmethod
    def _objective_labels(root, chapter: int, section: int) -> list[str]:
        if not chapter or not section:
            return []
        abstract = None
        for el in root.iter():
            if localname(el) == "abstract":
                abstract = el
                break
        if abstract is None:
            return []
        items = [el for el in abstract.iter() if localname(el) == "item"]
        return [f"{chapter}.{section}.{index + 1}" for index in range(len(items))]

    def lookup_target(self, module_id: str | None, target_id: str | None) -> Target | None:
        """Resolve a target id, preferring the module that owns the reference."""
        if target_id is None:
            return None
        if module_id:
            found = self.targets_by_module.get(module_id, {}).get(target_id)
            if found is not None:
                return found
        return self.targets.get(target_id)

    # -- helpers -----------------------------------------------------------

    def collection_of(self, module_id: str) -> CollectionInfo | None:
        for collection in self.collections:
            if module_id in collection.module_ids:
                return collection
        return None

    def order_in_collection(self, module_id: str) -> int:
        collection = self.collection_of(module_id)
        if collection is None:
            return 0
        return collection.module_ids.index(module_id)


def _numbered_kind(el) -> str | None:
    """Which OpenStax counter (if any) an element increments.

    Verified against the published pages: tables marked ``class="unnumbered"``
    are skipped entirely (they neither consume a number nor show one), while
    ``class="column-header"`` data tables *do* take a number. Figures are always
    numbered (chapter openers use ``class="splash"`` and are numbered too).
    """
    name = localname(el)
    if name in ("figure", "example"):
        return name
    if name == "table":
        return None if "unnumbered" in (el.get("class") or "") else "table"
    if name == "equation":
        return None if "unnumbered" in (el.get("class") or "") else "equation"
    if name == "note" and (el.get("class") or "") == "checkpoint":
        return "checkpoint"
    return None


def _safe_metadata(lib: CnxmlLib, path: Path) -> dict:
    try:
        return lib.parse_metadata(path)
    except Exception:  # pragma: no cover - malformed input
        return {}


def _referenced_modules(source: Path) -> set[str]:
    """Module ids referenced by ``<link document="..."/>`` in a CNXML file."""
    try:
        with open(source, "rb") as fh:
            root = etree.parse(fh).getroot()
    except Exception:  # pragma: no cover - malformed input
        return set()
    referenced: set[str] = set()
    for el in root.iter():
        if localname(el) == "link":
            document = el.get("document")
            if document:
                referenced.add(document)
    return referenced


class BuildContext:
    """Everything the renderer needs to know about the surrounding build."""

    def __init__(self, builder: Builder, module: ModuleInfo, out_path: Path) -> None:
        self.builder = builder
        self.bundle = builder.bundle
        self.options: RenderOptions = builder.options
        self.module = module
        self.module_id = module.id
        self.out_path = out_path
        self.bundle_root = builder.bundle.root
        self.referenced_ids = builder.referenced_ids
        self.targets = builder.targets
        self.targets_by_module = builder.targets_by_module
        self.numbering = builder.numbering
        self.module_titles = builder.module_titles
        collection = builder.bundle.collection_of(module.id)
        self.book_slug = collection.slug if collection else None
        self.book_title = collection.title if collection else None

    # -- stats -------------------------------------------------------------

    def stat(self, key: str, amount: int = 1) -> None:
        self.builder.stats[key] += amount

    def warn(self, message: str) -> None:
        self.builder.warn(message)

    def count_unhandled(self, name: str) -> None:
        self.builder.unhandled[name] += 1

    # -- numbering ---------------------------------------------------------

    def number(self, element_id: str | None) -> str:
        """Generated label for an element (``Figure 1.2``, ``Example 1.1``)."""
        return self.numbering.label(element_id, self.book_slug, self.module_id)

    def objective_numbers(self) -> list[str]:
        return self.numbering.objective_labels(self.module_id, self.book_slug)

    # -- links -------------------------------------------------------------

    def lookup_target(self, module_id: str | None, target_id: str | None) -> Target | None:
        return self.bundle.lookup_target(module_id, target_id)

    def media_href(self, module: ModuleInfo, src: str) -> str:
        return self.builder.media_href(module, self.out_path, src)

    def module_href(self, from_id: str, to_id: str, target_id: str | None) -> str | None:
        from_path = self.builder.out_path_for(from_id)
        to_path = self.builder.out_path_for(to_id)
        if from_path is None or to_path is None:
            return None
        fragment = f"#{target_id}" if target_id else ""
        if to_path == from_path:
            return fragment or None
        rel = os.path.relpath(to_path, from_path.parent).replace(os.sep, "/")
        return quote(rel, safe="/:") + fragment


@dataclass
class Report:
    modules: int = 0
    outputs: list[str] = field(default_factory=list)
    stats: Counter = field(default_factory=Counter)
    words: int = 0
    warnings: list[str] = field(default_factory=list)
    unhandled: Counter = field(default_factory=Counter)
    missing_media: list[str] = field(default_factory=list)
    validation_errors: list[str] = field(default_factory=list)
    validation_skipped: str = ""

    def to_dict(self) -> dict:
        return {
            "modules": self.modules,
            "outputs": self.outputs,
            "words": self.words,
            "stats": dict(self.stats),
            "unhandled_elements": dict(self.unhandled),
            "missing_media": self.missing_media,
            "warnings": self.warnings,
            "validation_errors": self.validation_errors,
            "validation_skipped": self.validation_skipped,
        }


class Builder:
    """Drives rendering of a bundle, a collection or a single module."""

    def __init__(
        self,
        bundle: Bundle,
        out_dir: Path,
        options: RenderOptions | None = None,
        layout: str = "mirror",
        media_mode: str | None = None,
        single_file: bool = False,
        validate: bool = False,
        with_deps: bool = False,
    ) -> None:
        self.bundle = bundle
        self.out_dir = Path(out_dir).resolve()
        self.options = options or RenderOptions()
        if media_mode:
            self.options.media = media_mode
        self.layout = layout
        self.single_file = single_file or layout == "single"
        self.validate = validate
        self.with_deps = with_deps
        self.report = Report()
        self.stats = self.report.stats
        self.warnings = self.report.warnings
        self.unhandled = self.report.unhandled
        self.referenced_ids = bundle.referenced_ids
        self.targets = bundle.targets
        self.targets_by_module = bundle.targets_by_module
        self.numbering = bundle.numbering
        self.module_titles = {mid: m.title for mid, m in bundle.modules.items()}
        self._out_paths: dict[str, Path] = {}
        self._media_copy: dict[str, Path] = {}
        self._missing_media: set[str] = set()
        self._warned: set[str] = set()
        self._preferred_collection: dict[str, str] = {}
        self._selection: list[str] | None = None
        self._indexed_collections: list[CollectionInfo] = []
        self._compute_out_paths()

    # -- paths -------------------------------------------------------------

    def _compute_out_paths(
        self,
        collection_order: list[str] | None = None,
        module_ids: Iterable[str] | None = None,
    ) -> None:
        """Assign output paths to the modules included in this build.

        Modules can belong to several books (e.g. a shared "Table of
        Derivatives" page); the first collection in the build order wins.
        Modules outside the build get no path, so links to them are rendered as
        plain text instead of dangling links.
        """
        order = (
            collection_order
            if collection_order is not None
            else [collection.slug for collection in self.bundle.collections]
        )
        self._preferred_collection = {}
        by_slug = {collection.slug: collection for collection in self.bundle.collections}
        for slug in order:
            collection = by_slug.get(slug)
            if collection is None:
                continue
            for module_id in collection.module_ids:
                self._preferred_collection.setdefault(module_id, slug)
        selected = list(module_ids) if module_ids is not None else list(self.bundle.modules)
        self._out_paths = {}
        for module_id in selected:
            if module_id in self.bundle.modules:
                self._out_paths[module_id] = self._default_out_path(module_id)

    @property
    def _selected_collection_slugs(self) -> list[str]:
        if self._selection is None:
            return [collection.slug for collection in self.bundle.collections]
        return list(self._selection)

    def _module_collection_slug(self, module_id: str) -> str | None:
        return self._preferred_collection.get(module_id)

    def _default_out_path(self, module_id: str) -> Path:
        module = self.bundle.modules[module_id]
        slug = self._module_collection_slug(module_id)
        if self.single_file:
            return self.out_dir / f"{slug or 'standalone'}.md"
        if self.layout == "flat" and slug:
            collection = next((c for c in self.bundle.collections if c.slug == slug), None)
            index = collection.module_ids.index(module_id) + 1 if collection else 0
            name = f"{index:02d}-{slugify(module.title)}.md"
            return self.out_dir / slug / name
        return self.out_dir / "modules" / module_id / "index.md"

    def out_path_for(self, module_id: str) -> Path | None:
        return self._out_paths.get(module_id)

    def warn(self, message: str) -> None:
        if message not in self._warned:
            self._warned.add(message)
            self.warnings.append(message)

    # -- media -------------------------------------------------------------

    def media_href(self, module: ModuleInfo, out_path: Path, src: str) -> str:
        src = (src or "").strip()
        if not src:
            return ""
        if re.match(r"^[a-z]+:", src, re.IGNORECASE):
            return src
        source_path = (module.source.parent / src).resolve()
        if not source_path.exists():
            key = str(source_path)
            if key not in self._missing_media:
                self._missing_media.add(key)
                self.report.missing_media.append(f"{module.id}: {src}")
                self.warn(f"{module.id}: missing media file {src}")
        mode = self.options.media
        if mode == "original":
            return src
        if mode == "copy" and source_path.exists():
            dest = self._copy_media(source_path)
            self.stats["media_copied"] += 1
            href = os.path.relpath(dest, out_path.parent).replace(os.sep, "/")
            return quote(href, safe="/:")
        href = os.path.relpath(source_path, out_path.parent).replace(os.sep, "/")
        self.stats["media_linked"] += 1
        return quote(href, safe="/:")

    def _copy_media(self, source: Path) -> Path:
        key = str(source)
        if key in self._media_copy:
            return self._media_copy[key]
        dest_dir = self.out_dir / "media"
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / source.name
        if dest.exists() and dest.stat().st_size != source.stat().st_size:
            stem, suffix = source.stem, source.suffix
            counter = 2
            while dest.exists():
                dest = dest_dir / f"{stem}-{counter}{suffix}"
                counter += 1
        if not dest.exists():
            shutil.copy2(source, dest)
        self._media_copy[key] = dest
        return dest

    # -- rendering ---------------------------------------------------------

    def render_module(self, module: ModuleInfo, front_matter: bool | None = None) -> str:
        out_path = self.out_path_for(module.id) or (self.out_dir / f"{module.id}.md")
        ctx = BuildContext(self, module, out_path)
        if front_matter is not None and front_matter != self.options.front_matter:
            ctx.options = replace(self.options, front_matter=front_matter)
        return ModuleRenderer(module, ctx).render()

    def build(
        self,
        module_ids: Iterable[str] | None = None,
        collection_slugs: Iterable[str] | None = None,
    ) -> Report:
        ids = list(module_ids) if module_ids is not None else None
        self._selection = list(collection_slugs) if collection_slugs is not None else None
        if ids is None and collection_slugs is not None:
            wanted = set(collection_slugs)
            ids = [
                mid
                for collection in self.bundle.collections
                if collection.slug in wanted
                for mid in collection.module_ids
            ]
        if ids is None:
            ids = list(self.bundle.modules)
        # keep build order, drop duplicates (modules shared between books)
        ids = list(dict.fromkeys(ids))
        if self.with_deps:
            ids = self._expand_dependencies(ids)
        self._compute_out_paths(self._selected_collection_slugs, ids)

        if self.validate:
            self._validate(ids)

        if self.single_file:
            self._build_single_file(ids)
        else:
            self._build_modules(ids)
        self._write_root_index()
        self.report.modules = len(ids)
        return self.report

    def _build_modules(self, ids: list[str]) -> None:
        for module_id in ids:
            module = self.bundle.modules.get(module_id)
            if module is None:
                self.warn(f"module {module_id} referenced but not found on disk")
                continue
            text = self.render_module(module)
            out_path = self.out_path_for(module_id)
            if out_path is not None:
                self._write(out_path, text)
        for collection in self._collections_to_index(ids):
            self._write(self._collection_index_path(collection), self._collection_index(collection))
            self._indexed_collections.append(collection)

    def _collections_to_index(self, ids: list[str]) -> list[CollectionInfo]:
        built = set(ids)
        if self._selection is not None and not self.with_deps:
            wanted = set(self._selection)
            return [
                c
                for c in self.bundle.collections
                if c.slug in wanted and any(m in built for m in c.module_ids)
            ]
        return [c for c in self.bundle.collections if any(m in built for m in c.module_ids)]

    def _expand_dependencies(self, ids: list[str]) -> list[str]:
        """Pull in every module referenced by the selected modules (transitively).

        Without this, cross references that leave a partial build can only be
        rendered as plain text.
        """
        selected = set(ids)
        queue = list(ids)
        while queue:
            module_id = queue.pop()
            module = self.bundle.modules.get(module_id)
            if module is None:
                continue
            for dependency in _referenced_modules(module.source):
                if dependency in self.bundle.modules and dependency not in selected:
                    selected.add(dependency)
                    queue.append(dependency)
        # keep the bundle's stable order, requested modules first
        ordered = [mid for mid in ids if mid in selected]
        ordered.extend(
            mid for mid in self.bundle.modules if mid in selected and mid not in set(ids)
        )
        return ordered

    def _build_single_file(self, ids: list[str]) -> None:
        grouped: dict[str, list[str]] = {}
        for module_id in ids:
            slug = self._module_collection_slug(module_id) or "standalone"
            grouped.setdefault(slug, []).append(module_id)
        for slug, module_ids in grouped.items():
            collection = next((c for c in self.bundle.collections if c.slug == slug), None)
            title = collection.title if collection else slug.replace("-", " ").title()
            parts = [
                self._book_front_matter(collection, module_ids),
                f"# {title}",
                self._toc(module_ids, link_targets=False),
            ]
            for module_id in module_ids:
                module = self.bundle.modules.get(module_id)
                if module is None:
                    continue
                body = self.render_module(module, front_matter=False)
                parts.append(demote_headings(body, 1))
            self._write(self.out_dir / f"{slug}.md", "\n\n".join(part for part in parts if part))
            if collection is not None:
                self._indexed_collections.append(collection)

    # -- collection scaffolding -------------------------------------------

    def _collection_index_path(self, collection: CollectionInfo) -> Path:
        if self.layout == "flat":
            return self.out_dir / collection.slug / "index.md"
        return self.out_dir / "collections" / f"{collection.slug}.md"

    def _collection_index(self, collection: CollectionInfo) -> str:
        parts = [
            self._book_front_matter(collection, collection.module_ids),
            f"# {collection.title}",
        ]
        same_dir = self.layout == "flat"
        base = self._collection_index_path(collection).parent
        parts.append(self._toc(collection.module_ids, link_targets=not same_dir, base=base))
        return "\n\n".join(part for part in parts if part)

    def _toc(
        self,
        module_ids: list[str],
        link_targets: bool = True,
        base: Path | None = None,
    ) -> str:
        base = base or self.out_dir
        lines = ["## Contents", ""]
        last_section = None
        for module_id in module_ids:
            module = self.bundle.modules.get(module_id)
            if module is None:
                continue
            slug = self._module_collection_slug(module_id)
            collection = next((c for c in self.bundle.collections if c.slug == slug), None)
            entry = None
            if collection is not None:
                entry = next((e for e in collection.entries if e.module_id == module_id), None)
            if entry is not None and entry.section_path and entry.section_path != last_section:
                lines.append(f"**{entry.section_path}**")
                lines.append("")
                last_section = entry.section_path
            target = self.out_path_for(module_id)
            if link_targets and target is not None:
                href = os.path.relpath(target, base).replace(os.sep, "/")
                lines.append(f"- [{module.title}]({quote(href, safe='/:')})")
            else:
                lines.append(f"- {module.title}")
        return "\n".join(lines)

    def _book_front_matter(self, collection: CollectionInfo | None, module_ids: list[str]) -> str:
        if collection is None:
            return ""
        meta = _safe_metadata(self.bundle.lib, collection.source)
        rows = [
            ("title", collection.title),
            ("book_slug", collection.slug),
            ("modules", str(len(module_ids))),
            ("language", meta.get("language")),
            ("license", meta.get("license_text")),
            ("license_url", meta.get("license_url")),
            ("collection_source", str(collection.source.relative_to(self.bundle.root))),
            ("generator", "cnxml2md (python)"),
        ]
        lines = ["---"]
        for key, value in rows:
            if value in (None, ""):
                continue
            text = str(value).replace("\\", "\\\\").replace('"', '\\"')
            lines.append(f'{key}: "{text}"')
        lines.append("---")
        return "\n".join(lines)

    def _write_root_index(self) -> None:
        if not self.bundle.collections:
            return
        collections = self._indexed_collections or self.bundle.collections
        lines = ["# Compiled OpenStax bundle", "", "## Books", ""]
        for collection in collections:
            path = (
                self.out_dir / f"{collection.slug}.md"
                if self.single_file
                else self._collection_index_path(collection)
            )
            href = os.path.relpath(path, self.out_dir).replace(os.sep, "/")
            lines.append(
                f"- [{collection.title}]({quote(href, safe='/:')}) — {len(collection.entries)} modules"
            )
        self._write(self.out_dir / "index.md", "\n".join(lines))

    # -- validation --------------------------------------------------------

    def _validate(self, ids: list[str]) -> None:
        lib = self.bundle.lib
        if not lib.validation_available:
            self.report.validation_skipped = lib.reason or "validation unavailable"
            self.warn(f"skipping validation: {self.report.validation_skipped}")
            return
        for module_id in ids:
            module = self.bundle.modules.get(module_id)
            if module is None:
                continue
            for error in lib.validate_cnxml(module.source):
                self.report.validation_errors.append(
                    f"{module.source.name}:{error.line}:{error.column} {error.type}: {error.message}"
                )
        for collection in self.bundle.collections:
            for error in lib.validate_collxml(collection.source):
                self.report.validation_errors.append(
                    f"{collection.source.name}:{error.line}:{error.column} {error.type}: {error.message}"
                )

    # -- io ----------------------------------------------------------------

    def _write(self, path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text.rstrip("\n") + "\n", encoding="utf-8")
        self.report.words += len(text.split())
        relative = os.path.relpath(path, self.out_dir).replace(os.sep, "/")
        self.report.outputs.append(relative)


def find_bundle_root(path: Path) -> Path | None:
    """Walk up from ``path`` looking for a bundle root."""
    path = path.resolve()
    candidates: list[Path] = []
    if path.is_file():
        candidates.append(path.parent)
    candidates.append(path)
    for candidate in candidates:
        for directory in [candidate, *candidate.parents]:
            if (directory / "META-INF" / "books.xml").is_file():
                return directory
            if (directory / "modules").is_dir() and (directory / "collections").is_dir():
                return directory
    return None
