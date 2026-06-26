from __future__ import annotations

import click

from eledoctl.cli.internal.cms import internal_cms_group
from eledoctl.cli.internal.docs import internal_docs_group


@click.group("internal")
def internal_group() -> None:
    """Internal Eledo operational tooling."""


internal_group.add_command(internal_docs_group)
internal_group.add_command(internal_cms_group)
