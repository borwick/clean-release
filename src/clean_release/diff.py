"""`diff`: the staged export against the public repo's HEAD, and `check` on it.

A view: it writes nothing and refuses none of `commit`'s refusals. The
staging repo reads the public repo's objects through
`GIT_ALTERNATE_OBJECT_DIRECTORIES`, so the two trees diff without either
repo gaining an object; with no public commit the export diffs against
the empty tree (`docs/data-structures/PUBLIC-REPO.md`).
"""

from dataclasses import dataclass
from pathlib import Path

from clean_release import Refusal, check, commit, git, machine, policy, stage


@dataclass(frozen=True)
class Diff:
    """The staged tree against the public HEAD: what is new, removed and binary,
    check's result, the identity that would commit it, and the full diff."""

    public: Path
    last: str | None
    public_tree: str | None
    version: str
    tree: str
    new: list[str]
    removed: list[str]
    binaries: list[str]
    result: check.Result
    identity: machine.Identity
    text: str


def diff(root: Path) -> Diff:
    """Diff the private repo at root's last stage against its public repo's HEAD."""
    pol = policy.load(root)
    mach = machine.load(root.name)
    path = commit.public_path(mach, pol)
    if path is None:
        raise Refusal(commit.unset(root.name))
    head = stage.staged(root)
    public_tree, objects, last = _public(path, pol.tag)
    env = {"GIT_ALTERNATE_OBJECT_DIRECTORIES": objects} if objects else None
    old = public_tree or _empty_tree(head.path)
    trees = (old, head.tree)

    def run(*args: str) -> bytes:
        return git.run(head.path, "diff", "--no-renames", *args, *trees, env=env)

    new, removed = [], []
    fields = run("--name-status", "-z").decode().split("\0")
    for status, name in zip(fields[0::2], fields[1::2], strict=False):
        if status == "A":
            new.append(name)
        elif status == "D":
            removed.append(name)
    binaries = [
        record.split("\t", 2)[2]
        for record in run("--numstat", "-z").decode().split("\0")
        if record.startswith("-\t-\t")
    ]
    text = run("--no-color", "--no-ext-diff", "--no-textconv")
    return Diff(
        path,
        last,
        public_tree,
        head.version,
        head.tree,
        new,
        removed,
        binaries,
        check.check(root),
        mach.identity,
        text.decode(errors="replace"),
    )


def _public(path: Path, pattern: str) -> tuple[str | None, str | None, str | None]:
    """The public HEAD's tree, the objects directory holding it, and the last
    release tag; all None when there is no public commit yet."""
    if not (path / ".git").exists() or not git.ok(
        path, "rev-parse", "--verify", "-q", "HEAD"
    ):
        return None, None, None
    tree = git.run(path, "rev-parse", "HEAD^{tree}").decode().strip()
    git_dir = git.run(path, "rev-parse", "--absolute-git-dir").decode().strip()
    last = commit.last_release(path, pattern)
    return tree, str(Path(git_dir) / "objects"), last[0] if last else None


def _empty_tree(repo: Path) -> str:
    """The empty tree's SHA in repo's hash, computed, never written."""
    return git.run(repo, "hash-object", "-t", "tree", "/dev/null").decode().strip()
