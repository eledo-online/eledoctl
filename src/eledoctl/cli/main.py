"""Top-level eledoctl command application."""

from __future__ import annotations

import typer

from eledoctl.cli import auth, internal, pdf, templates

app = typer.Typer(
    name="eledoctl",
    help="Command-line toolkit for Eledo.",
    no_args_is_help=True,
)

app.add_typer(auth.app, name="auth", help="Authentication and local credentials.")
app.add_typer(templates.app, name="templates", help="Template inspection commands.")
app.add_typer(pdf.app, name="pdf", help="PDF generation commands.")
app.add_typer(internal.app, name="internal", help="Internal Eledo operational tooling.")


def main() -> None:
    """Console entrypoint."""
    app()


if __name__ == "__main__":
    main()
