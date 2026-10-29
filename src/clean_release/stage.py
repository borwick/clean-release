"""`stage`: build a release's export from the tag's tree into the staging repo.

The staging repo is a git repo of its own at `<root>/local/clean-release/`,
one commit per stage; its `HEAD^{tree}` is the tree of record
(`docs/data-structures/STAGING-REPO.md`). Every check runs before it is
touched, so a refusal writes nothing.
"""

import re
from dataclasses import dataclass
from pathlib import Path

from clean_release import Refusal, git, machine, policy
from clean_release.git import Entry

STAGING = Path("local/clean-release")
MESSAGE = re.compile(r"^stage (\S+) ([0-9a-f]{40,64})$")


def message(version: str, tag_sha: str) -> str:
    """A stage commit's message, the form `MESSAGE` parses."""
    return f"stage {version} {tag_sha}"


@dataclass(frozen=True)
class Staged:
    """What one `stage` wrote: where, the tree SHA, and the path counts."""

    path: Path
    tree: str
    commit: str
    shipped: int
    excluded: int


@dataclass(frozen=True)
class Export:
    """A tag's tree under a policy: every tag entry, what ships, its files rewritten."""

    at_tag: list[Entry]
    entries: list[Entry]
    files: dict[str, bytes]
    excluded: list[str]


@dataclass(frozen=True)
class Head:
    """The staging repo's last stage: where, its tree, and the version and tag commit."""

    path: Path
    tree: str
    version: str
    tag: str


def staged(root: Path) -> Head:
    """Read the last stage from the staging repo's HEAD; none refuses."""
    staging = root / STAGING
    again = "run `clean-release stage VERSION`"
    if not (staging / ".git").exists():
        raise Refusal(f"no staging repo at {staging}; {again}")
    if not git.ok(staging, "rev-parse", "--verify", "-q", "HEAD"):
        raise Refusal(f"the staging repo {staging} has no commit; {again}")
    message = git.run(staging, "log", "-1", "--format=%B", "HEAD").decode().strip()
    found = MESSAGE.match(message)
    if found is None:
        raise Refusal(f"{staging} HEAD is not a stage commit; {again}")
    tree = git.run(staging, "rev-parse", "HEAD^{tree}").decode().strip()
    return Head(staging, tree, found[1], found[2])


def stage(root: Path, version: str) -> Staged:
    """Stage version's tag of the private repo at root."""
    pol = policy.load(root)
    mach = machine.load(root.name)
    tag = pol.tag.format(version=version)
    if not git.ok(root, "rev-parse", "--verify", "-q", f"refs/tags/{tag}^{{commit}}"):
        raise Refusal(f"no tag {tag} in {root}; tag the release first: git tag {tag}")
    tag_sha = git.run(root, "rev-parse", f"refs/tags/{tag}^{{commit}}").decode().strip()
    export = build(root, pol, tag_sha)

    if not git.ok(root, "check-ignore", "-q", str(STAGING)):
        raise Refusal(
            f"{STAGING} is not ignored by {root}; add `local/` to its .gitignore "
            "so the private repo cannot pick up the staging repo"
        )
    staging = _open(root / STAGING)
    tree = git.write_tree(staging, export.entries, export.files)
    commit = _commit(staging, tree, message(version, tag_sha), mach.identity)
    git.run(staging, "read-tree", "--reset", "-u", "HEAD")
    return Staged(staging, tree, commit, len(export.entries), len(export.excluded))


def build(root: Path, pol: policy.Policy, commit: str) -> Export:
    """The export of commit's tree under pol, rewrites applied; a mismatch refuses."""
    at_tag = git.ls_tree(root, commit)
    shipped, excluded = policy.classify(pol, [e.path for e in at_tag])
    keep = set(shipped)
    entries = [e for e in at_tag if e.path in keep]
    content = git.read_blobs(root, [e.sha for e in entries if e.type == "blob"])
    files = {e.path: content[e.sha] for e in entries if e.type == "blob"}
    _rewrite(pol, {e.path: e for e in entries}, files)
    return Export(at_tag, entries, files, excluded)


def _rewrite(
    pol: policy.Policy, export: dict[str, Entry], files: dict[str, bytes]
) -> None:
    """Apply each rule in file order to files, in place; any mismatch refuses."""
    for i, rule in enumerate(pol.rewrites, 1):
        where = f"[[rewrite]] {i} on {rule.path}"
        entry = export.get(rule.path)
        if entry is None:
            raise Refusal(
                f"{where}: {rule.path} is not in the export; include it or drop the rule"
            )
        if entry.mode not in ("100644", "100755"):
            raise Refusal(
                f"{where}: {rule.path} is not a regular file (mode {entry.mode})"
            )
        try:
            text = files[rule.path].decode("utf-8")
        except UnicodeDecodeError:
            raise Refusal(f"{where}: {rule.path} is not UTF-8 text") from None
        new, count = rule.pattern.subn(rule.replace, text)
        if count != rule.expect:
            raise Refusal(
                f"{where}: pattern matched {count} time(s), expect = {rule.expect}; "
                "fix the rule or its expect"
            )
        files[rule.path] = new.encode("utf-8")


def _open(staging: Path) -> Path:
    """The staging repo, created on the first run; never a directory of another repo."""
    if not (staging / ".git").exists():
        if staging.exists() and any(staging.iterdir()):
            raise Refusal(f"{staging} exists but is not a git repo; move it aside")
        staging.mkdir(parents=True, exist_ok=True)
        git.run(staging, "init", "-q", "-b", "main")
    top = Path(git.run(staging, "rev-parse", "--show-toplevel").decode().strip())
    if top.resolve() != staging.resolve():
        raise Refusal(f"{staging} is not the top of its own git repo; move it aside")
    return staging


def _commit(staging: Path, tree: str, message: str, who: machine.Identity) -> str:
    """Commit tree on top of HEAD, if any, as who; move HEAD to it."""
    parent = []
    if git.ok(staging, "rev-parse", "--verify", "-q", "HEAD"):
        parent = ["-p", git.run(staging, "rev-parse", "HEAD").decode().strip()]
    args = ["-c", "commit.gpgsign=false", "commit-tree", tree, *parent, "-m", message]
    commit = git.run(staging, *args, env=who.env()).decode().strip()
    git.run(staging, "update-ref", "HEAD", commit)
    return commit
