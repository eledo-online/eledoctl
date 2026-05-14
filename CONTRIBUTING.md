# Contributing

This project is currently pre-alpha.

## Development setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
pytest
```

## Code style

- format with Black
- lint with Ruff
- write behavior-focused tests
- keep `pyeledo` independent from CLI concerns
- keep Eledo authorization enforced server-side
