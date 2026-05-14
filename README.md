# eledoctl

`eledoctl` is an open-source command-line toolkit for Eledo.

It contains two Python modules:

- `pyeledo` — async-native Python API client for Eledo REST APIs
- `eledoctl` — CLI, REPL, and automation layer built on top of `pyeledo`

The project is MIT licensed and designed for both public developer workflows and internal Eledo operational tooling.

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

## Initial CLI tree

```bash
eledoctl profile
eledoctl templates list
eledoctl templates schema TEMPLATE_ID
eledoctl pdf generate TEMPLATE_ID --payload payload.json --output output.pdf
eledoctl internal docs sync docs
```

For now the CLI passes an empty token unless `--token` is provided. Persistent token storage will be added later in `eledoctl`, not in `pyeledo`.

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
