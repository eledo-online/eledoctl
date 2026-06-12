from __future__ import annotations

import yaml

from eledoctl.internal.docs.transformer import TransformStatus, transform_document
from tests.eledoctl.internal.docs.transformer_helpers import fixture, options_only


def test_frontmatter_fixture_strips_yaml_frontmatter_and_returns_metadata() -> None:
    result = transform_document(
        source_doc=fixture("frontmatter/source.mdx"),
        options=options_only(strip_frontmatter=True),
    )

    expected_metadata = yaml.safe_load(fixture("frontmatter/expected_metadata.yaml"))

    assert result.status == TransformStatus.SUCCESS
    assert result.metadata == expected_metadata
    assert result.content == fixture("frontmatter/expected.md")
    assert result.messages == ()