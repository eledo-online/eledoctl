# eledoctl
[![CI](https://github.com/eledo-online/eledoctl/actions/workflows/ci.yml/badge.svg)](https://github.com/eledo-online/eledoctl/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/eledo-online/eledoctl/graph/badge.svg?token=IVVXIPSQHM)](https://codecov.io/gh/eledo-online/eledoctl)
[![Release](https://img.shields.io/github/v/release/eledo-online/eledoctl)](https://github.com/eledo-online/eledoctl/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Eledo](https://img.shields.io/badge/Eledo-green.svg)](https://eledo.online/)
![Eledo PDF automation overview](https://github.com/user-attachments/assets/31ee16e8-7a60-4989-8a73-cf2c3097cfa4)

`eledoctl` is an open-source command-line toolkit for Eledo.

It contains two Python modules:

* `pyeledo` — async-native Python API client for Eledo REST APIs
* `eledoctl` — CLI, REPL, and automation layer built on top of `pyeledo`

The project is MIT licensed. Public functionality is exposed through `pyeledo` and `eledoctl`, while internal Eledo tooling is implemented as optional extensions.

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

`pyeledo` is async-first and async-only. It never stores credentials. Tokens are passed to the client by the caller.

```python
from pyeledo import EledoClient, TemplateScope

async with EledoClient(token="...") as client:
    profile = await client.get_profile()
    templates = await client.get_templates(scope=TemplateScope.PRIVATE)
```

## Initial CLI Tree

```bash
eledoctl profile
eledoctl templates list
eledoctl templates schema TEMPLATE_ID
eledoctl pdf generate TEMPLATE_ID --payload payload.json --output output.pdf
eledoctl internal docs sync docs
```

For now the CLI passes an empty token unless `--token` is provided. Persistent token storage will be added later in `eledoctl`, not in `pyeledo`.

## Installation

```bash
pip install eledoctl
```

## Development

The project uses modern Python tooling based on `uv`.

### Create or update the development environment

```bash
uv sync --group dev
```

### Run the test suite

```bash
uv run pytest
```

### Run the CLI

```bash
uv run eledoctl --help
```

### Format the code

```bash
uv run ruff format .
```

### Run linting

```bash
uv run ruff check .
```

### Run type checking

```bash
uv run mypy src
```

### Full validation

```bash
uv run ruff format .
uv run ruff check .
uv run mypy src
uv run pytest
```
