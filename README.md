# cnxml2md (python)

Compile [OpenStax](https://openstax.org/) textbook **CNXML/COLLXML** bundles into
**Markdown**.

Planned layout:

```text
src/cnxml2md/
  mathml.py        MathML -> LaTeX
  convert.py       CNXML -> Markdown (blocks, inline, admonitions, refs, media)
  book.py          bundle/collection discovery, index, layouts, build driver
  cnxml_bridge.py  import the upstream cnxml library (with fallbacks)
  cli.py           cnxml2md command line
tests/             unit tests + bundle integration tests
```

The conversion consumes the upstream checkouts pinned in
[`docs/sources.md`](docs/sources.md): `osbooks-calculus-bundle/` is the content,
`cnxml/` supplies the namespaces, schemas and metadata parser, and the original
JavaScript `cnxml2md/` is kept as the behavioural baseline.

## Environment

Managed with [uv](https://docs.astral.sh/uv/). Python >= 3.10, `lxml`, and
`setuptools<81` (the upstream `cnxml` library still imports `pkg_resources`,
which was removed in setuptools 81):

```bash
uv sync
```

## Usage

```bash
# whole bundle (all three calculus volumes), mirroring the source layout
uv run cnxml2md osbooks-calculus-bundle -o build/calculus

# one book, vault-friendly flat layout with copied media
uv run cnxml2md osbooks-calculus-bundle --collection calculus-volume-1 \
    --layout flat --media copy -o vault/calculus

# one book as a single markdown file
uv run cnxml2md osbooks-calculus-bundle --layout single -o build/books

# one module, with schema validation + JSON report
uv run cnxml2md osbooks-calculus-bundle/modules/m53477 --validate \
    --report build/report.json -o build/one
```

Inputs may be a bundle root, a `*.collection.xml`, a module directory, or an
`index.cnxml` file.

| Flag | Values | Default | Meaning |
|---|---|---|---|
| `-o/--out` | path | `build/<name>` | output directory |
| `--layout` | `mirror`, `flat`, `single` | `mirror` | `mirror` = `modules/<id>/index.md`; `flat` = `out/<book>/<NN>-<title>.md`; `single` = one file per book |
| `--media` | `link`, `copy`, `original` | `link` | relative link into the source tree, copy into `out/media/`, or keep `src` verbatim |
| `--anchors` | `referenced`, `always`, `none` | `referenced` | emit `<a id="…">` only for link targets, for every id, or never |
| `--math` | `dollar`, `bracket`, `none` | `dollar` | `$…$`/`$$…$$`, `\(…\)`/`\[…\]`, or plain LaTeX |
| `--admonitions` | `bold`, `block`, `heading` | `bold` | label style for examples/notes/solutions |
| `--collection`, `--module` | id/slug | – | limit the build (add `--with-deps` to also build referenced modules) |
| `--validate` | flag | off | run `jing.jar` CNXML/COLLXML validation (needs `java`) |
| `--strict` | flag | off | non-zero exit on warnings / validation errors |
| `--report` | path | – | write a JSON build report |
