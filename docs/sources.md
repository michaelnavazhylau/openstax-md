# Upstream sources

This workspace compiles OpenStax textbooks. It consumes three upstream
checkouts, kept as plain sibling directories (not submodules) next to the
`cnxml2md` package:

| Directory | Upstream repository | Pinned commit | Role |
|---|---|---|---|
| `cnxml/` | https://github.com/openstax/cnxml | `0eb1f576c2380f3f395508acc855bcff76343082` | Python toolkit: CNXML/COLLXML namespaces, RelaxNG schemas, `jing.jar` validator, metadata parser |
| `cnxml2md/` | https://github.com/Ravenstine/cnxml2md | `c8307358dc461b6250b25e1acda57ed96852faa8` | The 2016 JavaScript converter this project replaces; kept untouched as the behavioural baseline |
| `osbooks-calculus-bundle/` | https://github.com/openstax/osbooks-calculus-bundle | `8dbc2ce19e804924b2517b89ac72ee45be949d15` | Content: Calculus Volumes 1–3 as CNXML modules plus shared media |

All three working trees were clean at the pinned commits. To reproduce the
workspace:

```bash
git clone https://github.com/openstax/cnxml.git cnxml
git clone https://github.com/Ravenstine/cnxml2md.git cnxml2md
git clone https://github.com/openstax/osbooks-calculus-bundle.git osbooks-calculus-bundle
```

Licenses: `cnxml/` is AGPL-3.0, `cnxml2md/` and this package are MIT,
`osbooks-calculus-bundle/` is CC BY-NC-SA 4.0.
