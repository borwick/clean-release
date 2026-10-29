"""`commit`: write the approved tree to the public repo as one commit and a tag.

Every refusal runs before anything is written. The tree goes in as git
objects, `commit-tree` parents it on the last release, and a checkout
brings the work tree along; the public directory is never removed,
re-created or made (`docs/data-structures/PUBLIC-REPO.md`).
"""

import re
from dataclasses import dataclass
from pathlib import Path

from clean_release import Refusal, approve, git, machine, policy, stage

VERSION = re.compile(r"\d+(\.\d+)*")


@dataclass(frozen=True)
class Committed:
    """What one `commit` made, the push commands, and any line `git status` printed after."""

    path: Path
    version: str
    tag: str
    commit: str
    push: list[str]
    dirty: list[str]


@dataclass(frozen=True)
class Public:
    """The public repo as found: its branch and last release, None on a first release."""

    path: Path
    init: bool
    branch: str
    last: tuple[str, str] | None


def unset(repo: str) -> str:
    """What to set when no public repo is named; `doctor` says the same."""
    return (
        f"no public tree: set [repos.{repo}] public in the machine config "
        "or [release] public in clean-release.toml"
    )


def public_path(mach: machine.Machine | None, pol: policy.Policy | None) -> Path | None:
    """The machine config's `[repos.<name>] public`, else the policy's `[release] public`."""
    public = (mach and mach.public) or (pol and pol.public)
    return Path(public).expanduser() if public else None


def commit(root: Path) -> Committed:
    """Commit the approved stage of the private repo at root to its public repo."""
    pol = policy.load(root)
    mach = machine.load(root.name)
    head = stage.staged(root)
    approved = approve.read(head.path)
    if approved is None:
        raise Refusal(
            f"tree {head.tree} ({head.version}) is not approved; "
            "run `clean-release approve`"
        )
    if (approved.tree, approved.version) != (head.tree, head.version):
        raise Refusal(
            f"the staged tree {head.tree} ({head.version}) is not the approved tree "
            f"{approved.tree} ({approved.version}); run `clean-release approve`"
        )
    version = head.version
    tag = pol.tag.format(version=version)
    path = public_path(mach, pol)
    if path is None:
        raise Refusal(unset(root.name))
    found = _public(path, pol.tag, version, tag)

    if found.init:
        git.run(path, "init", "-q", "-b", found.branch)
    entries = git.ls_tree(head.path, "HEAD")
    blobs = git.read_blobs(head.path, [e.sha for e in entries if e.type == "blob"])
    files = {e.path: blobs[e.sha] for e in entries if e.type == "blob"}
    tree = git.write_tree(path, entries, files)
    if tree != approved.tree:
        raise Refusal(
            f"the tree written to {path} is {tree}, not the approved {approved.tree}"
        )
    env = mach.identity.env()
    parent = ["-p", found.last[1]] if found.last else []
    message = pol.message.replace("{version}", version)
    new = _out(
        path,
        "-c",
        "commit.gpgsign=false",
        "commit-tree",
        tree,
        *parent,
        "-m",
        message,
        env=env,
    )
    git.run(path, "update-ref", "HEAD", new, found.last[1] if found.last else "")
    _checkout(path, new)
    git.run(
        path, "-c", "tag.gpgsign=false", "tag", "-a", tag, "-m", message, new, env=env
    )
    dirty = git.run(path, "status", "--porcelain", "--untracked-files=all")
    return Committed(
        path,
        version,
        tag,
        new,
        _push(path, found.branch, tag),
        dirty.decode(errors="replace").splitlines(),
    )


def _checkout(path: Path, commit: str) -> None:
    """Make the index and work tree match commit, removing what it dropped."""
    git.run(path, "read-tree", "-m", "-u", commit)


def _push(path: Path, branch: str, tag: str) -> list[str]:
    """The owner's push commands; `remote add` first when there is no origin."""
    lines = []
    if not git.ok(path, "remote", "get-url", "origin"):
        lines.append(f"git -C {path} remote add origin <URL>")
    lines.append(f"git -C {path} push origin {branch} refs/tags/{tag}")
    return lines


def _public(path: Path, pattern: str, version: str, tag: str) -> Public:
    """Read the public repo and refuse what the draft's *Refusals* names."""
    if not VERSION.fullmatch(version):
        raise Refusal(f"version {version} is not dotted integers, such as 1.2.0")
    if not path.exists():
        raise Refusal(
            f"the public tree {path} does not exist; create it: mkdir -p {path}"
        )
    if not path.is_dir():
        raise Refusal(f"the public tree {path} is not a directory")
    if not (path / ".git").exists():
        if any(path.iterdir()):
            raise Refusal(
                f"the public tree {path} is neither a git repo nor empty; "
                "empty it or name another"
            )
        return Public(path, True, "main", None)
    top = Path(_out(path, "rev-parse", "--show-toplevel"))
    if top.resolve() != path.resolve():
        raise Refusal(f"{path} is not the top of its own git repo; it is in {top}")
    if not git.ok(path, "symbolic-ref", "-q", "HEAD"):
        raise Refusal(f"the public tree {path} has a detached HEAD; check out a branch")
    branch = _out(path, "symbolic-ref", "--short", "HEAD")
    status = git.run(path, "status", "--porcelain", "--untracked-files=all")
    if status.strip():
        listing = "\n  ".join(status.decode(errors="replace").splitlines())
        raise Refusal(
            f"the public tree {path} has uncommitted changes; clear them:\n  {listing}"
        )
    if git.ok(path, "rev-parse", "--verify", "-q", f"refs/tags/{tag}"):
        raise Refusal(f"tag {tag} already exists in {path}; release a newer version")
    if not git.ok(path, "rev-parse", "--verify", "-q", "HEAD"):
        return Public(path, False, branch, None)

    last = last_release(path, pattern)
    if last is None:
        raise Refusal(
            f"{path} has commits but no tag matching {pattern}; "
            "clean-release has not committed there"
        )
    last_tag, last_commit = last
    if _out(path, "rev-parse", "HEAD") != last_commit:
        raise Refusal(
            f"HEAD of {path} is not the last release {last_tag}; "
            "someone committed there, so reset it to the tag or move it aside"
        )
    if _key(version) <= _key(tag_version(pattern, last_tag)):
        raise Refusal(
            f"version {version} is not newer than the last release {last_tag}"
        )
    return Public(path, False, branch, last)


def last_release(path: Path, pattern: str) -> tuple[str, str] | None:
    """The highest tag matching pattern and its commit, or None."""
    tags = [
        t
        for t in _out(path, "tag", "-l").splitlines()
        if tag_version(pattern, t) is not None
    ]
    if not tags:
        return None
    tag = max(tags, key=lambda t: _key(tag_version(pattern, t)))
    return tag, _out(path, "rev-parse", f"refs/tags/{tag}^{{commit}}")


def tag_version(pattern: str, tag: str) -> str | None:
    """The version in tag when it matches pattern, such as `v{version}`, else None."""
    regex = re.escape(pattern).replace(re.escape("{version}"), f"({VERSION.pattern})")
    found = re.fullmatch(regex, tag)
    return found[1] if found else None


def _key(version: str) -> tuple[int, ...]:
    return tuple(int(n) for n in version.split("."))


def _out(cwd: Path, *args: str, env: dict[str, str] | None = None) -> str:
    return git.run(cwd, *args, env=env).decode().strip()
