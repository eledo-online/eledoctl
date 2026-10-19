"""Read-only detection of CMS articles not represented in the Git docs tree.

A directory pull has enough scope to compare remote children with local docs.
Single-file pulls deliberately skip this check: their sibling set is unknown.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from eledoctl.internal.docs.reverse import PullAction, PullResult
from eledoctl.internal.docs.uploader import SyncItem
from pyeledo import EledoApiError, EledoInvalidResponseError
from pyeledo.internal.cms import CmsClient


def _is_represented(
    path: tuple[str, ...],
    expected_paths: set[tuple[str, ...]],
) -> bool:
    """A path is valid if Git has a file there or anywhere beneath it.

    A CMS folder node need not have a Git index.mdx to be legitimate.
    """
    return any(len(expected) >= len(path) and expected[: len(path)] == path for expected in expected_paths)


async def detect_cms_only_articles(
    *,
    cms: CmsClient,
    items: Sequence[SyncItem],
    source_root: Path,
    selection: Path,
    destination_root: str,
    dry_run: bool,
) -> tuple[PullResult, ...]:
    """Report CMS-only articles inside a fully selected directory subtree.

    No CMS changes or local file writes are performed. Every CMS-only article
    receives a failure row (including nested articles). Retrieval failures are
    also reported rather than being mistaken for an empty CMS hierarchy.
    """
    if selection.is_file():
        return ()

    relative = selection.resolve().relative_to(source_root.resolve())
    segments = tuple(part for part in destination_root.strip("/").split("/") if part)
    root = (*segments, *relative.parts)
    expected_paths = {item.target_segments for item in items}
    results: list[PullResult] = []
    visited: set[tuple[str, ...]] = set()

    async def visit(path: tuple[str, ...], *, is_root: bool = False) -> None:
        if path in visited:
            return
        visited.add(path)
        target = "/" + "/".join(path)

        try:
            response = await cms.retrieve_article(path)
        except (EledoApiError, EledoInvalidResponseError) as exc:
            results.append(
                PullResult(
                    source_path=None,
                    target_path=target,
                    action=PullAction.FAILED,
                    dry_run=dry_run,
                    written=False,
                    messages=(f"Cannot inspect CMS hierarchy at {target}: {exc}",),
                    error_code="cms_tree_read_failed",
                )
            )
            return

        if not is_root and not _is_represented(path, expected_paths):
            results.append(
                PullResult(
                    source_path=None,
                    target_path=target,
                    action=PullAction.FAILED,
                    dry_run=dry_run,
                    written=False,
                    messages=(
                        f"CMS-only article {target}: no corresponding document or directory "
                        "exists in the selected Git source tree; manual reconciliation required.",
                    ),
                    error_code="cms_only_article",
                )
            )

        for child in response.children:
            await visit((*path, child.slug))

    await visit(root, is_root=True)
    return tuple(results)
