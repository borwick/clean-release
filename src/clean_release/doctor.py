"""`doctor`: check the machine config, the terms files, the scanner and the public tree.

Every check runs; each yields a `Note`, and a problem never stops the
next. The terms are counted, never shown: each terms file's entries are
reported by how many files at the private repo's HEAD hold them, in file
order, so an entry at 0 is a candidate to prune.
"""

import shutil
from dataclasses import dataclass
from pathlib import Path

from clean_release import Refusal, commit, git, machine, policy, scan, scanner


@dataclass(frozen=True)
class Note:
    """One check's outcome: ok or a problem, and what it found."""

    ok: bool
    text: str


def doctor(root: Path) -> list[Note]:
    """Check the setup for the private repo at root."""
    notes = []
    mach = pol = None
    try:
        mach = machine.load(root.name)
        count = len(mach.terms.plain) + len(mach.terms.sha256)
        notes.append(
            Note(
                True,
                f"machine config {machine.config_path()}: "
                f"{len(mach.terms_files)} terms file(s), {count} term(s)",
            )
        )
        notes += _hits(root, mach.terms_files)
    except Refusal as e:
        notes.append(Note(False, str(e)))
    try:
        pol = policy.load(root)
        notes.append(Note(True, f"policy {root / policy.FILENAME}"))
    except Refusal as e:
        notes.append(Note(False, str(e)))

    name = pol.scan.secrets if pol else scanner.DEFAULT
    absent = scanner.missing(name)
    notes.append(Note(False, absent) if absent else _found(name))
    notes.append(_public(root.name, commit.public_path(mach, pol)))
    return notes


def _hits(root: Path, files: tuple[Path, ...]) -> list[Note]:
    """Per terms file, how many files at HEAD hold each entry, path included."""
    if not files or not git.ok(root, "rev-parse", "--verify", "-q", "HEAD"):
        return []
    entries = [e for e in git.ls_tree(root, "HEAD") if e.type == "blob"]
    blobs = git.read_blobs(root, [e.sha for e in entries])
    texts = [
        f"{e.path}\n{blobs[e.sha].decode('utf-8', errors='replace')}" for e in entries
    ]
    lowered = [t.lower() for t in texts]
    digested = [scan.digests_in(t) for t in texts]
    notes = []
    for file in files:
        plain, digests = machine.read_terms(file)
        p = ", ".join(str(sum(t in low for low in lowered)) for t in plain)
        d = ", ".join(str(sum(x in held for held in digested)) for x in digests)
        notes.append(
            Note(
                True,
                f"terms file {file}: files at HEAD per entry: "
                f"plain [{p}], sha256 [{d}]",
            )
        )
    return notes


def _found(name: str) -> Note:
    return Note(True, f"scanner {name}: {shutil.which(name)}")


def _public(repo: str, path: Path | None) -> Note:
    """The public tree must be an empty directory or a git repo with nothing uncommitted."""
    if path is None:
        return Note(False, commit.unset(repo))
    if not path.is_dir():
        return Note(False, f"public tree {path} is not a directory")
    if not (path / ".git").exists():
        if any(path.iterdir()):
            return Note(False, f"public tree {path} is neither a git repo nor empty")
        return Note(True, f"public tree {path}: empty")
    try:
        status = git.run(path, "status", "--porcelain")
    except Refusal as e:
        return Note(False, f"public tree {path}: {e}")
    if status.strip():
        return Note(False, f"public tree {path} has uncommitted changes")
    return Note(True, f"public tree {path}: a clean git repo")
