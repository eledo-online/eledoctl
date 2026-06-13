from __future__ import annotations

from eledoctl.internal.docs.transformer import (
    TransformMessage,
    TransformMessageLevel,
    TransformStatus,
    _convert_admonitions,
    _has_reference,
    _is_frontmatter_value,
    _normalize_line_endings,
    _parse_frontmatter,
    _status_for,
    transform_document,
)
from tests.eledoctl.internal.docs.transformer_helpers import options_only


def test_normalize_line_endings_converts_crlf_and_cr_to_lf() -> None:
    assert _normalize_line_endings("a\r\nb\rc\n") == "a\nb\nc\n"


def test_transform_document_strips_frontmatter_and_returns_metadata() -> None:
    result = transform_document(
        options=options_only(strip_frontmatter=True),
        source_doc="""---
title: Creating PDFs
sidebar_position: 3
draft: false
tags:
  - docs
  - api
nested:
  enabled: true
---

# Creating PDFs
""",
    )

    assert result.status == TransformStatus.SUCCESS
    assert result.metadata == {
        "title": "Creating PDFs",
        "sidebar_position": 3,
        "draft": False,
        "tags": ["docs", "api"],
        "nested": {"enabled": True},
    }
    assert result.content == "# Creating PDFs\n"


def test_transform_document_accepts_empty_frontmatter() -> None:
    result = transform_document(
        options=options_only(strip_frontmatter=True),
        source_doc="""---
---

# Title
""",
    )

    assert result.status == TransformStatus.SUCCESS
    assert result.metadata == {}
    assert result.content == "# Title\n"


def test_transform_document_can_keep_frontmatter_when_disabled() -> None:
    source = """---
title: Test
---

# Test
"""

    result = transform_document(
        source_doc=source,
        options=options_only(strip_frontmatter=False),
    )

    assert result.status == TransformStatus.SUCCESS
    assert result.metadata == {}
    assert result.content == source


def test_parse_frontmatter_reports_invalid_yaml_as_failure() -> None:
    messages: list[TransformMessage] = []

    metadata = _parse_frontmatter(
        """title: [
""",
        messages,
    )

    assert metadata == {}
    assert len(messages) == 1
    assert messages[0].level == TransformMessageLevel.ERROR
    assert messages[0].code == "invalid_frontmatter_yaml"


def test_transform_document_reports_invalid_yaml_as_failure() -> None:
    result = transform_document(
        options=options_only(strip_frontmatter=True),
        source_doc="""---
title: [
---

# Title
""",
    )

    assert result.status == TransformStatus.FAILURE
    assert result.metadata == {}
    assert result.content == "# Title\n"
    assert len(result.messages) == 1
    assert result.messages[0].code == "invalid_frontmatter_yaml"


def test_parse_frontmatter_ignores_non_mapping_root() -> None:
    messages: list[TransformMessage] = []

    metadata = _parse_frontmatter(
        """- one
- two
""",
        messages,
    )

    assert metadata == {}
    assert len(messages) == 1
    assert messages[0].level == TransformMessageLevel.WARNING
    assert messages[0].code == "unsupported_frontmatter_root"


def test_parse_frontmatter_ignores_non_string_keys() -> None:
    messages: list[TransformMessage] = []

    metadata = _parse_frontmatter(
        """1: numeric key
title: Valid
""",
        messages,
    )

    assert metadata == {"title": "Valid"}
    assert len(messages) == 1
    assert messages[0].level == TransformMessageLevel.WARNING
    assert messages[0].code == "unsupported_frontmatter_key"


def test_is_frontmatter_value_accepts_json_like_yaml_values() -> None:
    assert _is_frontmatter_value(None) is True
    assert _is_frontmatter_value(True) is True
    assert _is_frontmatter_value(1) is True
    assert _is_frontmatter_value(1.5) is True
    assert _is_frontmatter_value("text") is True
    assert _is_frontmatter_value(["a", 1, False]) is True
    assert _is_frontmatter_value({"nested": ["a", 1, None]}) is True


def test_transform_document_warns_on_unterminated_frontmatter() -> None:
    source = """---
title: Missing close

# Title
"""

    result = transform_document(options=options_only(strip_frontmatter=True), source_doc=source)

    assert result.status == TransformStatus.WARNING
    assert result.metadata == {}
    assert result.content == source
    assert len(result.messages) == 1
    assert result.messages[0].code == "unterminated_frontmatter"


def test_transform_document_removes_import_lines() -> None:
    result = transform_document(
        options=options_only(remove_imports=True),
        source_doc="""import DocFeedbackForm from '@site/src/components/DocFeedbackForm';

# Title

Content.
""",
    )

    assert result.status == TransformStatus.SUCCESS
    assert (
        result.content
        == """
# Title

Content.
"""
    )


def test_transform_document_can_keep_import_lines_when_disabled() -> None:
    source = "import Something from './Something';\n\n# Title\n"

    result = transform_document(
        source_doc=source,
        options=options_only(remove_imports=False),
    )

    assert result.status == TransformStatus.SUCCESS
    assert result.content == source


def test_convert_admonitions_converts_known_admonition_to_blockquote() -> None:
    result = _convert_admonitions(
        """Before.

:::note
This is important.

Second paragraph.
:::

After.""",
        messages=[],
    )

    assert (
        result
        == """Before.

> **Note**
> This is important.
>
> Second paragraph.

After."""
    )


def test_convert_admonitions_preserves_custom_title() -> None:
    result = _convert_admonitions(
        """:::warning Read this first
Careful.
:::
""",
        messages=[],
    )

    assert (
        result
        == """> **Warning — Read this first**
> Careful.
"""
    )


def test_convert_admonitions_warns_on_unclosed_admonition() -> None:
    messages: list[TransformMessage] = []

    result = _convert_admonitions(
        """:::tip
Use this carefully.""",
        messages=messages,
    )

    assert (
        result
        == """> **Tip**
> Use this carefully."""
    )
    assert len(messages) == 1
    assert messages[0].level == TransformMessageLevel.WARNING
    assert messages[0].code == "unterminated_admonition"


def test_convert_admonitions_trims_blank_lines_after_opening_and_before_closing() -> None:
    result = _convert_admonitions(
        """:::note

JSON mode is intended for advanced users. If you are working with simple templates,\
 read the **[Guided Fields](../../data-input/guided-fields.mdx)** documentation first.

:::\
""",
        messages=[],
    )

    assert (
        result
        == """> **Note**
> JSON mode is intended for advanced users. If you are working with simple templates,\
 read the **[Guided Fields](../../data-input/guided-fields.mdx)** documentation first."""
    )


def test_transform_document_removes_unsupported_jsx_component_lines() -> None:
    result = transform_document(
        options=options_only(remove_unsupported_jsx=True),
        source_doc="""# Title

<DocFeedbackForm />

Content.
""",
    )

    assert result.status == TransformStatus.SUCCESS
    assert (
        result.content
        == """# Title


Content.
"""
    )
    assert len(result.messages) == 0


def test_transform_document_can_keep_unsupported_jsx_when_disabled() -> None:
    source = """# Title

<DocFeedbackForm />

Content.
"""

    result = transform_document(
        source_doc=source,
        options=options_only(remove_unsupported_jsx=False),
    )

    assert result.status == TransformStatus.SUCCESS
    assert result.content == source


def test_missing_reference_document_is_allowed_with_warning() -> None:
    result_with_none = transform_document(source_doc="# Title\n", reference_doc=None)
    result_with_empty = transform_document(source_doc="# Title\n", reference_doc="")

    assert result_with_none.status == TransformStatus.WARNING
    assert result_with_none.content == "# Title\n"
    assert result_with_empty.status == TransformStatus.WARNING
    assert result_with_empty.content == "# Title\n"


def test_has_reference_requires_non_empty_content() -> None:
    assert _has_reference(None) is False
    assert _has_reference("") is False
    assert _has_reference("   ") is False
    assert _has_reference("# Existing CMS document") is True


def test_status_for_returns_failure_when_any_error_exists() -> None:
    assert (
        _status_for(
            [
                TransformMessage(
                    level=TransformMessageLevel.WARNING,
                    code="warning",
                    message="Warning.",
                ),
                TransformMessage(
                    level=TransformMessageLevel.ERROR,
                    code="error",
                    message="Error.",
                ),
            ]
        )
        == TransformStatus.FAILURE
    )


def test_status_for_returns_warning_when_any_warning_exists() -> None:
    assert (
        _status_for(
            [
                TransformMessage(
                    level=TransformMessageLevel.WARNING,
                    code="warning",
                    message="Warning.",
                )
            ]
        )
        == TransformStatus.WARNING
    )


def test_status_for_returns_success_without_messages() -> None:
    assert _status_for([]) == TransformStatus.SUCCESS


def test_supported_image_component_uses_default_alt_text_when_alt_is_missing() -> None:
    result = transform_document(
        source_doc='<ImageWithCaption src="/img/example.png" caption="Example." />',
        options=options_only(convert_supported_images=True),
    )

    assert result.status == TransformStatus.SUCCESS
    assert result.content == "![Image](/img/example.png)"


def test_remove_unsupported_jsx_preserves_supported_image_component_when_image_transform_is_disabled() -> None:
    source = '<ImageWithCaption src="/img/example.png" alt="Example" />\n'

    result = transform_document(
        source_doc=source,
        options=options_only(remove_unsupported_jsx=True),
    )

    assert result.status == TransformStatus.SUCCESS
    assert result.content == source
    assert result.messages == ()


def test_reference_link_patching_warns_when_reference_doc_is_missing() -> None:
    source = "[Template Editor](./template-editor/index.mdx)\n"

    result = transform_document(
        source_doc=source,
        reference_doc=None,
        options=options_only(patch_links_from_reference=True),
    )

    assert result.status == TransformStatus.WARNING
    assert result.content == source
    assert len(result.messages) == 1
    assert result.messages[0].code == "missing_reference_doc"
