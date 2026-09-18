# Local consultation interface

Independent browser and terminal search over the RDF files in this
repository. It does **not** use openwordnet-pt.org, Cygnet, Solr, or
any extra Python packages — only the standard library.

## Requirements

- Python 3.10 or newer on `PATH`
- Turtle files under `data/` (`own-pt-*.ttl`, `own-en-*.ttl`)

## Start

From the repository root:

```bat
run.bat
```

or

```bash
python consult_ownpt.py
```

The first launch (or any launch after the RDF files change) builds
`consult/ownpt.sqlite`. The browser then opens at
`http://127.0.0.1:8765`. If that port is busy, the launcher tries the
next free port, or reuses an instance already serving this interface.

Stop the server with Ctrl+C. The SQLite index is gitignored and is
rebuilt when the Turtle files are newer than the index, or when you
pass `--rebuild`.

## Command-line options

| Option | Effect |
|--------|--------|
| `--query TERMO` | Search in the terminal and exit |
| `--rebuild` | Delete and rebuild the SQLite index |
| `--port N` | Listen on port *N* (default `8765`) |
| `--host ADDR` | Bind address (default `127.0.0.1`) |
| `--no-browser` | Do not open a browser window |
| `--help` | Show all options |

Example:

```bash
python consult_ownpt.py --query casa
```

## Browser

- Search by lemma, phrase, or synset id (`00001740-n`)
- Language filter: Portuguese, English, or both
- POS filter: noun, verb, adjective, satellite adjective, adverb
- Match mode: prefix, exact, or contains (accent-insensitive)
- Synset page: glosses, examples, hypernym chain, taxonomic and
  morphosemantic relations, nominalizations, Princeton equivalents
- Random synset; PT/EN interface language toggle
- Type-ahead suggestions

## HTTP API

Served by the same process:

| Path | Result |
|------|--------|
| `/api/stats` | Index counts (PT/EN lemmas, synsets, relations) |
| `/api/suggest?q=&lang=` | Lemma suggestions |
| `/api/search?q=&lang=&pos=&mode=` | Synset hits |
| `/api/synset/<id>` | Full synset record |
| `/api/random` | One random PT synset |

`mode` is `prefix` (default), `exact`, or `contains`. `lang` is `pt`,
`en`, or `all`.

## Index

`consult/store.py` streams the Turtle files through
`consult/turtle.py` and writes:

- `own-pt-words.ttl` / `own-en-words.ttl`
- `own-pt-wordsenses.ttl` / `own-en-wordsenses.ttl`
- `own-pt-synsets.ttl` / `own-en-synsets.ttl`
- `own-pt-relations.ttl` / `own-en-relations.ttl`
- `own-pt-morphosemantic-links.ttl` / `own-en-morphosemantic-links.ttl`

Missing files are skipped. Schema version is stored in the `meta`
table; bump `SCHEMA_VERSION` in `store.py` when the tables change.

## Tests

```bash
python -m unittest consult.test_parser
```
