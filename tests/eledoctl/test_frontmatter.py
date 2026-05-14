from eledoctl.internal.transform.markdown import parse_git_document


def test_parse_git_document_strips_frontmatter() -> None:
    document = parse_git_document("---\ntitle: Example\n---\n\n# Heading\n")

    assert document.frontmatter == {"title": "Example"}
    assert document.content == "# Heading"
