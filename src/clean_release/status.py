"""`status`: where a release stands, read from the staging and public repos.

A view: it writes nothing, and refuses only when the policy or the
machine config does not load. Anything else it cannot read is reported
in its field (`docs/data-structures/PUBLIC-REPO.md`).
"""

from dataclasses import dataclass
from pathlib import Path

from clean_release import Refusal, approve, commit, git, machine, policy, stage


@dataclass(frozen=True)
class Status:
    """The public repo and its last release, the stage and its approval, and the
    public tree's state: clean, missing, empty, not a git repo, or uncommitted
    with dirty its `git status` lines. A field it could not read says why."""

    public: Path | None
    last: str
    staged: str
    approved: str
    tree: str
    dirty: list[str]


def status(root: Path) -> Status:
    """Read the release state of the private repo at root."""
    pol = policy.load(root)
    mach = machine.load(root.name)
    path = commit.public_path(mach, pol)
    staged, approved = _stage(root)
    if path is None:
        return Status(None, "none", staged, approved, commit.unset(root.name), [])
    last, tree, dirty = _public(path, pol.tag)
    return Status(path, last, staged, approved, tree, dirty)


def _stage(root: Path) -> tuple[str, str]:
    """The staged version and tree, and whether that tree is the approved one."""
    try:
        head = stage.staged(root)
    except Refusal as e:
        return f"none ({e})", "no"
    staged = f"{head.version} (tree {head.tree})"
    try:
        found = approve.read(head.path)
    except Refusal as e:
        return staged, f"no ({e})"
    if found is None:
        return staged, "no"
    if (found.tree, found.version) != (head.tree, head.version):
        return staged, f"no (the approval is for {found.version}, tree {found.tree})"
    return staged, "yes"


def _public(path: Path, pattern: str) -> tuple[str, str, list[str]]:
    """The last public version, the public tree's state, and its uncommitted lines."""
    if not path.exists():
        return "none", "missing", []
    if not path.is_dir():
        return "none", "not a directory", []
    if not (path / ".git").exists():
        if any(path.iterdir()):
            return "none", "not a git repo", []
        return "none", "empty", []
    try:
        last = "none"
        if git.ok(path, "rev-parse", "--verify", "-q", "HEAD"):
            found = commit.last_release(path, pattern)
            if found is not None:
                last = commit.tag_version(pattern, found[0]) or found[0]
        out = git.run(path, "status", "--porcelain", "--untracked-files=all")
    except Refusal as e:
        return "unknown", f"unreadable ({e})", []
    dirty = out.decode(errors="replace").splitlines()
    if dirty:
        return last, f"{len(dirty)} uncommitted", dirty
    return last, "clean", []
