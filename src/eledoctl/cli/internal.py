"""Internal command namespace."""

from __future__ import annotations

import typer

from eledoctl.cli.internal_docs import app as docs_app

app = typer.Typer(no_args_is_help=True)
app.add_typer(docs_app, name="docs", help="Internal documentation synchronization tooling.")
