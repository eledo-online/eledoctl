from __future__ import annotations

import yaml

from eledoctl.internal.docs.transformer import TransformMessageLevel, TransformStatus, transform_document
from tests.eledoctl.internal.docs.transformer_helpers import fixture, options_only


def test_frontmatter_fixture_normalizes_line_endings_to_unix() -> None:
    result = transform_document(
        source_doc=fixture("line_endings/source.mdx"),
        options=options_only(normalize_line_endings=True),
    )

    assert result.status == TransformStatus.SUCCESS
    assert result.content == fixture("line_endings/expected.mdx")
    assert result.messages == ()


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


def test_frontmatter_fixture_remove_imports() -> None:
    result = transform_document(
        source_doc=fixture("remove_imports/source.mdx"),
        options=options_only(remove_imports=True),
    )

    assert result.status == TransformStatus.SUCCESS
    assert result.content == fixture("remove_imports/expected.md")
    assert result.messages == ()


def test_frontmatter_fixture_admonitions_to_blockquotes() -> None:
    result = transform_document(
        source_doc=fixture("admonitions/source.mdx"),
        options=options_only(convert_admonitions=True),
    )

    assert result.status == TransformStatus.SUCCESS
    assert result.content == fixture("admonitions/expected.md")
    assert result.messages == ()


def test_supported_image_component_fixture_converts_image_with_caption_to_markdown() -> None:
    result = transform_document(
        source_doc=fixture("supported_images/source.mdx"),
        options=options_only(convert_supported_images=True),
    )

    assert result.status == TransformStatus.SUCCESS
    assert result.content == fixture("supported_images/expected.md")
    assert result.messages == ()


def test_unsupported_jsx_fixture_removes_component() -> None:
    result = transform_document(
        source_doc=fixture("unsupported_jsx/source.mdx"),
        options=options_only(remove_unsupported_jsx=True),
    )

    assert result.status == TransformStatus.SUCCESS
    assert result.content == fixture("unsupported_jsx/expected.md")

    assert len(result.messages) == 0


def test_reference_links_fixture_patches_source_urls_from_reference_doc() -> None:
    result = transform_document(
        source_doc=fixture("reference_links/source.mdx"),
        reference_doc=fixture("reference_links/reference.md"),
        options=options_only(patch_links_from_reference=True),
    )

    assert result.status == TransformStatus.SUCCESS
    assert result.content == fixture("reference_links/expected.mdx")
    assert result.messages == ()


def test_reference_links_fixture_extra_source_url_issues_warning() -> None:
    result = transform_document(
        source_doc=fixture("reference_links/source_extra_url_reference.mdx"),
        reference_doc=fixture("reference_links/reference.md"),
        options=options_only(patch_links_from_reference=True),
    )

    assert result.status == TransformStatus.WARNING
    assert result.content == fixture("reference_links/expected_extra_url_reference.mdx")

    assert len(result.messages) == 1
    assert result.messages[0].level == TransformMessageLevel.WARNING
    assert result.messages[0].code == "missing_reference_urls"


def test_reference_links_fixture_removed_url_link_in_source_doc() -> None:
    result = transform_document(
        source_doc=fixture("reference_links/source_with_removed_url.mdx"),
        reference_doc=fixture("reference_links/reference.md"),
        options=options_only(patch_links_from_reference=True),
    )

    assert result.status == TransformStatus.SUCCESS
    assert result.content == fixture("reference_links/expected_with_removed_url.mdx")
    assert result.messages == ()


def test_reference_links_fixture_no_reference_doc() -> None:
    result = transform_document(
        source_doc=fixture("reference_links/source.mdx"),
        reference_doc=None,
        options=options_only(patch_links_from_reference=True),
    )

    assert result.status == TransformStatus.WARNING
    # No URL transformation happens
    assert result.content == fixture("reference_links/source.mdx")

    assert len(result.messages) == 1
    assert result.messages[0].level == TransformMessageLevel.WARNING
    assert result.messages[0].code == "missing_reference_doc"


def test_reference_images_fixture_patches_source_urls_from_reference_doc() -> None:
    result = transform_document(
        source_doc=fixture("reference_images/source.mdx"),
        reference_doc=fixture("reference_images/reference.md"),
        options=options_only(convert_supported_images=True, patch_images_from_reference=True),
    )

    assert result.status == TransformStatus.SUCCESS
    assert result.content == fixture("reference_images/expected.mdx")
    assert result.messages == ()


def test_reference_images_fixture_extra_source_image_issues_warning() -> None:
    result = transform_document(
        source_doc=fixture("reference_images/source_extra_image_reference.mdx"),
        reference_doc=fixture("reference_images/reference.md"),
        options=options_only(convert_supported_images=True, patch_images_from_reference=True),
    )

    assert result.status == TransformStatus.WARNING
    assert result.content == fixture("reference_images/expected_extra_image_reference.mdx")

    assert len(result.messages) == 1
    assert result.messages[0].level == TransformMessageLevel.WARNING
    assert result.messages[0].code == "missing_reference_urls"


def test_reference_images_fixture_removed_image_link_in_source_doc() -> None:
    result = transform_document(
        source_doc=fixture("reference_images/source_with_removed_image.mdx"),
        reference_doc=fixture("reference_images/reference.md"),
        options=options_only(convert_supported_images=True, patch_images_from_reference=True),
    )

    assert result.status == TransformStatus.SUCCESS
    assert result.content == fixture("reference_images/expected_with_removed_image.mdx")
    assert result.messages == ()


def test_reference_images_fixture_no_reference_doc() -> None:
    result = transform_document(
        source_doc=fixture("reference_images/source.mdx"),
        reference_doc=None,
        options=options_only(convert_supported_images=False, patch_images_from_reference=True),
    )

    assert result.status == TransformStatus.WARNING
    # No Image URL transformation happens
    assert result.content == fixture("reference_images/source.mdx")

    assert len(result.messages) == 1
    assert result.messages[0].level == TransformMessageLevel.WARNING
    assert result.messages[0].code == "missing_reference_doc"


def test_full_pipeline_fixture_transforms_source_to_cms_markdown() -> None:
    result = transform_document(
        source_doc=fixture("full_pipeline/source.mdx"),
        reference_doc=fixture("full_pipeline/reference.md"),
    )

    expected_metadata = yaml.safe_load(fixture("full_pipeline/expected_metadata.yaml"))

    assert result.status == TransformStatus.SUCCESS
    assert result.metadata == expected_metadata
    assert result.content == fixture("full_pipeline/expected.md")
    assert result.messages == ()
