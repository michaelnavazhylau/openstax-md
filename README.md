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
