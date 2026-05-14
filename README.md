# eledoctl

`eledoctl` is an open-source command-line toolkit for Eledo.

It contains two Python modules:

- `pyeledo` — async-native Python API client for Eledo REST APIs
- `eledoctl` — CLI, REPL, and automation layer built on top of `pyeledo`

The project is MIT licensed and designed for both public developer workflows and internal Eledo operational tooling.

## Goals

- provide a clean CLI for Eledo API workflows
- support PDF generation from command line
- provide reusable async Python API client
- support internal Git-to-CMS documentation synchronization
- preserve clean Git documentation repositories
- enable GitHub Actions automation

## Architecture

```text
repo/
├── src/
│   ├── pyeledo/       # Async SDK / REST client
│   └── eledoctl/      # CLI / REPL / orchestration
└── tests/
    ├── pyeledo/
    └── eledoctl/
```

`pyeledo` is async-first and async-only. A synchronous API may be added later only if a real requirement appears and its maintenance is explicitly justified.

## Initial commands

Planned public commands:

```bash
eledoctl auth login
eledoctl templates list
eledoctl pdf generate
```

Planned internal commands:

```bash
eledoctl internal docs sync docs
```

The `internal` namespace is not a security mechanism. All authorization must be enforced by the Eledo backend.

## Development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
pytest
```

Format and lint:

```bash
black src tests
ruff check src tests
```
