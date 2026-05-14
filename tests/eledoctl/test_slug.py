from pathlib import Path

from eledoctl.internal.docsync.slug import build_slug


def test_build_slug_from_markdown_path() -> None:
    slug = build_slug(Path("docs/product/template-editor.md"), docs_root=Path("docs"))

    assert slug == "/product/template-editor"


def test_build_slug_from_index_path() -> None:
    slug = build_slug(Path("docs/product/index.md"), docs_root=Path("docs"))

    assert slug == "/product"
