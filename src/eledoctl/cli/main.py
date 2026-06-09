"""Top-level eledoctl command tree."""

from __future__ import annotations

import click

from eledoctl.cli.documents import documents_group
from eledoctl.cli.internal.docs import internal_group
from eledoctl.cli.login import login
from eledoctl.cli.profile import profile
from eledoctl.cli.templates import templates


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
def main() -> None:
    """Command-line toolkit for Eledo."""


main.add_command(login)
main.add_command(profile)
main.add_command(templates)
main.add_command(documents_group)
main.add_command(internal_group)

# Compatibility alias for direct imports.
app = main


if __name__ == "__main__":
    main()
