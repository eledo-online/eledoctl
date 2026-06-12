from __future__ import annotations

from pathlib import Path

from eledoctl.internal.docs.transformer import TransformOptions

FIXTURES_ROOT = Path(__file__).parents[3] / "fixtures" / "docs_transformer"


def fixture(path: str) -> str:
    return (FIXTURES_ROOT / path).read_text(encoding="utf-8")

def options_only(**overrides: bool) -> TransformOptions:
    values = {
        "normalize_line_endings": False,
        "strip_frontmatter": False,
        "remove_imports": False,
        "convert_admonitions": False,
        "convert_supported_images": False,
        "remove_unsupported_jsx": False,
        "patch_links_from_reference": False,
        "patch_images_from_reference": False,
    }
    values.update(overrides)

    return TransformOptions(**values)