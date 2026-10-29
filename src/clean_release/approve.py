"""`approve`: record the staged tree as approved, only when `check` passes on it.

The approval is `<git-dir>/clean-release-approved` in the staging repo,
one line `<tree SHA> <version>`; it lives in no tree, and `commit`
commits only that tree (`docs/data-structures/STAGING-REPO.md`).
"""

import os
from dataclasses import dataclass
from pathlib import Path

from clean_release import Refusal, check, git, stage

FILENAME = "clean-release-approved"


@dataclass(frozen=True)
class Approval:
    """The tree SHA and version the owner approved."""

    tree: str
    version: str


def path(staging: Path) -> Path:
    """Where the staging repo at staging keeps its approval."""
    git_dir = git.run(staging, "rev-parse", "--absolute-git-dir").decode().strip()
    return Path(git_dir) / FILENAME


def read(staging: Path) -> Approval | None:
    """The approval the staging repo holds, or None."""
    file = path(staging)
    if not file.exists():
        return None
    fields = file.read_text().split()
    if len(fields) != 2:
        raise Refusal(f"{file} is not `<tree> <version>`; run `clean-release approve`")
    return Approval(fields[0], fields[1])


def approve(root: Path) -> tuple[check.Result, Approval | None]:
    """Check the last stage; on a pass, approve its tree. Findings approve nothing."""
    result = check.check(root)
    if result.findings:
        return result, None
    head = stage.staged(root)
    if head.tree != result.tree:
        raise Refusal(
            f"the staged tree moved from {result.tree} to {head.tree} during check; "
            "run `clean-release approve` again"
        )
    _write(path(head.path), f"{head.tree} {head.version}\n")
    return result, Approval(head.tree, head.version)


def _write(file: Path, text: str) -> None:
    """Write text to file atomically: a temp file beside it, fsync, `os.replace`."""
    tmp = file.with_name(file.name + ".tmp")
    with tmp.open("w") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, file)
