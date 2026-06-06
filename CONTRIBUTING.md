# Contributing

This project is currently in alpha development.

## Development Setup

Install development dependencies:

```bash
uv sync --group dev
```

Run the test suite:

```bash
uv run pytest
```

Run the CLI locally:

```bash
uv run eledoctl --help
```

## Code Style

Format code:

```bash
uv run ruff format .
```

Lint code:

```bash
uv run ruff check .
```

Type check:

```bash
uv run mypy src
```

Before submitting changes, ensure all checks pass:

```bash
uv run ruff format .
uv run ruff check .
uv run mypy src
uv run pytest
```

## Design Principles

* Write behavior-focused tests.
* Prefer explicit type hints.
* Keep `pyeledo` independent from CLI concerns.
* Keep `pyeledo` stateless and transport-focused.
* Keep Eledo authorization enforced server-side.
* Prefer async-first implementations.
* Avoid introducing synchronous API variants unless a clear requirement exists.
* Preserve backwards compatibility whenever practical.
* Keep public APIs semantic and Pythonic, even when underlying Eledo endpoints are not.
